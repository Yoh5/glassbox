"""Which rule decided this, and is it the one I am replaying with?

`replay` compares a recorded decision to whatever function the caller points
at. Until now it had no way of saying "that is not the rule that ran": an
edited rule produced a decision mismatch, which reads as *the agent was
wrong* when the truth is *you replayed with the wrong code*. Those are
opposite findings and an auditor must not have to guess which one they are
looking at.

The lesson comes from Yoh5/runway, where a run record stamps the digest of
the policy it decided under, and the verifier refuses to check a record
against a policy that has since been edited.
"""

import pytest

from glassbox.evidence import EvidenceStore
from glassbox.ledger import Ledger
from glassbox.recorder import Recorder
from glassbox.rule import rule_digest


def under_ten(evidence):
    price = int(evidence[0].payload.decode().split("=")[1])
    return ({"action": "buy", "reason": "cheap enough"} if price < 100
            else {"action": "none", "reason": "too expensive"})


def under_ten_reworded(evidence):
    # Same answers, different code. The digest is over the text of the rule,
    # so this is a different rule -- and saying so is the point.
    price = int(evidence[0].payload.decode().split("=")[1])
    if price < 100:
        return {"action": "buy", "reason": "cheap enough"}
    return {"action": "none", "reason": "too expensive"}


def build(tmp_path, *, rule=None):
    store = EvidenceStore(tmp_path / "evidence")
    led = Ledger(tmp_path / "ledger.jsonl", store=store)
    cheap = store.put(source="https://example.org/a", payload=b"price=10",
                      fetched_at="2026-10-14T09:30:00Z")
    led.append(name="buy?", started_at="2026-10-14T09:30:05Z", agent_version="v1",
               evidence=(cheap.id,), outcome={"action": "buy", "reason": "cheap enough"},
               rule_digest=rule_digest(rule) if rule else None)
    return led


def test_a_digest_is_stable_and_specific():
    assert rule_digest(under_ten) == rule_digest(under_ten)
    assert rule_digest(under_ten) != rule_digest(under_ten_reworded)
    assert rule_digest(under_ten).startswith("sha256:")


def test_indentation_does_not_change_a_rule(tmp_path):
    """The same function nested inside another is the same rule, not a new one.

    Its name is part of its source, though: a renamed rule is a different
    rule, which is the safe direction for a digest to err in.
    """

    def under_ten(evidence):
        price = int(evidence[0].payload.decode().split("=")[1])
        return ({"action": "buy", "reason": "cheap enough"} if price < 100
                else {"action": "none", "reason": "too expensive"})

    assert rule_digest(under_ten) == rule_digest(globals()["under_ten"])


def test_a_rule_whose_source_cannot_be_read_says_so():
    with pytest.raises(ValueError, match="source"):
        rule_digest(len)


def test_replaying_with_the_recorded_rule_confirms_it(tmp_path):
    led = build(tmp_path, rule=under_ten)
    result = led.replay(1, under_ten)

    assert result.matched is True
    assert result.same_rule is True
    assert "assumed rule" not in result.detail


def test_replaying_with_a_different_rule_says_so_instead_of_blaming_the_agent(tmp_path):
    led = build(tmp_path, rule=under_ten)
    result = led.replay(1, under_ten_reworded)

    # The answer is identical, so the decision reproduces. What changed is the
    # code, and the reader is told exactly that rather than nothing.
    assert result.matched is True
    assert result.same_rule is False
    assert "not the rule that ran" in result.detail


def test_a_mismatch_under_a_different_rule_names_both_facts(tmp_path):
    led = build(tmp_path, rule=under_ten)

    def never_buy(evidence):
        return {"action": "none", "reason": "too expensive"}

    result = led.replay(1, never_buy)
    assert result.matched is False
    assert result.same_rule is False
    assert "not the rule that ran" in result.detail
    assert "recorded" in result.detail


def test_a_record_with_no_rule_is_replayed_against_an_assumed_one(tmp_path):
    led = build(tmp_path)  # no rule recorded, as every record written before this
    result = led.replay(1, under_ten)

    assert result.matched is True
    assert result.same_rule is None
    assert "assumed rule" in result.detail


def test_records_written_before_the_field_existed_still_verify(tmp_path):
    """The chain must not move under records that predate the new field."""
    led = build(tmp_path)          # written without rule_digest
    assert led.verify() == []

    led.append(name="buy?", started_at="2026-10-14T09:32:05Z", agent_version="v1",
               outcome={"action": "none", "reason": "quiet"},
               rule_digest=rule_digest(under_ten))
    assert led.verify() == []
    assert led.records()[0].rule_digest is None
    assert led.records()[1].rule_digest == rule_digest(under_ten)


def test_the_recorder_stamps_the_rule_it_was_given(tmp_path):
    rec = Recorder(tmp_path, agent_version="v1", rule=under_ten)
    with rec.decision("buy?") as d:
        d.outcome(action="none", reason="quiet")

    assert rec.ledger.records()[0].rule_digest == rule_digest(under_ten)
    assert rec.verify() == []


def test_the_recorder_without_a_rule_stamps_nothing(tmp_path):
    rec = Recorder(tmp_path, agent_version="v1")
    with rec.decision("buy?") as d:
        d.outcome(action="none", reason="quiet")

    assert rec.ledger.records()[0].rule_digest is None
