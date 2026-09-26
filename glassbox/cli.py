"""What an auditor runs without reading a line of our code.

Five commands, for the four questions a record has to answer -- does this
ledger still hold together, what caused this action, would the rule decide the
same thing again, what did all of it cost -- and one that puts the same four
answers on a page, for the reader who will not type any of this.
"""

from __future__ import annotations

import argparse
import importlib
import importlib.util
from pathlib import Path
from typing import Any, Callable

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


def _load_rule(spec: str) -> Callable[..., Any]:
    """`path/to/file.py:function` or `package.module:function`.

    A rule lives in the agent's own code, so the replay has to reach into it
    rather than the other way round. The error names what was not found: a
    replay that quietly runs the wrong function is worse than one that refuses.
    """
    target, _, name = spec.rpartition(":")
    if not target or not name:
        raise ValueError(f"expected module:function or file.py:function, got {spec!r}")

    if target.endswith(".py"):
        module_spec = importlib.util.spec_from_file_location("glassbox_rule", target)
        if module_spec is None or module_spec.loader is None:
            raise ValueError(f"cannot load {target}")
        module = importlib.util.module_from_spec(module_spec)
        module_spec.loader.exec_module(module)
    else:
        module = importlib.import_module(target)

    if not hasattr(module, name):
        raise ValueError(f"{target} has no function named {name}")
    return getattr(module, name)


def _replay(args: argparse.Namespace) -> int:
    try:
        rule = _load_rule(args.rule)
    except (ValueError, ImportError, FileNotFoundError, SyntaxError) as error:
        print(f"FAIL  {error}")
        return 1

    results = _ledger(args).replay_all(rule)
    for result in results:
        mark = "ok  " if result.matched else "FAIL"
        print(f"{mark}  #{result.position}  {result.name}  {result.detail}")

    matched = sum(1 for r in results if r.matched)
    print(f"\n{matched}/{len(results)} decision(s) reproduced by this rule.")

    # A replay where every decision reproduces, run against code that is
    # demonstrably not the code that ran, is a green light for a check nobody
    # performed. It exits non-zero however well the answers lined up.
    wrong_rule = sum(1 for r in results if r.same_rule is False)
    if wrong_rule:
        print(f"{wrong_rule} of them were stamped with a different rule: "
              "this is not the code that decided them.")
        return 1

    return 0 if matched == len(results) else 1


def _stats(args: argparse.Namespace) -> int:
    stats = Ledger(args.ledger).stats()

    print(f"decisions   {stats['decisions']}")
    print(f"asks        {stats['asks']}")
    for tier, count in sorted(stats["calls_by_tier"].items()):
        print(f"  {tier:<9} {count} call(s)")
    print(f"cost        ${stats['cost_usd']:.4f}")

    share = stats["changed_share"]
    if share is None:
        print("escalation  nothing was escalated: the cheap tier answered every question")
    else:
        print(
            f"escalation  {stats['escalated']} of {stats['asks']} ask(s), "
            f"and the answer changed in {share * 100:.0f}% of them"
        )
    return 0


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


def _serve(args: argparse.Namespace) -> int:
    # Imported here so the four read-only commands never pull in a socket.
    from .viewer import serve

    serve(_ledger(args), host=args.host, port=args.port)
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

    replay = sub.add_parser("replay", help="re-run a rule over the evidence each decision cited")
    replay.add_argument("ledger", type=Path)
    replay.add_argument("--rule", required=True, help="module:function or file.py:function")
    replay.add_argument("--evidence", type=Path, required=True)
    replay.set_defaults(run=_replay)

    stats = sub.add_parser("stats", help="what the run cost, and what escalating bought")
    stats.add_argument("ledger", type=Path)
    stats.add_argument("--evidence", type=Path, default=None)
    stats.set_defaults(run=_stats)

    view = sub.add_parser("serve", help="browse the ledger in a local, read-only page")
    view.add_argument("ledger", type=Path)
    view.add_argument("--evidence", type=Path, default=None)
    view.add_argument("--port", type=int, default=8000)
    # Loopback by default. A decision ledger holds what an agent read, what it
    # was told and what it did; putting that on a network is a choice someone
    # has to make out loud.
    view.add_argument("--host", default="127.0.0.1")
    view.set_defaults(run=_serve)

    args = parser.parse_args(argv)
    return int(args.run(args))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
