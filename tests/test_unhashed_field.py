"""A field the chain does not cover must not pass for a record that holds.

The chain hashes an allowlist — the nine keys of `_BODY_KEYS`, and only those
actually present, so that adding an optional field left every ledger already on
disk exactly where it was. That choice is right and it has a hole: a key outside
the list is hashed by nothing at all.

Found by walking the product rather than by reading it. Appending
`"severity": "benign"` to a sealed record left `verify` saying the chain holds,
and 179 tests agreed with it, because every one of them mutated a field the
chain already knew about. The gate could only ever fail in the direction it was
built to fail in.

What a record carrying an unhashed field means is the whole question. It is not
proof of tampering: a newer writer may simply know a field this reader does not.
But it is not nothing either, because the two are indistinguishable from here —
and a verifier that cannot account for part of a record has no business calling
that record intact. So it is reported, by name, and `verify` exits non-zero.
"""

from __future__ import annotations

import json

from glassbox.ledger import _BODY_KEYS, _STRUCTURAL_KEYS, Ledger


def a_ledger(tmp_path, decisions=2):
    led = Ledger(tmp_path / "ledger.jsonl")
    for index in range(decisions):
        led.append(
            name=f"decision-{index}",
            started_at="2026-10-14T09:31:07Z",
            agent_version="a1b2c3d",
            evidence=(),
            model_calls=({"tier": "nano", "cost_usd": 0.0002},),
            actions=(),
            outcome={"action": "write-file", "reason": "done"},
        )
    return led


def smuggle(led, position, **champs):
    """Write `champs` into the record at `position` without touching its chain."""
    chemin = led.path
    lignes = chemin.read_text(encoding="utf-8").splitlines()
    raw = json.loads(lignes[position - 1])
    raw.update(champs)
    lignes[position - 1] = json.dumps(raw)
    chemin.write_text("\n".join(lignes) + "\n", encoding="utf-8")


def test_a_clean_ledger_reports_nothing(tmp_path):
    assert a_ledger(tmp_path).verify() == []


def test_a_field_no_hash_covers_is_reported(tmp_path):
    led = a_ledger(tmp_path)
    smuggle(led, 2, severity="benign")

    problems = led.verify()
    assert len(problems) == 1, problems
    assert "record 2" in problems[0]


def test_it_names_every_smuggled_field(tmp_path):
    """One of two named would be worse than none: it would read as the whole list."""
    led = a_ledger(tmp_path)
    smuggle(led, 1, note="approved by management", severity="benign")

    problems = led.verify()
    assert problems, "neither smuggled field was reported"
    assert "note" in problems[0]
    assert "severity" in problems[0]


def test_it_does_not_read_as_an_edit(tmp_path):
    """The two findings call for different actions, so they must not share wording.

    An edited record means someone rewrote history. An unhashed field may only
    mean a newer writer. Telling a reader the wrong one sends them after the
    wrong thing.
    """
    edited = a_ledger(tmp_path / "a")
    smuggle(edited, 2, outcome={"action": "nothing", "reason": "rewritten"})

    smuggled = a_ledger(tmp_path / "b")
    smuggle(smuggled, 2, severity="benign")

    sur_le_champ = smuggled.verify()
    assert sur_le_champ, "the smuggled field was not reported at all"
    assert "has been edited" in edited.verify()[0]
    assert "has been edited" not in sur_le_champ[0]


def test_the_chain_s_own_keys_are_never_reported(tmp_path):
    """`prev` and `chain` sit outside the allowlist by construction.

    Mutating one is caught by the chain check, as it always was — but neither
    may ever be named as a smuggled field, or every ledger on disk reports two.
    """
    led = a_ledger(tmp_path)
    assert led.verify() == []

    for key in _STRUCTURAL_KEYS:
        assert key not in _BODY_KEYS


def test_every_hashed_field_still_breaks_the_chain_when_changed(tmp_path):
    """The new check must not quietly take over for the old one.

    Each of the nine is rewritten in turn, and each must report an edit — not an
    unhashed field, which would mean the allowlist had lost a name.
    """
    valeurs = {
        "name": "something-else",
        "started_at": "2026-01-01T00:00:00Z",
        "agent_version": "deadbeef",
        "evidence": ["sha256:0000"],
        "asks": 99,
        "model_calls": [{"tier": "ultra", "cost_usd": 9.99}],
        "actions": [{"kind": "read-file", "target": "/etc/shadow"}],
        "outcome": {"action": "nothing", "reason": "rewritten"},
        "rule_digest": "sha256:0000",
    }
    assert set(valeurs) == set(_BODY_KEYS), "the allowlist changed; update this test"

    for champ, valeur in valeurs.items():
        led = a_ledger(tmp_path / champ)
        smuggle(led, 2, **{champ: valeur})
        problems = led.verify()
        assert problems, f"{champ} was rewritten and nothing said so"
        assert "has been edited" in problems[0], f"{champ}: {problems[0]}"
