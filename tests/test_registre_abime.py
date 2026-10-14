"""Le registre est le seul fichier dont on suppose qu'un adversaire le tient.

Tout le propos de la chaîne est que quelqu'un a peut-être édité ce fichier. Et
pourtant chaque lecteur appelait `json.loads` à nu : un octet corrompu ne
produisait pas un verdict mais un `JSONDecodeError`.

Trois conséquences, trouvées le 14 octobre 2026 :

1. **`verify` plantait au lieu de répondre.** Un auditeur ne pouvait pas
   distinguer un registre cassé d'un outil cassé — et un script non plus, les
   deux sortant non nuls. Un outil dont la promesse est *il détecte la
   falsification* doit répondre à la falsification par un constat.
2. **La démo publique renvoyait une trace** au lieu d'une page.
3. **`append` lisait la dernière chaîne avant d'écrire**, donc un octet ajouté
   empêchait le greffier d'enregistrer quoi que ce soit ensuite. Un déni
   d'enregistrement pour un octet, contre la seule faute que ce projet ne peut
   pas commettre.

Le banc adverse ne les avait pas vus : ses dix attaques manipulaient des
enregistrements, donc produisaient toutes du JSON valide. Il éprouvait la
solidité de la chaîne et jamais celle du lecteur.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from glassbox.ledger import Ledger
from glassbox.viewer import render

SABOTAGES = {
    "pas du json": "ceci n'est pas du json",
    "json tronque": '{"name": "x", "chain": "sha256:aa"',
    "json mais pas un objet": '"juste une chaine"',
    "objet sans les cles": '{"quoi": 1}',
    "tableau": "[1, 2, 3]",
    "nombre": "42",
    "null": "null",
}


def un_registre(tmp_path: Path, combien: int = 3) -> Ledger:
    registre = Ledger(tmp_path / "ledger.jsonl")
    for i in range(combien):
        registre.append(name=f"decision {i}", started_at=f"2026-01-0{i + 1}T00:00:00Z",
                        agent_version="t")
    return registre


def abimer(registre: Ledger, contenu: str, *, indice: int | None = None) -> None:
    """Ajoute `contenu` à la fin, ou écrase la ligne `indice`."""
    lignes = registre.path.read_text(encoding="utf-8").splitlines()
    if indice is None:
        lignes.append(contenu)
    else:
        lignes[indice] = contenu
    registre.path.write_text("\n".join(lignes) + "\n", encoding="utf-8")


@pytest.mark.parametrize("contenu", SABOTAGES.values(), ids=list(SABOTAGES))
def test_verify_rend_un_verdict_et_ne_leve_pas(tmp_path, contenu):
    registre = un_registre(tmp_path)
    abimer(registre, contenu)
    soucis = registre.verify()
    assert soucis, "une ligne qui n'est pas un enregistrement doit être signalée"
    assert any("line 4" in s for s in soucis), soucis


@pytest.mark.parametrize("contenu", SABOTAGES.values(), ids=list(SABOTAGES))
def test_la_page_rend_la_banniere_au_lieu_dune_trace(tmp_path, contenu):
    registre = un_registre(tmp_path)
    abimer(registre, contenu)
    statut, page = render("/", registre)
    assert statut == 200
    assert "does not hold" in page


@pytest.mark.parametrize("contenu", SABOTAGES.values(), ids=list(SABOTAGES))
def test_le_greffier_peut_encore_enregistrer(tmp_path, contenu):
    """Le déni d'enregistrement pour un octet.

    Refuser d'ajouter donnerait son résultat à l'attaque. La ligne abîmée reste
    dans le fichier et `verify` la signale tant que le registre existe, donc
    rien n'est caché — l'enregistrement continue par-dessus.
    """
    registre = un_registre(tmp_path)
    abimer(registre, contenu)
    registre.append(name="apres", started_at="2026-01-09T00:00:00Z", agent_version="t")
    noms = [r.name for r in registre.records()]
    assert noms[-1] == "apres"
    assert registre.verify(), "et la ligne abîmée est toujours signalée"


@pytest.mark.parametrize("contenu", SABOTAGES.values(), ids=list(SABOTAGES))
def test_commitment_et_records_ne_levent_pas(tmp_path, contenu):
    registre = un_registre(tmp_path)
    abimer(registre, contenu)
    compte, tete = registre.commitment()
    assert compte == 3, "une ligne qui n'est pas un enregistrement n'est pas comptée"
    assert tete == registre.records()[-1].chain
    assert registre.stats()["decisions"] == 3


def test_une_decision_ecrasee_par_du_bruit_est_signalee_deux_fois(tmp_path):
    """Sauter la ligne illisible sans le dire, ce serait la suppression gratuite.

    Elle est signalée comme ligne illisible, **et** la chaîne ne suit plus à
    partir de là. Les deux constats sont vrais et le second interdit de faire
    passer une suppression pour une panne de disque.
    """
    registre = un_registre(tmp_path, combien=5)
    abimer(registre, "}{ pas une decision", indice=2)
    soucis = registre.verify()
    assert any("line 3" in s for s in soucis), soucis
    assert any("does not follow the one before it" in s for s in soucis), soucis


def test_une_ligne_vide_nest_pas_un_sabotage(tmp_path):
    """Un `\\n` de trop en fin de fichier arrive, et n'accuse personne."""
    registre = un_registre(tmp_path)
    registre.path.write_text(registre.path.read_text(encoding="utf-8") + "\n\n  \n",
                             encoding="utf-8")
    assert registre.verify() == []
    assert render("/", registre)[0] == 200


def test_un_registre_entierement_illisible_ne_fait_pas_exploser_le_lecteur(tmp_path):
    chemin = tmp_path / "ledger.jsonl"
    chemin.write_text("rien\nde\nlisible\n", encoding="utf-8")
    registre = Ledger(chemin)
    assert len(registre.verify()) == 3
    assert registre.records() == []
    assert registre.commitment() == (0, None)
    assert render("/", registre)[0] == 200
    # Et on peut toujours enregistrer : la chaîne repart de zéro, ce que
    # `verify` continue de dire en signalant les trois lignes.
    registre.append(name="apres", started_at="2026-01-09T00:00:00Z", agent_version="t")
    assert [r.name for r in registre.records()] == ["apres"]


def test_un_champ_hors_chaine_reste_signale(tmp_path):
    """Ne pas avoir affaibli le contrôle existant en ajoutant le nouveau."""
    registre = un_registre(tmp_path, combien=1)
    ligne = json.loads(registre.path.read_text(encoding="utf-8").strip())
    ligne["ajoute_apres_coup"] = "sk"
    registre.path.write_text(json.dumps(ligne) + "\n", encoding="utf-8")
    assert any("which no hash covers" in s for s in registre.verify())


@pytest.mark.parametrize("chemin", [
    "/decision/²",      # isdigit() vrai, int() lève — plantait
    "/decision/½",
    "/decision/1²",
    "/decision/",
    "/decision/1/2",
    "/../etc/passwd",
    "/decision/999999999999999999999999",
    "/decision/-1",          # l'indexation négative aurait rendu le dernier
])
def test_aucun_chemin_forge_ne_fait_lever_le_routeur(tmp_path, chemin):
    """Atteignable depuis Internet sur la démo hébergée."""
    registre = un_registre(tmp_path)
    statut, page = render(chemin, registre)
    assert statut in (200, 404)
    assert "<h1>" in page
