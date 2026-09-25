"""Cheap model first; escalate on a signal that means something.

Asking a model how confident it is produces a number that correlates with
fluency, not with correctness. Sampling the cheap tier twice and escalating
when the two answers disagree costs one extra cheap call, needs no trust in
the model's self-assessment, and is the cheapest honest signal available.

Everything the router does is recorded per call — tier, cost, the answer — so
the ledger can carry it and the viewer can add it up. The number that comes
out is the one nobody publishes: of the questions that were escalated, how
many actually got a different answer. If the big model confirms the small one
nine times out of ten, that is worth knowing, and it is worth publishing even
when it makes the expensive tier look unnecessary.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Sequence

CallFn = Callable[[str, str], tuple[str, float]]
"""(tier, prompt) -> (answer, cost in USD)."""

DEFAULT_TIERS = ("nano", "super", "ultra")


def default_normalise(text: str) -> str:
    """What counts as "the same answer" when two samples are compared.

    Case and trailing punctuation are not disagreements. Measured on a real
    run: "Yellow" and "yellow" escalated a question about the colour of a
    banana to a model that costs twelve times more, and confirmed the same
    answer. The comparison is normalised; the recorded answer never is.
    """
    return re.sub(r"[\s.!,;:]+$", "", text.strip().casefold())


@dataclass(frozen=True)
class Answer:
    text: str
    tier: str
    cost_usd: float
    calls: tuple[Mapping[str, Any], ...]
    escalated_from: str | None = None
    #: None when nothing was escalated — "unchanged" and "never asked" are
    #: different facts and must not collapse into the same zero.
    changed_on_escalation: bool | None = None
    #: True when even the top tier disagreed with itself and we took the first
    #: sample anyway, because there is nothing above it.
    unresolved: bool = False


@dataclass
class _Tally:
    asks: int = 0
    escalated: int = 0
    changed: int = 0
    cost_usd: float = 0.0
    calls_by_tier: dict[str, int] = field(default_factory=dict)


class Router:
    def __init__(
        self,
        call: CallFn,
        tiers: Sequence[str] = DEFAULT_TIERS,
        samples: int = 2,
        validate: Callable[[str], bool] | None = None,
        normalise: Callable[[str], str] = default_normalise,
    ) -> None:
        if samples < 2:
            raise ValueError("samples must be at least 2: one sample cannot disagree with itself")
        self._call = call
        self._tiers = tuple(tiers)
        self._samples = samples
        self._validate = validate
        self._normalise = normalise
        self._tally = _Tally()

    def ask(self, prompt: str, *, floor: str | None = None) -> Answer:
        start = self._tiers.index(floor) if floor else 0
        calls: list[Mapping[str, Any]] = []
        cost = 0.0
        previous: str | None = None
        previous_tier: str | None = None

        for index in range(start, len(self._tiers)):
            tier = self._tiers[index]
            answers: list[str] = []
            for _ in range(self._samples):
                text, call_cost = self._call(tier, prompt)
                answers.append(text)
                cost += call_cost
                calls.append({"tier": tier, "cost_usd": call_cost, "answer": text})

            agreed = len({self._normalise(a) for a in answers}) == 1
            accepted = answers[0]
            valid = self._validate(accepted) if self._validate else True
            last = index == len(self._tiers) - 1

            if (agreed and valid) or last:
                return self._record(
                    Answer(
                        text=accepted,
                        tier=tier,
                        cost_usd=cost,
                        calls=tuple(calls),
                        escalated_from=previous_tier,
                        changed_on_escalation=(
                            None
                            if previous is None
                            else self._normalise(accepted) != self._normalise(previous)
                        ),
                        unresolved=last and not (agreed and valid),
                    )
                )

            previous, previous_tier = accepted, tier

        raise AssertionError("unreachable: the last tier always returns")  # pragma: no cover

    def stats(self) -> dict[str, Any]:
        tally = self._tally
        return {
            "asks": tally.asks,
            "escalated": tally.escalated,
            "changed_on_escalation": tally.changed,
            # None, not zero: "the big model never changed anything" and "we
            # never had to ask it" are different claims.
            "changed_share": (tally.changed / tally.escalated) if tally.escalated else None,
            "calls_by_tier": dict(tally.calls_by_tier),
            "cost_usd": tally.cost_usd,
        }

    def _record(self, answer: Answer) -> Answer:
        self._tally.asks += 1
        self._tally.cost_usd += answer.cost_usd
        for call in answer.calls:
            tier = str(call["tier"])
            self._tally.calls_by_tier[tier] = self._tally.calls_by_tier.get(tier, 0) + 1
        if answer.escalated_from is not None:
            self._tally.escalated += 1
            if answer.changed_on_escalation:
                self._tally.changed += 1
        return answer
