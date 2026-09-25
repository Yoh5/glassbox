"""The ledger: one record per decision, each chained to the one before it.

A log anyone can edit afterwards is a testimony. Chaining makes an edit, a
deletion and an insertion equally visible, which is what turns the journal into
a proof. The cost is that nothing can ever be scrubbed — which is exactly why
redaction happens at the boundary, before anything is written.

One record per decision, and one per refusal. A ledger that only fills up when
the agent acts cannot explain a quiet afternoon.
"""

from __future__ import annotations

import hashlib
import json
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from .evidence import EvidenceStore, UnknownEvidence


@dataclass(frozen=True)
class Explained:
    """A decision with its evidence resolved — the answer to "why did it do that".

    The evidence is returned whole, payload included: after an incident the
    question is not which ids were cited but what those bytes said.
    """

    decision: "Decision"
    position: int
    evidence: tuple[Any, ...]


@dataclass(frozen=True)
class Replay:
    """Whether a decision would be taken again, on the evidence it was taken from.

    Only meaningful for a deterministic decision function. A rule that calls a
    model on the way through will disagree with itself for reasons that have
    nothing to do with the record, and a replay that cannot fail proves
    nothing — which is the argument for keeping the deciding part of an agent
    free of model calls in the first place.
    """

    position: int
    name: str
    matched: bool
    recorded: Mapping[str, Any]
    recomputed: Mapping[str, Any] | None
    detail: str


@dataclass(frozen=True)
class Decision:
    name: str
    started_at: str
    agent_version: str
    evidence: tuple[str, ...]
    #: One entry per question put to a model: which tier answered, whether it
    #: was escalated to, and whether escalating changed the answer. The raw
    #: calls stay in `model_calls`; this is the level someone adds up later.
    asks: tuple[Mapping[str, Any], ...]
    model_calls: tuple[Mapping[str, Any], ...]
    actions: tuple[Mapping[str, Any], ...]
    outcome: Mapping[str, Any]
    prev: str | None
    chain: str = field(compare=False)


def _canonical(body: Mapping[str, Any]) -> str:
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _chain_hash(body: Mapping[str, Any], prev: str | None) -> str:
    material = (prev or "") + _canonical(body)
    return "sha256:" + hashlib.sha256(material.encode("utf-8")).hexdigest()


