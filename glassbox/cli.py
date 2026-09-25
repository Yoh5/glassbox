"""What an auditor runs without reading a line of our code.

Two commands, because two questions matter after an incident: does this ledger
still hold together, and what caused this action.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from .evidence import EvidenceStore
from .ledger import Ledger

SNIPPET = 160


def _ledger(args: argparse.Namespace) -> Ledger:
    store = EvidenceStore(args.evidence) if args.evidence else None
    return Ledger(args.ledger, store=store)


def _verify(args: argparse.Namespace) -> int:
    led = _ledger(args)
    problems = led.verify()
    if args.evidence:
        problems += EvidenceStore(args.evidence).verify()

    if not problems:
        print(f"{len(led.records())} decision(s) verified: the chain holds.")
        return 0

    for problem in problems:
        print(f"FAIL  {problem}")
    print(f"\n{len(problems)} problem(s).")
    return 1


def _trace(args: argparse.Namespace) -> int:
    hits = _ledger(args).trace_action(args.action)
    if not hits:
        print(f"no decision took an action of kind {args.action!r}.")
        return 0

    for hit in hits:
        print(f"#{hit.position}  {hit.decision.name}  {hit.decision.started_at}  "
              f"version {hit.decision.agent_version}")
        for action in hit.decision.actions:
            print(f"      action: {action}")
        for item in hit.evidence:
            text = item.payload.decode("utf-8", "replace").replace("\n", " ")
            print(f"      read:   {item.source}  fetched {item.fetched_at}")
            print(f"              {text[:SNIPPET]}{'...' if len(text) > SNIPPET else ''}")
        print()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="glassbox", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    verify = sub.add_parser("verify", help="re-chain the ledger and resolve every citation")
    verify.add_argument("ledger", type=Path)
    verify.add_argument("--evidence", type=Path, default=None)
    verify.set_defaults(run=_verify)

    trace = sub.add_parser("trace", help="find the decisions behind an action, and what they read")
    trace.add_argument("ledger", type=Path)
    trace.add_argument("--action", required=True)
    trace.add_argument("--evidence", type=Path, required=True)
    trace.set_defaults(run=_trace)

    args = parser.parse_args(argv)
    return int(args.run(args))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
