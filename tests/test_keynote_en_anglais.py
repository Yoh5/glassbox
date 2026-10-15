"""The keynote must not put a French word in front of an English-speaking jury.

The video was written in French and translated once. A translation done once
is a translation that drifts the next time a scene is edited, and the cost is
not stylistic: a judge who cannot read a line on screen stops reading the
screen. The rules also require the submission to be in English.

So the check is mechanical rather than remembered. Every string the keynote
draws is pulled out of the source with `ast` -- not a regex over the file,
which would also catch the French comments, and the comments are deliberately
French because they are for us.

The markers below are words that exist in French and not in English. Words the
two languages share (`decision`, `escalated`, `cost`) are useless as markers
and are left out: a check that fires on correct English teaches you to ignore
it.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

KEYNOTE = Path(__file__).resolve().parent.parent / "submission" / "video" / "keynote.py"

#: Mots français qui ne sont pas aussi des mots anglais.
MARQUEURS = ("cumule", "reponse", "maillon", "temoignage", "preuve", "aucun",
             "qu'un", "qu'on", "precedent", "escalade ", "chaine", "cout ",
             "sans lire", "ce qu'", "n'a ", "n'est ", "pas une", "deux ")


def chaines_affichees() -> list[tuple[int, str]]:
    """(ligne, texte) pour chaque chaîne passée à `ecrire`."""
    arbre = ast.parse(KEYNOTE.read_text(encoding="utf-8"))
    trouvees: list[tuple[int, str]] = []
    for noeud in ast.walk(arbre):
        if not (isinstance(noeud, ast.Call)
                and getattr(noeud.func, "id", "") == "ecrire"):
            continue
        for arg in noeud.args:
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                trouvees.append((noeud.lineno, arg.value))
            elif isinstance(arg, ast.JoinedStr):
                trouvees.append((noeud.lineno, "".join(
                    p.value for p in arg.values if isinstance(p, ast.Constant))))
    return trouvees


def test_le_keynote_dessine_bien_du_texte():
    """Si `ecrire` est renommé, le reste de ce fichier ne vérifie plus rien."""
    assert len(chaines_affichees()) > 20


@pytest.mark.parametrize("ligne,texte", chaines_affichees())
def test_aucune_chaine_affichee_nest_en_francais(ligne: int, texte: str):
    fautifs = [m for m in MARQUEURS if m in texte.lower()]
    assert not fautifs, (
        f"keynote.py ligne {ligne} affiche {texte!r}, qui porte {fautifs}. "
        "La vidéo est regardée par un jury anglophone.")


def test_la_narration_aussi():
    """Elle est dite à voix haute : une phrase française s'entend encore mieux."""
    import sys
    sys.path.insert(0, str(KEYNOTE.parent))
    narration = ast.literal_eval(
        [n for n in ast.walk(ast.parse(KEYNOTE.read_text(encoding="utf-8")))
         if isinstance(n, ast.Assign)
         and getattr(n.targets[0], "id", "") == "NARRATION"][0].value)
    for cle, phrase in narration.items():
        fautifs = [m for m in MARQUEURS if m in phrase.lower()]
        assert not fautifs, f"NARRATION[{cle!r}] porte {fautifs}"
