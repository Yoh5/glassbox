"""Replay: would it decide the same thing again, on the same evidence?

The third question, and the one that separates a bug from a coin flip. It only
means something for a decision function that is deterministic — which is
exactly why the library pushes people to keep one, and says so rather than
pretending a replay through a language model proves anything.
"""

import pytest

from glassbox.evidence import EvidenceStore
from glassbox.ledger import Ledger


def build(tmp_path):
    store = EvidenceStore(tmp_path / "evidence")
    led = Ledger(tmp_path / "ledger.jsonl", store=store)
    cheap = store.put(source="https://example.org/a", payload=b"price=10",
                      fetched_at="2026-10-14T09:30:00Z")
    dear = store.put(source="https://example.org/b", payload=b"price=900",
                     fetched_at="2026-10-14T09:31:00Z")
    led.append(name="buy?", started_at="2026-10-14T09:30:05Z", agent_version="v1",
               evidence=(cheap.id,), outcome={"action": "buy", "reason": "cheap enough"})
    led.append(name="buy?", started_at="2026-10-14T09:31:05Z", agent_version="v1",
               evidence=(dear.id,), outcome={"action": "none", "reason": "too expensive"})
    return led


def under_ten(evidence):
    price = int(evidence[0].payload.decode().split("=")[1])
    return ({"action": "buy", "reason": "cheap enough"} if price < 100
            else {"action": "none", "reason": "too expensive"})


def always_buy(evidence):
    return {"action": "buy", "reason": "cheap enough"}


def test_the_same_rule_on_the_same_evidence_reproduces_the_decision(tmp_path):
    led = build(tmp_path)

    assert led.replay(1, under_ten).matched is True
    assert led.replay(2, under_ten).matched is True


def test_a_rule_that_has_changed_since_shows_up_as_a_mismatch(tmp_path):
    led = build(tmp_path)

    result = led.replay(2, always_buy)

    assert result.matched is False
    assert result.recorded["action"] == "none"
    assert result.recomputed["action"] == "buy"


def test_the_mismatch_says_what_differs_rather_than_merely_that_it_does(tmp_path):
    led = build(tmp_path)

    assert "none" in led.replay(2, always_buy).detail
    assert "buy" in led.replay(2, always_buy).detail


def test_the_rule_is_handed_the_evidence_in_the_order_the_decision_cited_it(tmp_path):
    led = build(tmp_path)
    seen = []

    def remember(evidence):
        seen.append([item.source for item in evidence])
        return {"action": "buy", "reason": "cheap enough"}

    led.replay(1, remember)

    assert seen == [["https://example.org/a"]]


def test_replaying_the_whole_ledger_reports_one_verdict_per_record(tmp_path):
    led = build(tmp_path)

    results = led.replay_all(under_ten)

    assert [r.position for r in results] == [1, 2]
    assert all(r.matched for r in results)


def test_a_rule_that_raises_is_a_mismatch_and_not_a_crash(tmp_path):
    # A replay is an inspection. It must be able to report "this no longer even
    # runs" without taking the inspection down with it.
    led = build(tmp_path)

    def broken(evidence):
        raise ZeroDivisionError("nope")

    result = led.replay(1, broken)

    assert result.matched is False
    assert "ZeroDivisionError" in result.detail


def test_replaying_without_the_evidence_store_is_refused(tmp_path):
    led = Ledger(tmp_path / "ledger.jsonl")
    led.append(name="x", started_at="2026-10-14T09:31:07Z", agent_version="v")

    with pytest.raises(ValueError, match="evidence store"):
        led.replay(1, under_ten)
