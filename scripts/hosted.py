"""The hosted demo: one published ledger, read-only, that says what it is.

The product's viewer binds to `127.0.0.1` and that default does not move. A
decision ledger is an agent's most sensitive artifact — what it read, what it
was told, what it did — and putting one on a network by default would be the
opposite of what this project argues.

So the demo is a deliberate exception, narrow enough to state in one line on
the page: **one snapshot, already in the repository, of a measured run.** The
ledger it serves is `runs/escalation/ledger.jsonl` — the real escalation
measurement against Nemotron on Nebius Token Factory. It records tiers, costs,
the hash chain and the verdict. It carries no prompts, no responses and no
evidence bytes, which is why it can be published at all: `evidence` is empty in
every record, and that was checked before this file existed rather than
assumed.

Run it anywhere that sets `PORT`:

    python scripts/hosted.py

Nothing here is importable by the library: a deployment detail has no business
in `glassbox/`.
"""

from __future__ import annotations

import os
from pathlib import Path

from glassbox.ledger import Ledger
from glassbox.viewer import serve

RACINE = Path(__file__).resolve().parent.parent
LEDGER = RACINE / "runs" / "escalation" / "ledger.jsonl"

NOTICE = (
    "This is a published, read-only snapshot of one measured run — the "
    "escalation measurement against NVIDIA Nemotron on Nebius Token Factory. "
    "Glass Box itself serves a ledger on 127.0.0.1 only; a decision ledger is "
    "not something to put on a network. Everything below is recomputed from "
    "the file on each request: the chain banner is Ledger.verify(), the totals "
    "are Ledger.stats(). Reproduce it with "
    "`python -m glassbox verify runs/escalation/ledger.jsonl`."
)


def main() -> int:
    if not LEDGER.is_file():
        # Said out loud rather than served as an empty page. A viewer that
        # shows nothing reads as "this run recorded nothing", which is the one
        # confusion this product exists to prevent.
        print(f"No ledger at {LEDGER} — nothing to publish.")
        return 2

    # `0.0.0.0` is passed here and only here, next to the sentence that
    # justifies it. Grepping the repository for it finds this file.
    serve(Ledger(LEDGER), host="0.0.0.0", port=int(os.environ.get("PORT", "8000")),
          notice=NOTICE)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
