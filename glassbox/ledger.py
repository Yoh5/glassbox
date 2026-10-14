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
from .rule import rule_digest


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
    #: True when the replayed rule is the one the decision was stamped with,
    #: False when it is demonstrably another, and None when the decision
    #: carries no rule at all. The three are different findings: "it decided
    #: this again", "that is not the code that ran", and "nobody recorded
    #: which code ran, so this was checked against an assumption".
    same_rule: bool | None = None


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
    #: Digest of the decision function, when the agent declared one. Optional
    #: because records written before the field existed do not have it, and
    #: inventing it for them would be a claim nobody can check.
    rule_digest: str | None = None


#: The fields of a record that are hashed into its chain. `rule_digest` is
#: optional: a record written before it existed does not carry the key at all,
#: and since only the keys actually present are hashed, adding the field left
#: every chain already on disk exactly where it was. A new field that
#: invalidated old records would be indistinguishable from tampering.
_BODY_KEYS = (
    "name",
    "started_at",
    "agent_version",
    "evidence",
    "asks",
    "model_calls",
    "actions",
    "outcome",
    "rule_digest",
)


#: The two keys that carry the chain itself. Everything a record may legally
#: hold is `_BODY_KEYS` plus these; anything else is a field no hash covers,
#: which `verify` reports rather than ignores.
_STRUCTURAL_KEYS = ("prev", "chain")

#: Without these a line is not a record, and `_revive` would raise KeyError on
#: it. `asks` and `rule_digest` are absent from ledgers written before they
#: existed, so they are not required.
_CLES_REQUISES = ("name", "started_at", "agent_version", "evidence",
                  "model_calls", "actions", "outcome", "prev", "chain")


def _analyser(numero: int, ligne: str) -> tuple[Mapping[str, Any] | None, str | None]:
    """Un line in, either a record or the reason it is not one. Never raises.

    This file is the one input an adversary is assumed to control — the whole
    point of the chain is that someone may have edited it. Yet every reader
    here used to call `json.loads` bare, so a single corrupt byte did not
    produce a verdict: it produced a `JSONDecodeError`. A tool whose claim is
    *it detects tampering* has to answer tampering with a finding, not a
    traceback. An auditor cannot tell a broken ledger from a broken tool, and a
    script cannot tell either, because both exit non-zero.

    Worse, `append` reads the last chain before writing, so one appended byte
    stopped the recorder from ever appending again — every later decision lost,
    which is the one failure this project cannot have. For the cost of one byte.
    """
    try:
        brut = json.loads(ligne)
    except json.JSONDecodeError as erreur:
        return None, (f"line {numero} is not valid JSON ({erreur.msg} at column "
                      f"{erreur.colno}): it is not a record, and nothing vouches "
                      "for what it replaced")
    if not isinstance(brut, Mapping):
        return None, (f"line {numero} is valid JSON but not an object "
                      f"({type(brut).__name__}): it is not a record")
    manquantes = [cle for cle in _CLES_REQUISES if cle not in brut]
    if manquantes:
        return None, (f"line {numero} is missing {', '.join(manquantes)}: "
                      "it is not a record")
    return brut, None


def _canonical(body: Mapping[str, Any]) -> str:
    """The one rendering a record's hash is taken over, and the one written.

    `allow_nan=False` on purpose. Python writes `NaN` and `Infinity` for
    non-finite floats and reads them back again, so a ledger holding either
    verified clean here while `jq`, Go and Rust rejected the line — a file that
    claims to be JSON Lines and is not. The redactor describes such values
    before they arrive; this raises if one ever gets past it, because failing
    loudly beats appending a line no auditor can parse to an append-only file.
    """
    return json.dumps(body, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False)


def _chain_hash(body: Mapping[str, Any], prev: str | None) -> str:
    material = (prev or "") + _canonical(body)
    return "sha256:" + hashlib.sha256(material.encode("utf-8")).hexdigest()


