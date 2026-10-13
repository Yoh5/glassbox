"""The head: what closes the four attacks a chain alone cannot see.

`scripts/adversarial.py` runs ten attacks against a real ledger. The chain
catches six. The four it misses — truncation, rollback, a forged append, a full
rewrite — share one cause: a chain proves that the records it holds follow one
another, and says nothing about records it does not hold.

A count and a head hash, written down by someone the adversary does not
control, close all four. These tests pin that down, one attack at a time, so the
guarantee cannot quietly regress into the one the README used to imply.
"""

import json

from glassbox.cli import main
from glassbox.ledger import Ledger


def build(tmp_path, decisions=4):
    led = Ledger(tmp_path / "ledger.jsonl")
    for i in range(decisions):
        led.append(name=f"d{i}", started_at=f"2026-10-14T09:3{i}:00Z",
                   agent_version="a1b2c3d", outcome={"action": "answered"})
    return tmp_path / "ledger.jsonl"


def engagement(chemin):
    led = Ledger(chemin)
    return led.commitment()


def lignes(chemin):
    return [l for l in chemin.read_text(encoding="utf-8").splitlines() if l.strip()]


def ecrire(chemin, lgs):
    chemin.write_text("\n".join(lgs) + "\n", encoding="utf-8")


# --------------------------------------------------------------------------- #
# La commande
# --------------------------------------------------------------------------- #
def test_head_prints_the_count_and_the_hash(tmp_path, capsys):
    chemin = build(tmp_path)
    assert main(["head", str(chemin)]) == 0
    out = capsys.readouterr().out
    assert "decisions  4" in out
    assert "sha256:" in out


def test_head_tells_you_to_store_it_elsewhere(tmp_path, capsys):
    """Un engagement gardé à côté du fichier qu'il engage ne protège de rien,
    et la commande doit le dire plutôt que de laisser le lecteur le deviner."""
    chemin = build(tmp_path)
    main(["head", str(chemin)])
    out = capsys.readouterr().out
    assert "does not control" in out
    assert "--expect-count" in out and "--expect-head" in out


def test_head_refuses_an_empty_ledger(tmp_path, capsys):
    chemin = tmp_path / "vide.jsonl"
    chemin.write_text("", encoding="utf-8")
    assert main(["head", str(chemin)]) == 2
    assert "no head to record" in capsys.readouterr().out


def test_head_refuses_an_absent_ledger(tmp_path, capsys):
    assert main(["head", str(tmp_path / "nulle-part.jsonl")]) == 2


# --------------------------------------------------------------------------- #
# Le contrôle, attaque par attaque
# --------------------------------------------------------------------------- #
def test_an_untouched_ledger_matches_its_own_head(tmp_path, capsys):
    chemin = build(tmp_path)
    n, tete = engagement(chemin)
    code = main(["verify", str(chemin), "--expect-count", str(n),
                 "--expect-head", tete])
    assert code == 0, capsys.readouterr().out


def test_truncation_is_caught_only_by_the_count(tmp_path, capsys):
    """L'attaque qui a motivé tout ça : on n'altère rien, on arrête l'histoire.

    Sans engagement, la chaîne tient — et c'est vrai, elle tient : ce qui reste
    est une suite valide. C'est la question qui était mal posée.
    """
    chemin = build(tmp_path)
    n, tete = engagement(chemin)

    ecrire(chemin, lignes(chemin)[:2])
    assert main(["verify", str(chemin)]) == 0, "la chaîne tronquée tient, et c'est normal"

    code = main(["verify", str(chemin), "--expect-count", str(n),
                 "--expect-head", tete])
    out = capsys.readouterr().out
    assert code == 1
    assert "removed from this ledger" in out
    assert "4 then, 2 now" in out


def test_rollback_is_caught(tmp_path, capsys):
    chemin = build(tmp_path)
    n, tete = engagement(chemin)
    ecrire(chemin, lignes(chemin)[:1])
    assert main(["verify", str(chemin), "--expect-count", str(n),
                 "--expect-head", tete]) == 1


def test_a_forged_append_is_caught(tmp_path, capsys):
    """Une décision inventée, chaînée correctement : le compte la trahit."""
    chemin = build(tmp_path)
    n, tete = engagement(chemin)
    led = Ledger(chemin)
    led.append(name="approved-by-nobody", started_at="2026-10-14T10:00:00Z",
               agent_version="a1b2c3d", outcome={"action": "approved"})
    assert main(["verify", str(chemin)]) == 0, "la chaîne reste valide"
    code = main(["verify", str(chemin), "--expect-count", str(n),
                 "--expect-head", tete])
    assert code == 1
    assert "added to this ledger" in capsys.readouterr().out


def test_a_full_rewrite_is_caught_by_the_head_alone(tmp_path, capsys):
    """Le compte ne bouge pas ; seule la tête le dit.

    C'est pourquoi les deux moitiés existent séparément : un compte seul
    laisserait passer une réécriture en place, une tête seule suffirait ici mais
    pas à nommer ce qui s'est passé.
    """
    chemin = build(tmp_path)
    n, tete = engagement(chemin)

    lgs = lignes(chemin)
    enregistrements = [json.loads(l) for l in lgs]
    enregistrements[1]["outcome"] = {"action": "refused"}
    from glassbox.ledger import _chain_hash
    prev = None
    for e in enregistrements:
        corps = {k: v for k, v in e.items() if k not in ("prev", "chain")}
        e["prev"] = prev
        e["chain"] = _chain_hash(corps, prev)
        prev = e["chain"]
    ecrire(chemin, [json.dumps(e, sort_keys=True, separators=(",", ":"))
                    for e in enregistrements])

    assert main(["verify", str(chemin)]) == 0, "une chaîne refaite est parfaite"
    code = main(["verify", str(chemin), "--expect-count", str(n),
                 "--expect-head", tete])
    out = capsys.readouterr().out
    assert code == 1
    assert "rewritten rather than cut" in out


def test_the_two_halves_are_independent(tmp_path, capsys):
    """On peut n'en donner qu'une, et elle contrôle ce qu'elle peut."""
    chemin = build(tmp_path)
    n, _ = engagement(chemin)
    ecrire(chemin, lignes(chemin)[:2])
    assert main(["verify", str(chemin), "--expect-count", str(n)]) == 1
    assert main(["verify", str(chemin), "--expect-count", "2"]) == 0


def test_no_expectation_means_no_commitment_check(tmp_path, capsys):
    """Sans engagement, le comportement d'avant est inchangé — la compatibilité
    compte, parce que la commande est déjà documentée telle quelle."""
    chemin = build(tmp_path)
    ecrire(chemin, lignes(chemin)[:2])
    assert main(["verify", str(chemin)]) == 0
