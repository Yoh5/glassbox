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

import hashlib
import math

from typing import Any, Iterable, Mapping

PLACEHOLDER = "[redacted]"

#: Past this many nested containers, a structure is described rather than walked.
#: A cycle is caught by identity below; this catches the merely absurd, and keeps
#: the walk from spending the interpreter's stack on data nobody will read.
PROFONDEUR_MAX = 50

#: How much of a described value's `repr` is kept. Enough to recognise what it
#: was, short enough that a stray megabyte in a field cannot bloat the ledger.
REPR_MAX = 200

#: The scalars JSON has. Everything else gets described, including `float`'s
#: non-finite values, which Python writes as `NaN` and `Infinity` — tokens the
#: JSON grammar does not contain.
_CLES_JSON = (str, int, float, bool, type(None))


def _descripteur(charge: bytes) -> str:
    """Ce qu'on inscrit au registre à la place d'octets : leur taille et leur hachage.

    Assez pour reconnaître la même charge deux fois et pour la rapprocher d'une
    preuve stockée, et jamais assez pour reconstruire ce qu'elle contenait.
    """
    return f"<{len(charge)} bytes sha256:{hashlib.sha256(charge).hexdigest()[:16]}>"


def _json_natif(obj: Any) -> bool:
    """Whether `json.dumps` writes this scalar as valid JSON, unaided.

    `bool` is a subclass of `int` and both are fine. `float` is not: Python
    emits `NaN` and `Infinity` for its non-finite values, and a ledger line
    holding either is not JSON — Python reads its own output back, so nothing
    complains here, while `jq` and every strict parser reject the line.
    """
    if isinstance(obj, float):
        return math.isfinite(obj)
    return obj is None or isinstance(obj, (str, int))


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

    def decrire(self, obj: Any) -> str:
        """What goes to the ledger in place of a value JSON cannot carry.

        The type name plus a redacted, truncated `repr`. An auditor reading
        `<Decimal 19.99>` knows what the agent was handed and that the recorder
        did not silently drop it; nobody is misled into thinking the field held
        the string "19.99".

        The `repr` is redacted because an object's own `repr` is a perfectly
        ordinary place for a credential to sit — a session, a client, a config
        object — and this is the last point before an append-only file.
        """
        try:
            texte = repr(obj)
        except Exception as erreur:  # noqa: BLE001 - a __repr__ may raise anything
            # A broken `__repr__` must not take the decision down with it. The
            # record says the value could not be described, which is itself
            # worth knowing, and the run continues.
            texte = f"<repr indisponible: {type(erreur).__name__}>"
        texte = self(texte)
        if len(texte) > REPR_MAX:
            texte = texte[:REPR_MAX] + f"... (+{len(texte) - REPR_MAX} car.)"
        return f"<{type(obj).__name__} {texte}>"

    def value(self, obj: Any) -> Any:
        """Redacts through a structure, keeping its shape where JSON can hold it.

        An action is recorded as `{"kind": ..., **fields}`, and fields are
        whatever the agent author passed: `token="sk-live-..."` sits beside
        `retries=3` and `headers={"authorization": "..."}`. Stringifying the lot
        would redact it and turn 3 into "3", so the walk keeps the shape and
        touches only what it must.

        Keys are redacted as well as values. A secret used as a dictionary key
        is unusual, but a ledger is append-only and hash-chained: a credential
        that reaches it cannot be taken back out, so the cheap half of the pair
        is not the one to skip.
        """
        return self._walk(obj, ())

    def _walk(self, obj: Any, chemin: tuple[int, ...]) -> Any:
        """The walk proper. `chemin` holds the ids of the containers above us.

        Identity rather than equality, and the current path rather than every
        container seen: a structure that holds the same dictionary twice side by
        side is ordinary and must be walked twice, while one that holds itself
        must not be walked at all.
        """
        if isinstance(obj, str):
            return self(obj)
        if isinstance(obj, (bytes, bytearray)):
            # Redacted bytes are still bytes, and the ledger is JSON: writing
            # them back raised `TypeError: Object of type bytes is not JSON
            # serializable` from inside the decision block, so the decision was
            # never recorded at all. A recorder that drops what it was asked to
            # record is the one failure this project cannot have.
            #
            # They are described rather than carried. An action's parameters say
            # what the agent did; the bytes it acted on belong in the evidence
            # store, which is content-addressed and built for them. A descriptor
            # is also the only form that cannot hide a credential in a payload
            # nobody reads.
            return _descripteur(self.bytes(bytes(obj)))

        if isinstance(obj, (Mapping, list, tuple, set, frozenset)):
            if id(obj) in chemin:
                # `d = {}; d["self"] = d` is two lines of agent code and it used
                # to raise RecursionError here, inside the decision block —
                # losing the record, which is the one failure this project
                # cannot have. The cycle is named rather than followed.
                return f"<{type(obj).__name__} cycle>"
            if len(chemin) >= PROFONDEUR_MAX:
                return self.decrire(obj)
            dessous = chemin + (id(obj),)
            if isinstance(obj, Mapping):
                return {self._cle(key, dessous): self._walk(item, dessous)
                        for key, item in obj.items()}
            if isinstance(obj, (set, frozenset)):
                # Sorted on the rendered form, not left in iteration order: a
                # set of strings iterates differently from one process to the
                # next, so the same action recorded twice produced two different
                # chain hashes. Sorting on the rendered form also handles the
                # mixed-type set, which `sorted` alone cannot.
                return sorted((self._walk(item, dessous) for item in obj),
                              key=lambda rendu: (type(rendu).__name__, repr(rendu)))
            return [self._walk(item, dessous) for item in obj]

        if _json_natif(obj):
            return obj
        # A datetime, a Decimal, a Path, a UUID, an enum, a client object, a
        # NaN — every one of them raised `TypeError: Object of type ... is not
        # JSON serializable` from `_canonical`, and the decision was lost. They
        # are described, for the same reason bytes are.
        return self.decrire(obj)

    def _cle(self, key: Any, chemin: tuple[int, ...]) -> Any:
        """A redacted key JSON can actually use.

        `json.dumps` accepts only str, int, float, bool and None as keys, and
        the walk can produce something else: a tuple key comes back as a list,
        which is unhashable, so building the dictionary raised before anything
        reached the ledger.
        """
        rendu = self._walk(key, chemin)
        if isinstance(rendu, _CLES_JSON) and _json_natif(rendu):
            return rendu
        return self.decrire(key)
