"""The façade: the three lines someone actually writes.

```python
rec = Recorder("runs", agent_version=git_sha(), secrets=[os.environ["API_KEY"]])

with rec.decision("summarise-page") as d:
    page = d.evidence(source=url, payload=html)
    answer = d.ask("Summarise and list actions", floor="nano")
    d.act("write-file", target="notes.md")
```

A library nobody wants to call will not be called, and a recorder people have
to remember to feed gets fed selectively — which is worse than no recorder,
because the gaps look like quiet afternoons.

So the block records itself. It records when the body raises, it records when
the body does nothing, and it refuses to be nested rather than producing a
record that describes two decisions at once.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from .evidence import Evidence, EvidenceStore
from .ledger import Ledger
from .redact import Redactor
from .router import Answer, Router
from .rule import rule_digest


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class DecisionContext:
    """The handle a block gets. Everything it is told lands in one record."""

    def __init__(self, recorder: "Recorder", name: str, started_at: str) -> None:
        self._recorder = recorder
        self.name = name
        self.started_at = started_at
        self._evidence: list[str] = []
        self._asks: list[Mapping[str, Any]] = []
        self._model_calls: list[Mapping[str, Any]] = []
        self._actions: list[Mapping[str, Any]] = []
        self._outcome: dict[str, Any] | None = None

    def evidence(self, *, source: str, payload: bytes, media_type: str = "text/plain") -> Evidence:
        """Stores an input and cites it. Called before a model sees the bytes."""
        item = self._recorder.store.put(
            source=source,
            payload=payload,
            fetched_at=self._recorder.clock(),
            media_type=media_type,
        )
        self._evidence.append(item.id)
        return item

    def ask(self, prompt: str, *, floor: str | None = None) -> Answer:
        if self._recorder.router is None:
            raise ValueError(
                "this Recorder has no router: construct it with router=Router(...) "
                "before asking a model, rather than making a call nothing records"
            )
        answer = self._recorder.router.ask(prompt, floor=floor)
        self._asks.append(
            {
                "tier": answer.tier,
                "escalated_from": answer.escalated_from,
                "changed_on_escalation": answer.changed_on_escalation,
                "cost_usd": answer.cost_usd,
                "calls": len(answer.calls),
            }
        )
        for call in answer.calls:
            self._model_calls.append(
                {"tier": call["tier"], "cost_usd": call["cost_usd"]}
            )
        return answer

    def act(self, kind: str, **fields: Any) -> None:
        self._actions.append({"kind": kind, **fields})
        self._outcome = {"action": kind, "reason": self._recorder.redact(str(fields))}

    def refuse(self, reason: str) -> None:
        """Nothing was done, and the record says why. A refusal is a decision."""
        self._outcome = {"action": "none", "reason": self._recorder.redact(reason)}

    def outcome(self, *, action: str, reason: str) -> None:
        self._outcome = {"action": action, "reason": self._recorder.redact(reason)}

    def _resolved_outcome(self, error: BaseException | None) -> Mapping[str, Any]:
        if error is not None:
            return {"action": "failed", "reason": self._recorder.redact(f"{type(error).__name__}: {error}")}
        if self._outcome is not None:
            return self._outcome
        return {"action": "none", "reason": "the block recorded no outcome"}

    def __enter__(self) -> "DecisionContext":  # pragma: no cover - entered by Recorder
        return self

    def __exit__(self, exc_type, exc, traceback) -> bool:
        self._recorder._close(self, exc)
        return False  # never swallow: the caller's error is the caller's


class Recorder:
    def __init__(
        self,
        root: str | Path,
        *,
        agent_version: str,
        secrets: Iterable[str | None] = (),
        router: Router | None = None,
        rule: Callable[..., Any] | None = None,
        clock: Callable[[], str] | None = None,
    ) -> None:
        self.root = Path(root)
        self.agent_version = agent_version
        self.clock = clock or _now
        self.router = router
        # Stamped on every record, so a replay can tell "the agent decided
        # wrongly" from "you replayed with the wrong code". Digested once, at
        # construction, so a rule edited mid-run is caught here rather than
        # silently stamping two different digests onto one run.
        self.rule_digest = rule_digest(rule) if rule is not None else None
        self._redactor = Redactor(secrets)
        self.store = EvidenceStore(self.root / "evidence", redactor=self._redactor)
        self.ledger = Ledger(self.root / "ledger.jsonl", store=self.store)
        self._open: DecisionContext | None = None

    def decision(self, name: str) -> DecisionContext:
        if self._open is not None:
            raise RuntimeError(
                f"a decision is already open ({self._open.name!r}): one block is one record, "
                "and nesting them would describe two decisions in one"
            )
        self._open = DecisionContext(self, name, self.clock())
        return self._open

    def redact(self, text: str) -> str:
        return self._redactor(text)

    def verify(self) -> list[str]:
        return self.ledger.verify() + self.store.verify()

    def _close(self, context: DecisionContext, error: BaseException | None) -> None:
        self.ledger.append(
            name=context.name,
            started_at=context.started_at,
            agent_version=self.agent_version,
            evidence=context._evidence,
            asks=context._asks,
            model_calls=context._model_calls,
            actions=context._actions,
            outcome=context._resolved_outcome(error),
            rule_digest=self.rule_digest,
        )
        self._open = None
