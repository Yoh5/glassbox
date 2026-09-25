"""Nemotron on Nebius Token Factory, priced from what the API says it used.

Three tiers, three public endpoints, and a factor of twelve between the cheapest
and the dearest on output. That spread is what makes the escalation measurement
worth making: if the cheap tier answers the same thing most of the time, the
saving is real money, and if it does not, the record says so.

Cost comes from the `usage` block the API returns, never from an estimate over
the prompt. An estimate that drifts turns the one number this project publishes
into decoration.
"""

from __future__ import annotations

import json as jsonlib
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, Mapping

DEFAULT_BASE_URL = "https://api.tokenfactory.nebius.com/v1"


@dataclass(frozen=True)
class Tier:
    model_id: str
    #: US dollars per million tokens, as published on the model's page.
    usd_in_per_m: float
    usd_out_per_m: float


#: Only the models with a *public* endpoint. The others (Llama-3_1-Nemotron-Ultra,
#: Nano-Omni, Nano-V2-12b) need a dedicated deployment, which is a different
#: project with a different bill.
#: The ids are the ones `GET /v1/models` returns, not the ones the product
#: pages display: two of the three differ in case or carry an extra prefix, and
#: a wrong id is a 404 at the worst possible moment.
TIERS: dict[str, Tier] = {
    "nano": Tier("nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B", 0.06, 0.24),
    "super": Tier("nvidia/nemotron-3-super-120b-a12b", 0.30, 0.90),
    "ultra": Tier("nvidia/Nemotron-3-Ultra-550b-a55b", 1.00, 3.00),
}

PostFn = Callable[..., Mapping[str, Any]]


def _urllib_post(url: str, *, headers: Mapping[str, str], json: Mapping[str, Any]) -> Mapping[str, Any]:
    request = urllib.request.Request(
        url,
        data=jsonlib.dumps(json).encode("utf-8"),
        headers={**headers, "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=120) as response:  # noqa: S310 - our own URL
        return jsonlib.loads(response.read().decode("utf-8"))


def nebius_call(
    *,
    api_key: str,
    base_url: str = DEFAULT_BASE_URL,
    tiers: Mapping[str, Tier] = TIERS,
    post: PostFn | None = None,
    temperature: float = 0.7,
    max_tokens: int = 512,
) -> Callable[[str, str], tuple[str, float]]:
    """Builds the `(tier, prompt) -> (answer, cost)` function the Router calls.

    `temperature` must be above zero. The router escalates when two samples of
    the cheap tier disagree; at temperature zero they never disagree, the
    escalation never fires, and a check that cannot fail proves nothing. The
    library refuses the setting rather than reporting a perfect agreement rate
    that means nothing.
    """
    if temperature <= 0:
        raise ValueError(
            "temperature must be above zero: the router's escalation signal is two samples "
            "disagreeing, and at zero they never will"
        )
    send = post or _urllib_post

    def call(tier: str, prompt: str) -> tuple[str, float]:
        if tier not in tiers:
            raise KeyError(f"unknown tier {tier!r}; known tiers are {', '.join(tiers)}")
        model = tiers[tier]

        body = send(
            f"{base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": model.model_id,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
        )

        # Nemotron 3 reasons before it answers. When `max_tokens` runs out
        # inside the thinking, the API returns `content: null` -- and a crash
        # there would take a fourteen-day run down over one truncated answer.
        message = body["choices"][0]["message"]
        text = (message.get("content") or message.get("reasoning_content") or "").strip()
        usage = body.get("usage") or {}
        cost = (
            usage.get("prompt_tokens", 0) / 1_000_000 * model.usd_in_per_m
            + usage.get("completion_tokens", 0) / 1_000_000 * model.usd_out_per_m
        )
        return text, cost

    return call


def list_models(api_key: str, base_url: str = DEFAULT_BASE_URL) -> list[str]:
    """Every model id the account can call. Used to confirm the ids above."""
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/models",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310 - our own URL
        return [entry["id"] for entry in jsonlib.loads(response.read().decode("utf-8"))["data"]]
