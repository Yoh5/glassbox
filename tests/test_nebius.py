"""The Nebius Token Factory call function, tested without touching the network.

Cost is computed from the usage the API reports, not estimated from the prompt:
an estimate that drifts turns the one number this project publishes into
decoration.
"""

import pytest

from glassbox.nebius import TIERS, nebius_call


def fake_http(captured, answer="blue", prompt_tokens=100, completion_tokens=20, status=200):
    def post(url, *, headers, json):
        captured.append({"url": url, "headers": headers, "json": json})
        if status != 200:
            raise RuntimeError(f"http {status}")
        return {
            "choices": [{"message": {"content": answer}}],
            "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens},
        }

    return post


def test_sends_the_model_id_of_the_tier_it_was_asked_for():
    captured: list[dict] = []
    call = nebius_call(api_key="k", base_url="https://api.example/v1", post=fake_http(captured))

    call("super", "what colour")

    assert captured[0]["json"]["model"] == TIERS["super"].model_id
    assert captured[0]["url"].endswith("/chat/completions")


def test_authenticates_with_a_bearer_token():
    captured: list[dict] = []
    call = nebius_call(api_key="sk-secret", base_url="https://api.example/v1", post=fake_http(captured))

    call("nano", "hello")

    assert captured[0]["headers"]["Authorization"] == "Bearer sk-secret"


def test_costs_what_the_usage_says_it_costs():
    call = nebius_call(
        api_key="k",
        base_url="https://api.example/v1",
        post=fake_http([], prompt_tokens=1_000_000, completion_tokens=1_000_000),
    )

    _, cost = call("nano", "hello")

    # Nano: $0.06 in + $0.24 out, per million.
    assert cost == pytest.approx(0.30)


def test_each_tier_is_priced_with_its_own_numbers():
    captured: list[dict] = []
    call = nebius_call(
        api_key="k",
        base_url="https://api.example/v1",
        post=fake_http(captured, prompt_tokens=1_000_000, completion_tokens=0),
    )

    assert call("nano", "x")[1] == pytest.approx(0.06)
    assert call("super", "x")[1] == pytest.approx(0.30)
    assert call("ultra", "x")[1] == pytest.approx(1.00)


def test_returns_the_text_the_model_answered():
    call = nebius_call(api_key="k", base_url="https://api.example/v1",
                       post=fake_http([], answer="  blue  "))

    text, _ = call("nano", "what colour")

    assert text == "blue"


def test_samples_at_a_temperature_above_zero_or_the_whole_signal_dies():
    # The router escalates when two samples of the cheap tier disagree. At
    # temperature zero they never disagree, the signal is always "agreed", and
    # the escalation never fires -- a check that cannot fail proves nothing.
    captured: list[dict] = []
    call = nebius_call(api_key="k", base_url="https://api.example/v1", post=fake_http(captured))

    call("nano", "x")

    assert captured[0]["json"]["temperature"] > 0


def test_refuses_a_temperature_of_zero_rather_than_quietly_breaking_escalation():
    with pytest.raises(ValueError, match="temperature"):
        nebius_call(api_key="k", base_url="https://api.example/v1", post=fake_http([]), temperature=0)


def test_an_unknown_tier_is_refused_by_name():
    call = nebius_call(api_key="k", base_url="https://api.example/v1", post=fake_http([]))

    with pytest.raises(KeyError, match="mega"):
        call("mega", "x")


def test_a_missing_usage_block_costs_nothing_and_does_not_invent_a_number():
    def post(url, *, headers, json):
        return {"choices": [{"message": {"content": "blue"}}]}

    call = nebius_call(api_key="k", base_url="https://api.example/v1", post=post)

    assert call("nano", "x") == ("blue", 0.0)


def test_the_tier_ids_are_the_ones_the_api_serves_not_the_ones_the_page_shows():
    # Confirmed against GET /v1/models on 25 September 2026. Two of the three
    # differ from the product pages -- nano carries an extra NVIDIA- prefix and
    # super is lower-case -- and a wrong id is a 404 mid-run.
    assert TIERS["nano"].model_id == "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B"
    assert TIERS["super"].model_id == "nvidia/nemotron-3-super-120b-a12b"
    assert TIERS["ultra"].model_id == "nvidia/Nemotron-3-Ultra-550b-a55b"


def test_a_reasoning_model_that_spends_its_budget_thinking_does_not_crash_the_run():
    """Nemotron 3 reasons before it answers; a truncated thought returns
    content: null, and crashing there would take down a long run.

    This test used to assert `text == "let me think..."` -- the thinking
    returned as the answer -- against a fixture carrying `reasoning_content`.
    Probing the live API on 8 October 2026 showed the field is `reasoning`, so
    the fixture described a response the API does not produce, and the
    assertion pinned behaviour that was wrong anyway: a half-formed thought
    must not enter the ledger wearing the shape of a reply.

    The fixture now matches what the API returns, and the assertion is that the
    truncation is reported rather than disguised.
    """
    def post(url, *, headers, json):
        return {
            "choices": [{"message": {"content": None, "reasoning": "let me think..."},
                         "finish_reason": "length"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 24},
        }

    call = nebius_call(api_key="k", base_url="https://api.example/v1", post=post)
    text, cost = call("nano", "x")

    assert "let me think..." not in text, "the thinking is passed off as an answer"
    assert "no answer" in text and "finish_reason=length" in text
    assert cost > 0


def test_an_answer_with_neither_content_nor_reasoning_says_so_rather_than_nothing():
    """Was: returns the empty string. Changed deliberately on 8 October 2026.

    "No crash" was the right instinct and the wrong landing. An empty string is
    indistinguishable from a model that answered with nothing, and it travels
    into the ledger wearing the shape of a reply. The reply now names what
    happened, stays a string so nothing crashes, and cannot be read as an
    answer. See tests/test_truncated_reply.py for the rest of the contract.
    """
    def post(url, *, headers, json):
        return {"choices": [{"message": {"content": None}}], "usage": {}}

    texte, cout = nebius_call(api_key="k", base_url="https://api.example/v1", post=post)("nano", "x")
    assert "no answer" in texte
    assert cout == 0.0
