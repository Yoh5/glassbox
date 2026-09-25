"""What the run cost, and what the expensive tier actually bought.

The router knows this while it runs. The point of putting it in the ledger is
that someone who was not there can add it up afterwards, from the record,
without trusting a number we printed at the time.
"""

from glassbox.ledger import Ledger
from glassbox.recorder import Recorder
from glassbox.router import Router


def ledger_with(tmp_path, asks):
    led = Ledger(tmp_path / "ledger.jsonl")
    for index, ask in enumerate(asks):
        led.append(
            name=f"decision-{index}",
            started_at="2026-10-14T09:31:07Z",
            agent_version="v1",
            asks=(ask,),
            model_calls=tuple(
                {"tier": tier, "cost_usd": cost} for tier, cost in ask["calls"]
            ),
        )
    return led


def ask(tier, escalated_from=None, changed=None, calls=(("nano", 0.0001), ("nano", 0.0001))):
    return {
        "tier": tier,
        "escalated_from": escalated_from,
        "changed_on_escalation": changed,
        "calls": list(calls),
    }


def test_counts_the_calls_by_tier_and_adds_up_the_cost(tmp_path):
    led = ledger_with(tmp_path, [ask("nano"), ask("nano")])

    stats = led.stats()

    assert stats["calls_by_tier"] == {"nano": 4}
    assert round(stats["cost_usd"], 6) == 0.0004


def test_reports_how_often_the_cheap_tier_was_enough(tmp_path):
    led = ledger_with(
        tmp_path,
        [
            ask("nano"),
            ask("nano"),
            ask("super", escalated_from="nano", changed=True,
                calls=(("nano", 0.0001), ("nano", 0.0001), ("super", 0.001), ("super", 0.001))),
        ],
    )

    stats = led.stats()

    assert stats["asks"] == 3
    assert stats["escalated"] == 1


def test_reports_the_share_of_escalations_that_changed_the_answer(tmp_path):
    led = ledger_with(
        tmp_path,
        [
            ask("super", escalated_from="nano", changed=True),
            ask("super", escalated_from="nano", changed=False),
            ask("super", escalated_from="nano", changed=False),
        ],
    )

    assert led.stats()["changed_share"] == 1 / 3


def test_never_escalating_reports_no_share_rather_than_zero(tmp_path):
    led = ledger_with(tmp_path, [ask("nano"), ask("nano")])

    assert led.stats()["changed_share"] is None


def test_a_ledger_with_no_asks_still_answers(tmp_path):
    led = Ledger(tmp_path / "ledger.jsonl")
    led.append(name="no-model-here", started_at="2026-10-14T09:31:07Z", agent_version="v1")

    stats = led.stats()

    assert stats["asks"] == 0
    assert stats["cost_usd"] == 0.0
    assert stats["changed_share"] is None


def test_an_ask_edited_in_the_ledger_breaks_the_chain(tmp_path):
    # The cost figures are part of the record, not a note beside it.
    led = ledger_with(tmp_path, [ask("nano")])
    path = tmp_path / "ledger.jsonl"
    path.write_text(path.read_text(encoding="utf-8").replace("0.0001", "0.9999"), encoding="utf-8")

    assert led.verify()


def test_the_recorder_writes_the_ask_summary_by_itself(tmp_path):
    calls = {"nano": ["blue", "green"], "super": ["red", "red"]}

    def call(tier, prompt):
        return calls[tier].pop(0), {"nano": 0.0001, "super": 0.001}[tier]

    rec = Recorder(tmp_path, agent_version="v1", router=Router(call))

    with rec.decision("ask-colour") as d:
        d.ask("what colour")

    recorded = rec.ledger.records()[0].asks[0]
    assert recorded["tier"] == "super"
    assert recorded["escalated_from"] == "nano"
    assert recorded["changed_on_escalation"] is True