class Ledger:
    """Append-only JSON Lines, one decision per line.

    JSON Lines rather than a database on purpose: an auditor with no tooling
    can read it, `tail` it while a run is in progress, and diff two copies.

    Appending is safe from several threads. It is NOT safe from several
    processes writing the same file: the lock lives in this interpreter, and
    two processes would need a file lock. One ledger per process.
    """

    def __init__(self, path: str | Path, store: EvidenceStore | None = None) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._store = store
        # Reading the last chain and writing the next record must not be
        # separable: two threads doing it at once produce two records pointing
        # at the same predecessor, and the chain breaks. Found by wiring this
        # library onto an agent whose deep-dive runs on four threads.
        self._lock = threading.Lock()

    def append(
        self,
        *,
        name: str,
        started_at: str,
        agent_version: str,
        evidence: Sequence[str] = (),
        asks: Sequence[Mapping[str, Any]] = (),
        model_calls: Sequence[Mapping[str, Any]] = (),
        actions: Sequence[Mapping[str, Any]] = (),
        outcome: Mapping[str, Any] | None = None,
    ) -> Decision:
        body = {
            "name": name,
            "started_at": started_at,
            "agent_version": agent_version,
            "evidence": list(evidence),
            "asks": [dict(a) for a in asks],
            "model_calls": [dict(c) for c in model_calls],
            "actions": [dict(a) for a in actions],
            "outcome": dict(outcome or {}),
        }
        with self._lock:
            prev = self._last_chain()
            chain = _chain_hash(body, prev)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(_canonical({**body, "prev": prev, "chain": chain}) + "\n")

        return Decision(
            name=name,
            started_at=started_at,
            agent_version=agent_version,
            evidence=tuple(evidence),
            asks=tuple(dict(a) for a in asks),
            model_calls=tuple(dict(c) for c in model_calls),
            actions=tuple(dict(a) for a in actions),
            outcome=dict(outcome or {}),
            prev=prev,
            chain=chain,
        )

    def records(self) -> list[Decision]:
        return [self._revive(json.loads(line)) for line in self._lines()]

    def verify(self) -> list[str]:
        """Re-chains the whole file and resolves every citation.

        Reports the position of the first record that does not hold, counting
        from one, because "something is wrong somewhere" is not a finding.
        """
        problems: list[str] = []
        prev: str | None = None

        for position, line in enumerate(self._lines(), start=1):
            raw = json.loads(line)
            body = {key: raw[key] for key in
                    ("name", "started_at", "agent_version", "evidence", "asks",
                     "model_calls", "actions", "outcome")}

            if raw.get("prev") != prev:
                problems.append(
                    f"record {position} ({raw['name']}) does not follow the one before it: "
                    "a record was edited, deleted or inserted"
                )
            elif _chain_hash(body, prev) != raw.get("chain"):
                problems.append(
                    f"record {position} ({raw['name']}) has been edited since it was written"
                )

            prev = raw.get("chain")

            if self._store is not None:
                for evidence_id in raw["evidence"]:
                    try:
                        self._store.get(evidence_id)
                    except UnknownEvidence:
                        problems.append(
                            f"record {position} ({raw['name']}) cites evidence "
                            f"{evidence_id[:19]}... which the store does not have"
                        )

        return problems

    def explain(self, position: int) -> Explained:
        """The decision at `position` (counting from one) with its evidence read back."""
        if self._store is None:
            raise ValueError(
                "explaining a decision needs the evidence store it cited: "
                "construct the Ledger with store=EvidenceStore(...)"
            )
        records = self.records()
        if not 1 <= position <= len(records):
            raise IndexError(f"no record at position {position}; the ledger holds {len(records)}")
        decision = records[position - 1]
        return Explained(
            decision=decision,
            position=position,
            evidence=tuple(self._store.get(i) for i in decision.evidence),
        )

    def replay(self, position: int, decide: Callable[[Sequence[Any]], Mapping[str, Any]]) -> Replay:
        """Re-runs `decide` over the evidence the decision cited, and compares.

        A rule that raises is a mismatch, not a crash: a replay is an
        inspection, and "this no longer even runs" is a finding worth
        reporting rather than an error worth propagating.
        """
        explained = self.explain(position)
        recorded = dict(explained.decision.outcome)

        try:
            recomputed = dict(decide(explained.evidence))
        except Exception as error:  # noqa: BLE001 - the point is to report it
            return Replay(
                position=position,
                name=explained.decision.name,
                matched=False,
                recorded=recorded,
                recomputed=None,
                detail=f"the rule no longer runs on this evidence: "
                       f"{type(error).__name__}: {error}",
            )

        matched = _canonical(recomputed) == _canonical(recorded)
        return Replay(
            position=position,
            name=explained.decision.name,
            matched=matched,
            recorded=recorded,
            recomputed=recomputed,
            detail=(
                "the rule reproduces the recorded decision"
                if matched
                else f"recorded {_canonical(recorded)}, recomputed {_canonical(recomputed)}"
            ),
        )

    def replay_all(self, decide: Callable[[Sequence[Any]], Mapping[str, Any]]) -> list[Replay]:
        return [self.replay(position, decide) for position in range(1, len(self.records()) + 1)]

    def trace_action(self, kind: str) -> list[Explained]:
        """Every decision that took an action of this kind, evidence included.

        This is the incident path: start from the thing that should not have
        happened, end at the input that caused it.
        """
        return [
            self.explain(position)
            for position, record in enumerate(self.records(), start=1)
            if any(action.get("kind") == kind for action in record.actions)
        ]

    def stats(self) -> dict[str, Any]:
        """What the run cost, and what the expensive tier actually bought.

        Added up from the record rather than reported at the time, so someone
        who was not there can check the number instead of believing it.
        """
        calls_by_tier: dict[str, int] = {}
        cost = 0.0
        asks = escalated = changed = 0

        for record in self.records():
            for call in record.model_calls:
                tier = str(call["tier"])
                calls_by_tier[tier] = calls_by_tier.get(tier, 0) + 1
                cost += float(call.get("cost_usd", 0.0))
            for ask in record.asks:
                asks += 1
                if ask.get("escalated_from"):
                    escalated += 1
                    if ask.get("changed_on_escalation"):
                        changed += 1

        return {
            "decisions": len(self.records()),
            "asks": asks,
            "escalated": escalated,
            "changed_on_escalation": changed,
            # None, not zero: "the expensive tier never changed anything" and
            # "we never had to ask it" are different claims.
            "changed_share": (changed / escalated) if escalated else None,
            "calls_by_tier": calls_by_tier,
            "cost_usd": cost,
        }

    def _lines(self) -> list[str]:
        if not self.path.exists():
            return []
        return [line for line in self.path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def _last_chain(self) -> str | None:
        lines = self._lines()
        return json.loads(lines[-1])["chain"] if lines else None

    @staticmethod
    def _revive(raw: Mapping[str, Any]) -> Decision:
        return Decision(
            name=raw["name"],
            started_at=raw["started_at"],
            agent_version=raw["agent_version"],
            evidence=tuple(raw["evidence"]),
            asks=tuple(raw.get("asks", ())),
            model_calls=tuple(raw["model_calls"]),
            actions=tuple(raw["actions"]),
            outcome=raw["outcome"],
            prev=raw["prev"],
            chain=raw["chain"],
        )
