"""Which code decided this.

A replay compares a recorded decision to whatever function it is handed. That
is a useful check and a dangerous one: replay with an edited rule and the
mismatch reads as *the agent decided wrongly*, when the truth is *you replayed
with the wrong code*. Opposite findings, identical output.

So a decision can carry the digest of the rule that took it, and the replay
says which of the two it is looking at.

**What the digest covers, exactly:** the source text of the function itself,
with its indentation removed so that a rule defined inside another is the same
rule. It does not cover the helpers that function calls, the module it lives
in, or the library versions underneath it. A digest that matches is therefore
evidence, not proof; a digest that differs is certain. Overclaiming here would
be worse than not measuring at all.
"""

from __future__ import annotations

import hashlib
import inspect
import textwrap
from typing import Any, Callable


def rule_digest(rule: Callable[..., Any]) -> str:
    """A stable digest of a decision function's own source."""
    try:
        source = inspect.getsource(rule)
    except (OSError, TypeError) as error:
        # A built-in, a C extension, or a function defined in a REPL. Refusing
        # is the honest answer: a digest of something else would be a claim
        # about code nobody can produce.
        raise ValueError(
            f"cannot read the source of {getattr(rule, '__name__', rule)!r}, so it cannot be "
            "stamped on a decision: a rule has to live in a file that can be read back"
        ) from error

    canonical = textwrap.dedent(source).strip()
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()
