"""The façade: the three lines someone actually writes.

A library nobody wants to call will not be called, and a recorder that people
have to remember to feed will be fed selectively — which is worse than not
recording at all, because it looks complete.
"""

import pytest

from glassbox.recorder import Recorder
from glassbox.router import Router


def scripted(answers):
    def call(tier, prompt):
        return answers[tier], {"nano": 0.0001, "super": 0.0010, "ultra": 0.01}[tier]

    return call


def recorder(tmp_path, secrets=(), router=None):
    ticks = iter([f"2026-10-14T09:31:{second:02d}Z" for second in range(0, 60)])
    return Recorder(
        tmp_path,
        agent_version="a1b2c3d",
        secrets=secrets,
        router=router,
        clock=lambda: next(ticks),
    )


def test_one_block_writes_exactly_one_record(tmp_path):
    rec = recorder(tmp_path)

    with rec.decision("summarise-page"):
        pass

    assert len(rec.ledger.records()) == 1
    assert rec.ledger.records()[0].name == "summarise-page"


def test_evidence_read_inside_the_block_is_cited_by_the_record(tmp_path):
    rec = recorder(tmp_path)

    with rec.decision("summarise-page") as d:
        item = d.evidence(source="https://example.org", payload=b"<html>hi</html>")

    assert rec.ledger.records()[0].evidence == (item.id,)


def test_the_agent_never_has_to_name_the_time(tmp_path):
    rec = recorder(tmp_path)

    with rec.decision("summarise-page") as d:
        d.evidence(source="https://example.org", payload=b"x")

    assert rec.ledger.records()[0].started_at.startswith("2026-10-14T09:31:")


def test_actions_taken_inside_the_block_are_recorded(tmp_path):
    rec = recorder(tmp_path)

    with rec.decision("summarise-page") as d:
        d.act("read-file", target="~/.ssh/id_rsa")

    assert rec.ledger.records()[0].actions == ({"kind": "read-file", "target": "~/.ssh/id_rsa"},)


def test_a_model_call_carries_its_tier_and_cost_into_the_record(tmp_path):
    rec = recorder(tmp_path, router=Router(scripted({"nano": "blue"})))

    with rec.decision("ask-colour") as d:
        assert d.ask("what colour").text == "blue"

    call = rec.ledger.records()[0].model_calls[0]
    assert call["tier"] == "nano"
    assert call["cost_usd"] == pytest.approx(0.0001)


def test_asking_without_a_router_is_refused_rather_than_silently_skipped(tmp_path):
    rec = recorder(tmp_path)

    with pytest.raises(ValueError, match="router"):
        with rec.decision("ask-colour") as d:
            d.ask("what colour")


def test_a_decision_that_raises_is_still_recorded_then_re_raised(tmp_path):
    rec = recorder(tmp_path)

    with pytest.raises(RuntimeError, match="upstream died"):
        with rec.decision("summarise-page") as d:
            d.evidence(source="https://example.org", payload=b"x")
            raise RuntimeError("upstream died")

    record = rec.ledger.records()[0]
    assert record.outcome["action"] == "failed"
    assert "upstream died" in record.outcome["reason"]


def test_a_decision_that_does_nothing_records_that_it_did_nothing(tmp_path):
    # A ledger that only fills up when the agent acts cannot explain a quiet
    # afternoon, so a block with no action is a record like any other.
    rec = recorder(tmp_path)

    with rec.decision("check-inbox") as d:
        d.refuse("nothing worth acting on")

    record = rec.ledger.records()[0]
    assert record.outcome == {"action": "none", "reason": "nothing worth acting on"}


def test_secrets_never_reach_the_ledger_even_through_a_reason(tmp_path):
    rec = recorder(tmp_path, secrets=["sk-live-9f3a"])

    with rec.decision("summarise-page") as d:
        d.refuse("refused after sk-live-9f3a failed")

    assert "sk-live-9f3a" not in rec.ledger.path.read_text(encoding="utf-8")


def test_the_records_chain_across_blocks(tmp_path):
    rec = recorder(tmp_path)

    with rec.decision("one"):
        pass
    with rec.decision("two"):
        pass

    assert rec.verify() == []
    assert rec.ledger.records()[1].prev == rec.ledger.records()[0].chain


def test_a_block_inside_a_block_is_refused_rather_than_producing_a_muddle(tmp_path):
    rec = recorder(tmp_path)

    with pytest.raises(RuntimeError, match="already"):
        with rec.decision("outer"):
            with rec.decision("inner"):
                pass
