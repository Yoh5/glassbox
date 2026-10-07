"""Redaction at the boundary: nothing reaches the ledger carrying a credential.

The ledger is append-only and hash-chained on purpose, which means a secret
written into it cannot be scrubbed afterwards without breaking the chain — the
two properties are in direct tension, and the only resolution is to redact
before writing rather than after.

Redaction runs before hashing, so a record's hash covers what was actually
stored. A record whose text was redacted says so, rather than leaving a reader
to wonder whether `[redacted]` was in the source all along.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

PLACEHOLDER = "[redacted]"


class Redactor:
    """Replaces known secrets with a placeholder, in text and in bytes.

    Empty and missing values are dropped: an unset environment variable reads
    as an empty string, and replacing every empty string would turn the whole
    ledger into placeholders.
    """

    def __init__(self, secrets: Iterable[str | None]) -> None:
        # Longest first: replacing "abc" before "abc123" would cut the longer
        # secret in half and leave a recognisable tail in the ledger.
        self._secrets = sorted(
            {s for s in secrets if s}, key=len, reverse=True
        )

    def __call__(self, text: str) -> str:
        for secret in self._secrets:
            text = text.replace(secret, PLACEHOLDER)
        return text

    def bytes(self, payload: bytes) -> bytes:
        for secret in self._secrets:
            payload = payload.replace(secret.encode("utf-8"), PLACEHOLDER.encode("utf-8"))
        return payload

    def applied(self, text: str) -> bool:
        """Whether redacting this text would change it — recorded on the item."""
        return any(secret in text for secret in self._secrets)

    def value(self, obj: Any) -> Any:
        """Redacts through a structure, leaving everything that is not text alone.

        An action is recorded as `{"kind": ..., **fields}`, and fields are
        whatever the agent author passed: `token="sk-live-..."` sits beside
        `retries=3` and `headers={"authorization": "..."}`. Stringifying the lot
        would redact it and turn 3 into "3", so the walk keeps the shape and
        touches only the strings and bytes in it.

        Keys are redacted as well as values. A secret used as a dictionary key
        is unusual, but a ledger is append-only and hash-chained: a credential
        that reaches it cannot be taken back out, so the cheap half of the pair
        is not the one to skip.
        """
        if isinstance(obj, str):
            return self(obj)
        if isinstance(obj, (bytes, bytearray)):
            return self.bytes(bytes(obj))
        if isinstance(obj, Mapping):
            return {self.value(key): self.value(item) for key, item in obj.items()}
        if isinstance(obj, (list, tuple, set, frozenset)):
            return [self.value(item) for item in obj]
        return obj