def _rule_note(same_rule: bool | None) -> str:
    """The clause that keeps a replay from accusing the wrong party."""
    if same_rule is True:
        return ""
    if same_rule is False:
        return " -- but this is not the rule that ran"
    return " (no rule recorded: replayed against an assumed rule)"


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

    @property
    def store(self) -> EvidenceStore | None:
        """The evidence store this ledger resolves citations against, if any.

        A ledger opened without one still reads: the decisions are in the file.
        What it cannot do is show what they were standing on, and a reader is
        told that rather than shown an empty section.
        """
        return self._store

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
        rule_digest: str | None = None,
    ) -> Decision:
        body: dict[str, Any] = {
            "name": name,
            "started_at": started_at,
            "agent_version": agent_version,
            "evidence": list(evidence),
            "asks": [dict(a) for a in asks],
            "model_calls": [dict(c) for c in model_calls],
            "actions": [dict(a) for a in actions],
            "outcome": dict(outcome or {}),
        }
        if rule_digest is not None:
            body["rule_digest"] = rule_digest
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
            rule_digest=rule_digest,
        )

    def _analysees(self) -> tuple[list[Mapping[str, Any]], list[str]]:
        """Every line that is a record, and a problem for every line that is not.

        The two halves are returned together on purpose: a malformed line that
        is merely skipped is indistinguishable from a deleted one, and silent
        deletion is the attack. Nothing here drops a line without saying so.
        """
        records: list[Mapping[str, Any]] = []
        problems: list[str] = []
        for numero, ligne in enumerate(self._lines(), start=1):
            brut, souci = _analyser(numero, ligne)
            if souci is not None:
                problems.append(souci)
            else:
                assert brut is not None
                records.append(brut)
        return records, problems

    def records(self) -> list[Decision]:
        """The well-formed records. `verify` is what reports the rest.

        A reader that raised on a corrupt line could show nothing at all — so
        the page an auditor opens on a tampered ledger would be a traceback
        rather than the banner that says it does not hold.
        """
        return [self._revive(raw) for raw in self._analysees()[0]]

    def verify(self) -> list[str]:
        """Re-chains the whole file and resolves every citation.

        Reports the position of the first record that does not hold, counting
        from one, because "something is wrong somewhere" is not a finding.
        """
        lus, problems = self._analysees()
        prev: str | None = None

        for position, raw in enumerate(lus, start=1):
            body = {key: raw[key] for key in _BODY_KEYS if key in raw}

            if raw.get("prev") != prev:
                problems.append(
                    f"record {position} ({raw['name']}) does not follow the one before it: "
                    "a record was edited, deleted or inserted"
                )
            elif _chain_hash(body, prev) != raw.get("chain"):
                problems.append(
                    f"record {position} ({raw['name']}) has been edited since it was written"
                )

            hors_chaine = sorted(set(raw) - set(_BODY_KEYS) - set(_STRUCTURAL_KEYS))
            if hors_chaine:
                problems.append(
                    f"record {position} ({raw['name']}) carries "
                    f"{', '.join(hors_chaine)}, which no hash covers: this verifier "
                    "cannot vouch for a field it does not know about"
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

        It also reports whether the rule it was handed is the one the decision
        was stamped with. Without that, an edited rule produces a mismatch
        that reads as "the agent decided wrongly" when the truth is "you
        replayed with the wrong code" — and those are opposite findings.
        """
        explained = self.explain(position)
        recorded = dict(explained.decision.outcome)
        same_rule = self._same_rule(explained.decision, decide)
        note = _rule_note(same_rule)

        try:
            recomputed = dict(decide(explained.evidence))
        except Exception as error:  # noqa: BLE001 - the point is to report it
            return Replay(
                position=position,
                name=explained.decision.name,
                matched=False,
                recorded=recorded,
                recomputed=None,
                same_rule=same_rule,
                detail=f"the rule no longer runs on this evidence: "
                       f"{type(error).__name__}: {error}{note}",
            )

        matched = _canonical(recomputed) == _canonical(recorded)
        return Replay(
            position=position,
            name=explained.decision.name,
            matched=matched,
            recorded=recorded,
            recomputed=recomputed,
            same_rule=same_rule,
            detail=(
                f"the rule reproduces the recorded decision{note}"
                if matched
                else f"recorded {_canonical(recorded)}, "
                     f"recomputed {_canonical(recomputed)}{note}"
            ),
        )

    @staticmethod
    def _same_rule(decision: "Decision", decide: Callable[..., Any]) -> bool | None:
        """None when the decision names no rule, or the replayed one has no source.

        A rule whose source cannot be read (a built-in, a C extension, a
        lambda typed into a REPL) leaves the question unanswered rather than
        answered wrongly: "I could not tell" and "it is a different rule" are
        not the same statement.
        """
        if decision.rule_digest is None:
            return None
        try:
            return rule_digest(decide) == decision.rule_digest
        except ValueError:
            return None

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

    def commitment(self) -> tuple[int, str | None]:
        """How many decisions, and the hash at the end of the chain.

        A chain proves that the records it holds follow one another. It proves
        nothing about records it does **not** hold, and nothing about when any
        of them was written. An adversarial bench against this ledger
        (`scripts/adversarial.py`) catches nine attacks out of thirteen with the
        chain alone, and the four it misses share that one cause:

        - cut the tail off and what remains is a valid chain;
        - republish an older copy and it is a valid chain too;
        - append a record you computed yourself and the chain still closes;
        - hold the writer, rewrite everything, and the chain is perfect.

        This pair is what closes all four — **provided someone who is not the
        adversary wrote it down earlier**. Count and head together move under
        every one of those four attacks, so a CI job, an auditor or a
        counterparty that recorded `(count, head)` on Monday can refuse
        Tuesday's file.

        It is deliberately two small values: short enough to paste into a
        ticket, a commit message or a chat, which is the whole point. What it
        does not give you is *time* — nothing here proves when a record was
        written, and that is what external anchoring is for.

        A line that is not a record is not counted, because the count is of
        decisions and a reader who counted raw lines would report a different
        number than another reader on the same file. Garbage appended to the
        file therefore moves neither value — that case belongs to `verify`,
        which reports it for as long as the line is there. The two tools answer
        different questions and neither covers for the other.
        """
        lus, _ = self._analysees()
        return len(lus), self._last_chain()

    def _last_chain(self) -> str | None:
        """The chain at the end of the *well-formed* records.

        Not simply the last line. One corrupt byte appended to the file used to
        raise here, and since `append` reads this before writing, the recorder
        could never append again: a denial-of-recording attack for the price of
        one byte, against the one failure this project cannot have.

        Building on the last good chain is the deliberate choice. Refusing to
        append would hand that attack its result; the corrupt line stays in the
        file and `verify` reports it for as long as the ledger exists, so
        nothing is hidden — recording simply continues over it.
        """
        lus, _ = self._analysees()
        if not lus:
            return None
        chain = lus[-1].get("chain")
        return chain if isinstance(chain, str) else None

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
            rule_digest=raw.get("rule_digest"),
        )
