"""Nothing in here that nothing calls.

`list_models` was written, correct, and referenced by absolutely nothing -- not
the package, not the CLI, not an example, not a test. It had been reviewed and
it had been committed, and neither of those is a use.

The failure is cheap to describe and expensive to leave: code that nothing
calls is code nobody can run, so its claims are never checked against reality
and its bugs wait for the first real caller. It is also invisible to every
other test in this suite, because a test that calls it *is* a caller -- which
is why the rule below counts tests as callers too. Something no test even
mentions is something nothing at all uses.

Kept deliberately blunt: one reference anywhere is enough. The point is not to
police the design, it is to make dead code impossible to commit quietly.
"""

import ast
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parent.parent
DOSSIERS = ("glassbox", "examples", "tests")

#: Names the language or a framework calls for us, so the absence of a written
#: caller says nothing about them.
APPELES_AILLEURS = {"main"}


def _publics() -> list[tuple[str, str, int]]:
    trouves = []
    for fichier in sorted((RACINE / "glassbox").glob("*.py")):
        if fichier.name.startswith("__"):
            continue
        arbre = ast.parse(fichier.read_text(encoding="utf-8"))
        for noeud in arbre.body:
            if isinstance(noeud, (ast.FunctionDef, ast.ClassDef)):
                if not noeud.name.startswith("_") and noeud.name not in APPELES_AILLEURS:
                    trouves.append((noeud.name, fichier.name, noeud.lineno))
    return trouves


def _mentions(nom: str) -> int:
    """How many times the name appears anywhere but on its own def line."""
    total = 0
    for dossier in DOSSIERS:
        for fichier in (RACINE / dossier).rglob("*.py"):
            for numero, ligne in enumerate(fichier.read_text(encoding="utf-8").splitlines(), 1):
                depouille = ligne.strip()
                if depouille.startswith((f"def {nom}", f"class {nom}")):
                    continue
                total += nom in ligne
    return total


def test_the_package_exposes_something():
    """A guard that measures nothing would pass forever."""
    assert len(_publics()) > 10


@pytest.mark.parametrize("nom,fichier,ligne", _publics(), ids=lambda v: str(v))
def test_nothing_is_written_that_nothing_calls(nom, fichier, ligne):
    assert _mentions(nom) > 0, (
        f"{fichier}:{ligne} {nom} is referenced nowhere -- not by the package, "
        "an example, or a test. Either something should call it, or it should go."
    )
