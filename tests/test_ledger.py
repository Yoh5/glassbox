"""The ledger: decisions, chained, so the journal is a proof rather than a story.

A log anyone can edit afterwards is a testimony. Chaining each record to the
one before it makes an edit, a deletion and an insertion all equally visible,
which is the difference between "here is what we logged" and "here is what
happened".
"""

from glassbox.evidence import EvidenceStore
from glassbox.ledger import Ledger


def ledger(tmp_path, store=None):
    return Ledger(tmp_path / "ledger.jsonl", store=store)


def a_decision(led, name="summarise-page", evidence=(), actions=()):
    return led.append(
        name=name,
        started_at="2026-10-14T09:31:07Z",
        agent_version="a1b2c3d",
        evidence=evidence,
        model_calls=({"tier": "nano", "cost_usd": 0.0002},),
        actions=actions,
        outcome={"action": "write-file", "reason": "summary ready"},
    )


def test_the_first_record_chains_to_nothing(tmp_path):
    first = a_decision(ledger(tmp_path))
    assert first.prev is None
    assert first.chain


def test_each_record_chains_to_the_one_before(tmp_path):
    led = ledger(tmp_path)
    first = a_decision(led)
    second = a_decision(led, name="fetch-page")

    assert second.prev == first.chain


def test_the_same_content_always_chains_to_the_same_hash(tmp_path):
    a = a_decision(ledger(tmp_path / "a"))
    b = a_decision(ledger(tmp_path / "b"))
    assert a.chain == b.chain


def test_a_different_decision_gets_a_different_hash(tmp_path):
    a = a_decision(ledger(tmp_path / "a"))
    b = a_decision(ledger(tmp_path / "b"), name="something-else")
    assert a.chain != b.chain


def test_an_untouched_ledger_verifies_clean(tmp_path):
    led = ledger(tmp_path)
    a_decision(led)
    a_decision(led, name="fetch-page")

    assert led.verify() == []


def test_an_edited_decision_is_caught_and_located(tmp_path):
    led = ledger(tmp_path)
    a_decision(led)
    a_decision(led, name="fetch-page")

    path = tmp_path / "ledger.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    lines[0] = lines[0].replace("summarise-page", "innocent-lookup")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    problems = led.verify()
    assert problems
    assert "1" in problems[0]


def test_a_deleted_record_breaks_the_chain(tmp_path):
    led = ledger(tmp_path)
    a_decision(led)
    a_decision(led, name="fetch-page")
    a_decision(led, name="write-notes")

    path = tmp_path / "ledger.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    path.write_text(lines[0] + "\n" + lines[2] + "\n", encoding="utf-8")

    assert led.verify()


def test_reading_back_gives_the_records_in_the_order_they_happened(tmp_path):
    led = ledger(tmp_path)
    a_decision(led)
    a_decision(led, name="fetch-page")

    assert [r.name for r in led.records()] == ["summarise-page", "fetch-page"]


def test_evidence_a_decision_cites_must_resolve_in_the_store(tmp_path):
    store = EvidenceStore(tmp_path / "evidence")
    led = ledger(tmp_path, store=store)
    a_decision(led, evidence=("sha256:" + "0" * 64,))

    problems = led.verify()
    assert any("evidence" in p for p in problems)


def test_a_decision_citing_real_evidence_verifies_clean(tmp_path):
    store = EvidenceStore(tmp_path / "evidence")
    item = store.put(source="https://example.org", payload=b"page", fetched_at="2026-10-14T09:30:00Z")
    led = ledger(tmp_path, store=store)
    a_decision(led, evidence=(item.id,))

    assert led.verify() == []


def test_an_action_that_cites_no_decision_evidence_is_still_recorded_and_visible(tmp_path):
    # Actions are recorded inside the decision that produced them, so an action
    # with no decision behind it cannot exist by construction. This pins that.
    led = ledger(tmp_path)
    decision = a_decision(led, actions=({"kind": "write-file", "target": "notes.md"},))

    assert led.records()[0].actions == decision.actions
    assert decision.actions[0]["target"] == "notes.md"
