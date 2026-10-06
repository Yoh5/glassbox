"""The published snapshot, and the default it must not move.

The hackathon asks for "a URL to a working demo". This project's viewer binds
to `127.0.0.1` on purpose: a decision ledger is what an agent read, was told
and did, and a product that put one on a network by default would argue
against itself.

So the demo is an exception, and the job of these tests is to keep it one. The
hosted entry point passes `0.0.0.0` in one file, next to the sentence that
justifies it, and the page says what it is showing. The library's default stays
loopback, and if someone ever changes it, the first test here fails rather than
a reviewer noticing.

The second thing they pin is why this particular file can be published at all:
`runs/escalation/ledger.jsonl` records tiers, costs, the chain and the verdict,
and carries no evidence bytes. That was checked before the demo was written,
and it is checked again on every run, because a ledger is appended to.
"""

from __future__ import annotations

import ast
import inspect
import json
from pathlib import Path

from glassbox.ledger import Ledger
from glassbox.viewer import render, serve

RACINE = Path(__file__).resolve().parent.parent
LEDGER = RACINE / "runs" / "escalation" / "ledger.jsonl"


# ── Le défaut du produit ────────────────────────────────────────────────

def test_servir_reste_sur_la_boucle_locale_par_defaut():
    assert inspect.signature(serve).parameters["host"].default == "127.0.0.1"


def test_un_seul_appel_ouvre_le_visualiseur():
    """Un seul endroit doit APPELER `serve` avec autre chose que la boucle
    locale, et ce doit être celui qui porte la justification.

    Premier jet : chercher la chaîne « 0.0.0.0 » dans les fichiers. Elle est
    aussi dans la docstring de `serve`, qui explique précisément pourquoi ce
    n'est pas le défaut — le test accusait la phrase qui énonce la règle. On
    cherche donc un appel, par l'AST."""
    ouverts = []
    for chemin in list(RACINE.glob("glassbox/*.py")) + list(RACINE.glob("scripts/*.py")):
        arbre = ast.parse(chemin.read_text(encoding="utf-8"))
        for noeud in ast.walk(arbre):
            if not (isinstance(noeud, ast.Call) and getattr(noeud.func, "id", "") == "serve"):
                continue
            for mot in noeud.keywords:
                # Seulement une adresse ÉCRITE EN DUR. `cli.py` passe
                # `host=args.host` : c'est l'utilisateur qui choisit, sur sa
                # propre machine, et son défaut est vérifié juste en dessous.
                # Deuxième jet de ce test — le premier accusait la CLI.
                if mot.arg != "host" or not isinstance(mot.value, ast.Constant):
                    continue
                if mot.value.value != "127.0.0.1":
                    ouverts.append(chemin.relative_to(RACINE).as_posix())

    assert ouverts == ["scripts/hosted.py"]


def test_le_defaut_de_la_commande_serve_est_la_boucle_locale():
    """L'autre moitié : la CLI passe ce que l'utilisateur tape, donc c'est son
    défaut à elle qui décide pour qui ne tape rien."""
    source = (RACINE / "glassbox" / "cli.py").read_text(encoding="utf-8")

    assert '--host", default="127.0.0.1"' in source.replace("'", '"')


# ── Ce que la page publiée dit d'elle-même ──────────────────────────────

def test_la_page_hebergee_annonce_ce_qu_elle_est():
    from scripts.hosted import NOTICE

    statut, page = render("/", Ledger(LEDGER), NOTICE)

    assert statut == 200
    assert "read-only snapshot" in page
    assert "127.0.0.1" in page, "la page doit dire où le produit, lui, se lie"


def test_sans_avis_la_page_locale_est_inchangee():
    """La réciproque : l'avis est une option de la démo, pas une bannière que
    tout le monde récolte. Un utilisateur qui lance `glassbox serve` chez lui ne
    doit pas lire une phrase écrite pour le public d'un hackathon."""
    _, locale = render("/", Ledger(LEDGER))

    assert "read-only snapshot" not in locale


def test_l_avis_ne_remplace_pas_la_banniere_de_chaine():
    """Les deux coexistent, et c'est la seconde qui porte la vérité : elle est
    calculée par `Ledger.verify()`, pas écrite à la main."""
    from scripts.hosted import NOTICE

    _, page = render("/", Ledger(LEDGER), NOTICE)

    assert "read-only snapshot" in page
    assert "the chain holds" in page


# ── Pourquoi CE registre peut être publié ───────────────────────────────

def test_le_registre_publie_ne_contient_aucune_preuve():
    """Le champ `evidence` porte les octets que l'agent a lus. Publier un
    registre qui en contient serait publier ce qu'un agent a lu — ici il est
    vide partout, et c'est la raison pour laquelle cette page existe."""
    for ligne in LEDGER.read_text(encoding="utf-8").strip().splitlines():
        assert json.loads(ligne).get("evidence") == []


def test_le_registre_publie_ne_contient_ni_prompt_ni_reponse():
    """Les appels enregistrés portent un palier et un coût. Le jour où le
    recorder se mettrait à garder le texte envoyé au modèle, cette page
    publierait des prompts — et ce test tomberait avant."""
    interdits = {"prompt", "response", "messages", "content", "text", "completion"}

    for ligne in LEDGER.read_text(encoding="utf-8").strip().splitlines():
        for appel in json.loads(ligne).get("model_calls", []):
            assert not (interdits & set(appel)), f"champ sensible publié : {appel}"


def test_la_chaine_du_registre_publie_tient():
    """Publier un registre qui ne se vérifie pas serait la pire des vitrines."""
    problemes = Ledger(LEDGER).verify()

    assert problemes == [], problemes
