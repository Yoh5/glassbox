"""The router: cheap model first, escalate on a deterministic signal.

Self-reported confidence is sand — a model asked how sure it is will tell you
what you want to hear. Sampling the cheap tier twice and escalating when the
two answers disagree costs one extra cheap call and means something.

The metric that comes out of it is the one nobody publishes: of the questions
that were escalated, how many actually got a different answer.
"""

import pytest

from glassbox.router import Router


def scripted(answers):
    """A model that returns the next scripted answer for each tier, with a cost."""
    costs = {"nano": 0.0001, "super": 0.0010, "ultra": 0.0100}
    calls = []

    def call(tier, prompt):
        queue = answers[tier]
        text = queue.pop(0) if isinstance(queue, list) else queue
        calls.append((tier, text))
        return text, costs[tier]

    call.calls = calls
    return call


def test_two_agreeing_cheap_samples_are_taken_at_face_value():
    router = Router(scripted({"nano": ["blue", "blue"]}))

    answer = router.ask("what colour")

    assert answer.text == "blue"
    assert answer.tier == "nano"
    assert answer.escalated_from is None


def test_two_disagreeing_cheap_samples_escalate():
    router = Router(scripted({"nano": ["blue", "green"], "super": ["blue", "blue"]}))

    answer = router.ask("what colour")

    assert answer.tier == "super"
    assert answer.escalated_from == "nano"


def test_an_escalation_records_whether_the_answer_actually_changed():
    router = Router(scripted({"nano": ["blue", "green"], "super": ["red", "red"]}))

    answer = router.ask("what colour")

    assert answer.changed_on_escalation is True


def test_an_escalation_that_confirms_the_cheap_answer_says_so():
    # The headline number: paying for the big model and getting the same thing.
    router = Router(scripted({"nano": ["blue", "green"], "super": ["blue", "blue"]}))

    answer = router.ask("what colour")

    assert answer.changed_on_escalation is False


def test_a_rejected_answer_escalates_even_when_the_cheap_samples_agree():
    router = Router(
        scripted({"nano": ["not json", "not json"], "super": ["{}", "{}"]}),
        validate=lambda text: text.startswith("{"),
    )

    assert router.ask("give me json").tier == "super"


def test_the_top_tier_is_accepted_even_when_it_disagrees_with_itself():
    router = Router(
        scripted({"nano": ["a", "b"], "super": ["c", "d"], "ultra": ["e", "f"]}),
    )

    answer = router.ask("hard one")

    assert answer.tier == "ultra"
    assert answer.text == "e"
    assert answer.unresolved is True


def test_starting_above_the_floor_skips_the_cheap_tier():
    call = scripted({"super": ["x", "x"]})
    router = Router(call)

    assert router.ask("expensive question", floor="super").tier == "super"
    assert all(tier == "super" for tier, _ in call.calls)


def test_every_underlying_call_is_recorded_for_the_ledger():
    router = Router(scripted({"nano": ["blue", "green"], "super": ["blue", "blue"]}))

    answer = router.ask("what colour")

    assert [c["tier"] for c in answer.calls] == ["nano", "nano", "super", "super"]
    assert answer.cost_usd == pytest.approx(0.0001 * 2 + 0.0010 * 2)


def test_the_stats_are_what_the_viewer_shows():
    router = Router(
        scripted(
            {
                "nano": ["blue", "blue", "blue", "green", "red", "red"],
                "super": ["blue", "blue", "orange", "orange"],
            }
        )
    )
    router.ask("one")    # agrees at nano
    router.ask("two")    # disagrees, super confirms blue -> unchanged
    router.ask("three")  # agrees at nano

    stats = router.stats()

    assert stats["asks"] == 3
    assert stats["escalated"] == 1
    assert stats["changed_on_escalation"] == 0
    assert stats["calls_by_tier"] == {"nano": 6, "super": 2}
    assert stats["cost_usd"] == pytest.approx(0.0001 * 6 + 0.0010 * 2)


def test_the_number_that_matters_is_a_share_not_a_count():
    router = Router(scripted({"nano": ["a", "b"], "super": ["z", "z"]}))
    router.ask("one")

    assert router.stats()["changed_share"] == 1.0


def test_no_escalation_means_no_share_to_report_rather_than_zero():
    # Reporting 0% "changed" when nothing was escalated would read as "the big
    # model never helps", which is a different claim entirely.
    router = Router(scripted({"nano": ["a", "a"]}))
    router.ask("one")

    assert router.stats()["changed_share"] is None


def test_capitalisation_is_not_a_disagreement():
    # Measured on a real run: "Yellow" and "yellow" escalated a question about
    # the colour of a banana, at twelve times the price, for nothing.
    router = Router(scripted({"nano": ["Yellow", "yellow"]}))

    answer = router.ask("what colour is a banana")

    assert answer.tier == "nano"
    assert answer.escalated_from is None


def test_surrounding_punctuation_is_not_a_disagreement_either():
    router = Router(scripted({"nano": ["yes.", "Yes"]}))

    assert router.ask("is 17 prime").escalated_from is None


def test_a_real_difference_still_escalates_after_normalising():
    router = Router(scripted({"nano": ["yes", "no"], "super": ["no", "no"]}))

    assert router.ask("is 1 prime").tier == "super"


def test_the_answer_kept_is_the_one_the_model_actually_wrote():
    # Normalising is for comparing, never for recording: the ledger must hold
    # what the model said, not our tidied version of it.
    router = Router(scripted({"nano": ["Yellow", "yellow"]}))

    assert router.ask("what colour").text == "Yellow"
