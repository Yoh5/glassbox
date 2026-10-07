"""The numbers in the README are read out of the ledger, not typed.

This project's entire claim is that a decision record can be checked. The
README publishes five figures from the measured run — twelve asks, $0.0029, two
escalations, the answer changed in half of them, and the per-tier call counts —
and until now nothing stopped those figures drifting from the file they came
from. A reader has no way of knowing whether the number was computed or
remembered, and neither did we.

So the document is parsed and compared against `Ledger.stats()` on the ledger
that ships in the repository. Edit a figure in the README and this fails. Append
to the ledger and this fails. Both are the right answer: a published measurement
that no longer matches its artifact is the one defect this project cannot
afford, because it is the defect it was built to detect in other people's
systems.

The idea is borrowed from a sibling project, where the evidence document is
parsed back out of the run record and the gate shipped red so no figure could be
written into it before a real run produced one. Here the run already exists, so
the gate ships green — but it ships with the mutation that proves it can fail,
recorded in the commit that added it.
"""

from __future__ import annotations

import re
from pathlib import Path

from glassbox.ledger import Ledger

RACINE = Path(__file__).resolve().parent.parent
README = (RACINE / "README.md").read_text(encoding="utf-8")
LEDGER = RACINE / "runs" / "escalation" / "ledger.jsonl"


def stats() -> dict:
    """Lu à l'appel, pas à l'import.

    Au niveau du module, un registre devenu illisible fait tomber la COLLECTE :
    pytest rend « 1 error » et aucun des sept tests ne s'exécute, y compris
    celui qui dirait pourquoi. Vérifié en ajoutant une ligne au registre — un
    garde qui explose avant de parler ne garde rien.
    """
    return Ledger(LEDGER).stats()


def bloc_mesure() -> str:
    """Le bloc de code du README qui affiche les chiffres de la mesure."""
    debut = README.index("## Measured on real models")
    fin = README.index("##", debut + 10)
    blocs = re.findall(r"```\n(.*?)\n```", README[debut:fin], re.S)
    assert blocs, "le bloc de chiffres a disparu du README"
    return blocs[0]


# ── Les cinq chiffres publiés ───────────────────────────────────────────

def test_le_nombre_de_demandes():
    trouve = re.search(r"asks\s+(\d+)", bloc_mesure())
    assert trouve, "la ligne « asks » a disparu"
    assert int(trouve.group(1)) == stats()["asks"]


def test_le_cout_total():
    trouve = re.search(r"cost\s+\$([0-9.]+)", bloc_mesure())
    assert trouve, "la ligne « cost » a disparu"
    # Le README arrondit à quatre décimales, comme `glassbox stats`.
    assert trouve.group(1) == f"{stats()['cost_usd']:.4f}"


def test_les_appels_par_palier():
    bloc = bloc_mesure()
    for palier, appels in stats()["calls_by_tier"].items():
        trouve = re.search(rf"{palier}\s+(\d+) call", bloc)
        assert trouve, f"le palier {palier} n'est plus cité dans le README"
        assert int(trouve.group(1)) == appels, palier


def test_les_escalades_et_leur_effet():
    trouve = re.search(r"escalation\s+(\d+) of (\d+) ask\(s\), and the answer changed in (\d+)%",
                       bloc_mesure())
    assert trouve, "la ligne « escalation » a changé de forme"
    escalades, demandes, part = (int(g) for g in trouve.groups())

    assert escalades == stats()["escalated"]
    assert demandes == stats()["asks"]
    assert part == round(stats()["changed_share"] * 100)


# ── Et la prose qui les entoure ─────────────────────────────────────────

def test_le_gain_annonce_dans_le_texte_correspond_au_cout_mesure():
    """Le README raconte que le correctif a fait tomber le coût de $0.0048 à
    $0.0029. Le second chiffre doit être celui du registre publié, sinon la
    phrase raconte une amélioration qui ne mène pas au fichier qu'on livre."""
    assert f"${stats()['cost_usd']:.4f}" in README


def test_la_reserve_sur_le_bruit_d_echantillonnage_reste_ecrite():
    """La phrase la plus importante de la section n'est pas un chiffre : c'est
    celle qui dit qu'une partie de l'écart est du bruit et non le correctif.
    La retirer rendrait la mesure plus belle et moins vraie."""
    assert "sampling noise" in README


def test_la_chaine_du_registre_publie_tient():
    """Une mesure lue dans un registre qui ne se vérifie pas ne vaut rien."""
    assert Ledger(LEDGER).verify() == []


# ── Et le chiffre qui avait déjà dérivé ─────────────────────────────────

def test_le_nombre_de_tests_annonce_est_celui_que_pytest_collecte():
    """Le README annonçait 122 tests quand la suite en comptait 179.

    Trouvé en marchant le produit, pas en le relisant. C'est exactement la
    dérive que ce projet existe pour détecter chez les autres, et les sept
    gardes voisins ne couvraient que les chiffres de la mesure.

    Le compte est demandé à pytest plutôt que calculé : compter les fonctions
    `test_*` à la main donne 159, parce que `parametrize` en produit d'autres —
    un garde qui compte autrement que l'outil garde un autre chiffre.
    """
    import subprocess
    import sys

    sortie = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", str(RACINE / "tests")],
        capture_output=True, text=True, cwd=RACINE,
    ).stdout
    collectes = re.search(r"(\d+) tests? collected", sortie)
    assert collectes, f"pytest n'a pas annoncé de total :\n{sortie[-400:]}"

    annonce = re.search(r"\*\*(\d+) tests\.\*\*", README)
    assert annonce, "le README n'annonce plus de nombre de tests"
    assert int(annonce.group(1)) == int(collectes.group(1))
