"""The evidence store: what the agent saw, when, and where it came from.

Every input an agent reads is stored here before a model is allowed near it,
because the question that matters after an incident is not "what did the model
answer" but "what was it looking at". A decision cites evidence by id, so the
path from an action back to the byte that provoked it is a lookup rather than
an investigation.

An id addresses an *observation*, not a payload: the same bytes fetched from
two sources, or from one source at two times, are two different facts about the
world. The payload digest is carried alongside, so a reader can still see that
the bytes were identical.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from .redact import Redactor


class UnknownEvidence(KeyError):
    """Raised for an id the store has never seen — never a silent None."""


@dataclass(frozen=True)
class Evidence:
    id: str
    source: str
    fetched_at: str
    media_type: str
    payload_sha256: str
    payload: bytes
    redacted: bool


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class EvidenceStore:
    """Content-addressed, append-only, with redaction at the boundary.

    Redaction runs before hashing, so an id covers exactly what was stored. The
    alternative — hash first, scrub later — produces a store whose ids no longer
    describe its contents, which is worse than the secret it was meant to hide.
    """

    def __init__(self, root: str | Path, redactor: Redactor | None = None) -> None:
        self.root = Path(root)
        self._objects = self.root / "objects"
        self._items = self.root / "items"
        self._objects.mkdir(parents=True, exist_ok=True)
        self._items.mkdir(parents=True, exist_ok=True)
        self._redactor = redactor or Redactor([])

    def put(
        self,
        *,
        source: str,
        payload: bytes,
        fetched_at: str,
        media_type: str = "text/plain",
    ) -> Evidence:
        redacted = self._redactor.applied(source) or self._redactor.applied(
            payload.decode("utf-8", "replace")
        )
        source = self._redactor(source)
        payload = self._redactor.bytes(payload)

        payload_sha256 = _sha256(payload)
        envelope = json.dumps(
            {
                "source": source,
                "fetched_at": fetched_at,
                "media_type": media_type,
                "payload_sha256": payload_sha256,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        item = Evidence(
            id="sha256:" + _sha256(envelope.encode("utf-8")),
            source=source,
            fetched_at=fetched_at,
            media_type=media_type,
            payload_sha256=payload_sha256,
            payload=payload,
            redacted=redacted,
        )

        blob = self._objects / payload_sha256
        if not blob.exists():
            blob.write_bytes(payload)
        (self._items / f"{item.id.split(':', 1)[1]}.json").write_text(
            json.dumps(
                {
                    "id": item.id,
                    "source": item.source,
                    "fetched_at": item.fetched_at,
                    "media_type": item.media_type,
                    "payload_sha256": item.payload_sha256,
                    "redacted": item.redacted,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        return item

    def get(self, evidence_id: str) -> Evidence:
        path = self._items / f"{evidence_id.split(':', 1)[-1]}.json"
        if not path.exists():
            raise UnknownEvidence(evidence_id)
        meta = json.loads(path.read_text(encoding="utf-8"))
        return Evidence(
            id=meta["id"],
            source=meta["source"],
            fetched_at=meta["fetched_at"],
            media_type=meta["media_type"],
            payload_sha256=meta["payload_sha256"],
            payload=(self._objects / meta["payload_sha256"]).read_bytes(),
            redacted=meta["redacted"],
        )

    def verify(self) -> list[str]:
        """Re-hashes every stored payload. Silence here is the only good news."""
        problems: list[str] = []
        for blob in sorted(self._objects.iterdir()):
            actual = _sha256(blob.read_bytes())
            if actual != blob.name:
                problems.append(
                    f"payload {blob.name[:12]} has been edited on disk: it now hashes to {actual[:12]}"
                )
        return problems
