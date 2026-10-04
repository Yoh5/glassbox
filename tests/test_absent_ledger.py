"""Nothing is not a passing grade.

The cheapest attack on a hash-chained ledger is not to alter it. Altering it
breaks the chain, and that is the one thing this tool always catches. The cheap
attack is to **delete** it — and `verify` answered, on a path that did not
exist:

    0 decision(s) verified: the chain holds.     (exit 0)

A nightly audit would have gone green through the whole incident. A tool whose
entire pitch is "can you still trust this record?" replied yes to no record at
all, and it is hard to think of a worse place for that answer to live.

It also greeted anyone who mistyped a path, which is how most people meet a
tool for the first time, and it made the README's first command look like a
broken demo rather than a wrong path.

The empty case is separated on purpose. An empty ledger is a legitimate state
before the first run and a catastrophic one after it, and nothing in the file
says which. The tool refuses to pick, and refuses to call it a pass.
"""

import io
import json
from pathlib import Path

import pytest

from glassbox.cli import main


def lance(*arguments, capsys) -> tuple[int, str]:
    code = main(list(arguments))
    return code, capsys.readouterr().out


COMMANDES = [
    ["verify"],
    ["stats"],
    ["trace", "--action", "read-file", "--evidence", "x"],
    ["replay", "--rule", "glassbox.rule:noop", "--evidence", "x"],
]


@pytest.mark.parametrize("commande", COMMANDES, ids=lambda c: c[0])
def test_a_missing_ledger_is_never_a_pass(commande, tmp_path, capsys):
    absent = tmp_path / "gone.jsonl"

    code, dit = lance(commande[0], str(absent), *commande[1:], capsys=capsys)

    assert code != 0, f"{commande[0]} passed on a ledger that does not exist"
    assert "does not exist" in dit


@pytest.mark.parametrize("commande", COMMANDES, ids=lambda c: c[0])
def test_it_names_the_path_it_looked_at(commande, tmp_path, capsys):
    """The usual cause is the boring one, and naming the path is what lets
    someone see it in a second."""
    absent = tmp_path / "gone.jsonl"

    _, dit = lance(commande[0], str(absent), *commande[1:], capsys=capsys)

    assert "gone.jsonl" in dit


def test_verify_says_what_a_missing_ledger_might_mean(tmp_path, capsys):
    """Not just that the file is absent: what it would mean if the path is
    right. That is the sentence an auditor needs."""
    _, dit = lance("verify", str(tmp_path / "gone.jsonl"), capsys=capsys)

    assert "the ledger is gone" in dit


# ── The empty case, which is not the same case ──────────────────────────

def test_an_empty_ledger_is_not_a_pass_either(tmp_path, capsys):
    vide = tmp_path / "empty.jsonl"
    vide.write_text("", encoding="utf-8")

    code, dit = lance("verify", str(vide), capsys=capsys)

    assert code != 0
    assert "no decisions" in dit


def test_it_refuses_to_guess_which_kind_of_empty(tmp_path, capsys):
    """A run that has not started and a run whose record was deleted look
    identical on disk. Picking one would be inventing the fact that matters."""
    vide = tmp_path / "empty.jsonl"
    vide.write_text("", encoding="utf-8")

    _, dit = lance("verify", str(vide), capsys=capsys)

    assert "has not started" in dit
    assert "gone" in dit


# ── And a real ledger still passes ──────────────────────────────────────

def test_the_shipped_ledger_still_verifies(capsys):
    """The guard must not have turned into a refusal to work."""
    ledger = Path(__file__).resolve().parent.parent / "runs" / "escalation" / "ledger.jsonl"
    if not ledger.exists():
        pytest.skip("the shipped ledger is not in this checkout")

    code, dit = lance("verify", str(ledger), capsys=capsys)

    assert code == 0
    assert "the chain holds" in dit


def test_a_ledger_with_one_record_passes(tmp_path, capsys):
    from glassbox.evidence import EvidenceStore
    from glassbox.ledger import Ledger

    store = EvidenceStore(tmp_path / "evidence")
    led = Ledger(tmp_path / "ledger.jsonl", store=store)
    led.append(name="something", started_at="2026-10-14T09:31:07Z",
               agent_version="a1b2c3d", outcome={"action": "none"})

    code, dit = lance("verify", str(tmp_path / "ledger.jsonl"), capsys=capsys)

    assert code == 0
    assert "1 decision(s)" in dit
