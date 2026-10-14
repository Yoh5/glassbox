"""What an agent author actually passes, and what the recorder must survive.

Four defects found on 14 October 2026 by handing `act()` the kinds of value a
real agent holds. Every one of them had the same shape: the value reached
`_canonical`, `json.dumps` raised or wrote something it should not have, and the
exception came out *inside the decision block* — so the decision was never
recorded at all.

That is the one failure this project cannot have. A recorder that drops the
record is worse than no recorder, because the absence looks like a decision that
was never taken.

The fifth test is different in kind: the line was written, Python read it back,
`verify()` reported nothing, and the file still was not JSON.
"""
from __future__ import annotations

import enum
import json
import math
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from glassbox.ledger import _canonical
from glassbox.recorder import Recorder
from glassbox.redact import PROFONDEUR_MAX, REPR_MAX, Redactor


class Etat(enum.Enum):
    OUVERT = "ouvert"


class ReprQuiFuit:
    """An object whose own `repr` carries the credential.

    Not contrived: a session, an HTTP client and a config object all print
    their configuration, and the token is part of it.
    """

    def __repr__(self) -> str:
        return "<Client token=sk-live-SECRET>"


class ReprCasse:
    def __repr__(self) -> str:
        raise RuntimeError("non")


def registre(tmp_path: Path, **champs: object) -> dict:
    """Records one action carrying `champs`, and returns the line written."""
    r = Recorder(root=tmp_path, agent_version="t", secrets=["sk-live-SECRET"])
    with r.decision("paiement") as d:
        d.act("virement", **champs)
    lignes = (tmp_path / "ledger.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lignes) == 1, "une décision, une ligne"
    return json.loads(lignes[0])


@pytest.mark.parametrize("valeur", [
    datetime(2026, 10, 14, tzinfo=timezone.utc),
    Decimal("19.99"),
    Path("/tmp/x"),
    uuid.UUID(int=1),
    Etat.OUVERT,
    1 + 2j,
    ReprQuiFuit(),
])
def test_une_valeur_non_json_est_decrite_et_la_decision_tient(tmp_path, valeur):
    """Each of these raised TypeError from _canonical and lost the record."""
    rendu = registre(tmp_path, montant=valeur)["actions"][0]["montant"]
    assert isinstance(rendu, str)
    assert rendu.startswith(f"<{type(valeur).__name__} ")


def test_le_repr_dun_objet_est_redige(tmp_path):
    """The last point before an append-only file, so the repr is redacted too."""
    rendu = registre(tmp_path, client=ReprQuiFuit())["actions"][0]["client"]
    assert "sk-live-SECRET" not in rendu
    assert "[redacted]" in rendu


def test_un_repr_qui_leve_ne_tue_pas_la_decision(tmp_path):
    """Et surtout : le registre ne doit pas accuser l'agent a sa place.

    `str(fields)` rappelait chaque `__repr__` hors du filet du redacteur. Celui
    qui levait faisait sortir l'exception du bloc de decision, et `__exit__`
    inscrivait `failed: RuntimeError` -- alors que l'action, elle, avait pu
    reussir. Un outil d'audit qui attribue a tort est pire qu'un outil muet.
    """
    ligne = registre(tmp_path, objet=ReprCasse())
    rendu = ligne["actions"][0]["objet"]
    assert "repr indisponible" in rendu and "RuntimeError" in rendu
    assert ligne["outcome"]["action"] == "virement", "l'action ne doit pas etre dite echouee"


def test_une_chaine_longue_reste_entiere(tmp_path):
    """Seules les valeurs *decrites* sont tronquees, pas le texte rendu tel quel."""
    rendu = registre(tmp_path, blob="x" * 10_000)["actions"][0]["blob"]
    assert len(rendu) == 10_000


def test_un_repr_enorme_est_tronque(tmp_path):
    rendu = registre(tmp_path, objet=Decimal("1" * 5_000))["actions"][0]["objet"]
    assert len(rendu) < REPR_MAX + 100 and "car.)" in rendu


def test_une_structure_cyclique_est_nommee_pas_suivie(tmp_path):
    """`d = {}; d["self"] = d` — deux lignes, et c'était un RecursionError."""
    cyclique: dict = {"nom": "a"}
    cyclique["moi"] = cyclique
    rendu = registre(tmp_path, charge=cyclique)["actions"][0]["charge"]
    assert rendu["nom"] == "a"
    assert rendu["moi"] == "<dict cycle>"


def test_une_liste_qui_se_contient_est_nommee(tmp_path):
    boucle: list = [1]
    boucle.append(boucle)
    rendu = registre(tmp_path, charge=boucle)["actions"][0]["charge"]
    assert rendu == [1, "<list cycle>"]


def test_le_meme_objet_deux_fois_de_suite_est_bien_parcouru_deux_fois():
    """Partage n'est pas cycle : interdire le second serait une régression."""
    commun = {"a": 1}
    rendu = Redactor([]).value({"x": commun, "y": commun})
    assert rendu == {"x": {"a": 1}, "y": {"a": 1}}


def test_le_plafond_de_profondeur_tombe_exactement_ou_il_est_annonce():
    """Mesure sur le redacteur seul : l'objet passe EST le premier niveau."""
    profond: dict = {}
    courant = profond
    for _ in range(PROFONDEUR_MAX + 10):
        suivant: dict = {}
        courant["x"] = suivant
        courant = suivant
    rendu = Redactor([]).value(profond)
    niveaux = 0
    while isinstance(rendu, dict):
        rendu = rendu["x"]
        niveaux += 1
    assert niveaux == PROFONDEUR_MAX
    assert rendu.startswith("<dict ")


def test_une_structure_trop_profonde_passe_par_le_recorder(tmp_path):
    """Par le recorder, la profondeur consommee depend de l'imbrication du
    champ -- ce qui compte est qu'une structure absurde s'enregistre."""
    profond: dict = {}
    courant = profond
    for _ in range(PROFONDEUR_MAX + 10):
        suivant: dict = {}
        courant["x"] = suivant
        courant = suivant
    rendu = registre(tmp_path, charge=profond)["actions"][0]["charge"]
    niveaux = 0
    while isinstance(rendu, dict):
        rendu = rendu["x"]
        niveaux += 1
    assert niveaux < PROFONDEUR_MAX, "la coupe doit tomber avant le plafond"
    assert rendu.startswith("<dict ")


def test_un_set_de_chaines_a_le_meme_ordre_dun_processus_a_lautre():
    """Deux interpréteurs, deux graines de hachage, un seul rendu.

    L'ordre d'itération d'un set de chaînes dépend de PYTHONHASHSEED. Le même
    action enregistrée deux fois produisait deux hachages de chaîne différents,
    donc deux registres que rien ne permettait de rapprocher.
    """
    programme = (
        "import json;from glassbox.redact import Redactor;"
        "print(json.dumps(Redactor([]).value("
        "{'t': {'alpha','beta','gamma','delta','epsilon','zeta','eta'}})))"
    )
    racine = Path(__file__).resolve().parent.parent
    rendus = set()
    for graine in ("0", "1", "2"):
        r = subprocess.run([sys.executable, "-c", programme],
                           capture_output=True, text=True, cwd=racine,
                           env={"PYTHONHASHSEED": graine, "PATH": ""})
        assert r.returncode == 0, r.stderr
        rendus.add(r.stdout.strip())
    assert len(rendus) == 1, f"ordres divergents : {rendus}"


def test_un_set_de_types_melanges_ne_fait_pas_exploser_le_tri():
    rendu = Redactor([]).value({"t": {1, "a", None, 2.5}})
    assert sorted(map(repr, rendu["t"])) == sorted(["1", "'a'", "None", "2.5"])


def test_une_cle_tuple_est_decrite_au_lieu_de_lever(tmp_path):
    """`{("a","b"): 1}` : la clé revenait en liste, non hachable, et ça levait."""
    rendu = registre(tmp_path, charge={("a", "b"): 1})["actions"][0]["charge"]
    assert list(rendu) == ["<tuple ('a', 'b')>"]


def test_une_cle_secrete_est_redigee(tmp_path):
    rendu = registre(tmp_path, charge={"sk-live-SECRET": 1})["actions"][0]["charge"]
    assert list(rendu) == ["[redacted]"]


@pytest.mark.parametrize("valeur", [float("nan"), float("inf"), float("-inf")])
def test_un_flottant_non_fini_ne_sort_pas_en_faux_json(tmp_path, valeur):
    """La ligne s'écrivait, Python la relisait, verify() ne disait rien.

    Et pourtant `NaN` et `Infinity` ne sont pas des jetons de la grammaire
    JSON : jq, Go et Rust refusaient la ligne. Un fichier qui s'annonce JSON
    Lines et qui n'en est pas trahit la promesse « un auditeur sans outillage
    peut le lire ».
    """
    ligne = (tmp_path / "ledger.jsonl")
    donnees = registre(tmp_path, taux=valeur)
    assert isinstance(donnees["actions"][0]["taux"], str)

    brut = ligne.read_text(encoding="utf-8")
    assert "NaN" not in brut and "Infinity" not in brut

    def refuser(jeton: str) -> None:
        raise AssertionError(f"constante non JSON dans le registre : {jeton}")

    json.loads(brut.strip(), parse_constant=refuser)


def test_canonical_refuse_un_non_fini_meme_sans_passer_par_le_redacteur():
    """Le filet du registre, indépendant de celui du rédacteur."""
    with pytest.raises(ValueError):
        _canonical({"taux": math.nan})


def test_les_valeurs_json_natives_gardent_leur_type(tmp_path):
    """La correction ne doit pas transformer 3 en "3"."""
    champs = {"retries": 3, "ratio": 0.5, "actif": True, "rien": None, "nom": "a"}
    assert registre(tmp_path, **champs)["actions"][0] == {"kind": "virement", **champs}
