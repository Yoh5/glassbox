"""What an auditor runs without reading a line of our code.

Five commands, for the four questions a record has to answer -- does this
ledger still hold together, what caused this action, would the rule decide the
same thing again, what did all of it cost -- and one that puts the same four
answers on a page, for the reader who will not type any of this.

A sixth answers the question that comes before all of them, and only when
someone tries to reproduce the run: **are the three tiers this tool routes
between actually on this account?** Model ids get renamed and withdrawn. When
one of ours is gone, the router does not stop -- it fails on that tier and the
measurement quietly becomes a measurement of something else. That is the worst
way for a number to be wrong, so it gets a command that exits non-zero.
"""

from __future__ import annotations

import argparse
import importlib
import importlib.util
from pathlib import Path
from typing import Any, Callable

import os

from .evidence import EvidenceStore
from .ledger import Ledger
from .nebius import DEFAULT_BASE_URL, TIERS, list_models

SNIPPET = 160


def _ledger(args: argparse.Namespace) -> Ledger:
    store = EvidenceStore(args.evidence) if args.evidence else None
    return Ledger(args.ledger, store=store)


def _models(args: argparse.Namespace) -> int:
    key = os.environ.get(args.api_key_env, "").strip()
    if not key:
        print(f"{args.api_key_env} is not set: nothing to ask.")
        return 2

    try:
        available = set(list_models(key, args.base_url))
    except Exception as why:  # noqa: BLE001 - every failure reads the same here
        print(f"could not reach {args.base_url}: {why}")
        return 2

    missing = []
    for name, tier in TIERS.items():
        there = tier.model_id in available
        print(f"{name:<7} {tier.model_id:<45} {'available' if there else 'MISSING'}")
        if not there:
            missing.append(name)

    print(f"\n{len(available)} model(s) on this account.")
    if missing:
        # Naming them is the point: a fallback nobody notices turns a
        # measurement into a different measurement with the same title.
        print(
            f"{', '.join(missing)} not among them. Routing would fail on that "
            "tier, and the escalation numbers would be measuring something "
            "else. Check the ids in glassbox/nebius.py against the console."
        )
    return 1 if missing else 0


def _absent(path: Path, what: str) -> str:
    """Why an empty answer is not a good answer.

    The cheapest attack on a hash-chained ledger is not to alter it. Altering
    it breaks the chain, and that is the one thing this tool always catches.
    The cheap attack is to **delete** it — and `verify` used to answer, on a
    path that did not exist:

        0 decision(s) verified: the chain holds.     (exit 0)

    A nightly audit would have gone green through the whole incident. The same
    output greeted anyone who mistyped the path, which is how the first person
    to try this tool meets it.

    Nothing is not a passing grade. It exits 2, and it says which path it
    looked at, because the usual cause is the boring one.
    """
    return (
        f"{path} does not exist. Nothing was verified — and nothing verified "
        f"is not the same as {what}. Check the path; if it is right, the "
        "ledger is gone, which is the thing this tool exists to notice."
    )


def _head(args: argparse.Namespace) -> int:
    """Print the commitment someone else should write down.

    The output is meant to be pasted somewhere the holder of the ledger does
    not control — a ticket, a commit message, a message to a counterparty. That
    is what makes it worth anything: a commitment kept beside the file it
    commits to protects against nothing.
    """
    if not Path(args.ledger).exists():
        print(_absent(Path(args.ledger), "a head to record"))
        return 2

    # `head` ne lit pas les pièces : il n'a besoin que de la chaîne, donc il
    # n'expose pas `--evidence` et ne peut pas passer par `_ledger`.
    count, head = Ledger(args.ledger).commitment()
    if not count:
        print(f"{args.ledger} holds no decisions, so there is no head to record.")
        return 2

    print(f"decisions  {count}")
    print(f"head       {head}")
    print()
    print("Record these somewhere this ledger's holder does not control, and")
    print("later refuse anything that does not match:")
    print(f"  glassbox verify {args.ledger} --expect-count {count} "
          f"--expect-head {head}")
    return 0


def _commitment_problems(led: Ledger, args: argparse.Namespace) -> list[str]:
    """Compare the ledger against a commitment recorded earlier.

    Separate messages for the two mismatches, because they mean different
    things to whoever reads the failure. A different count means records were
    added or removed; the same count with a different head means the content
    was rewritten in place, which takes the writer's own tooling.
    """
    expected_count = getattr(args, "expect_count", None)
    expected_head = getattr(args, "expect_head", None)
    if expected_count is None and expected_head is None:
        return []

    count, head = led.commitment()
    problems: list[str] = []
    if expected_count is not None and count != expected_count:
        sens = "added to" if count > expected_count else "removed from"
        problems.append(
            f"{abs(count - expected_count)} decision(s) have been {sens} this "
            f"ledger since the head was recorded: {expected_count} then, "
            f"{count} now. The chain still holds, which is exactly why the "
            f"count has to be checked separately."
        )
    if expected_head is not None and head != expected_head:
        if expected_count is None or count == expected_count:
            problems.append(
                f"the head does not match the one recorded: expected "
                f"{expected_head}, found {head}. The record count is unchanged, "
                f"so this ledger was rewritten rather than cut — which takes "
                f"whatever wrote it in the first place."
            )
        else:
            problems.append(f"head {head} does not match the recorded {expected_head}.")
    return problems


def _verify(args: argparse.Namespace) -> int:
    if not Path(args.ledger).exists():
        print(_absent(Path(args.ledger), "a chain that holds"))
        return 2

    led = _ledger(args)
    problems = led.verify()
    if args.evidence:
        problems += EvidenceStore(args.evidence).verify()
    problems += _commitment_problems(led, args)

    if not problems:
        count = len(led.records())
        if not count:
            # An empty ledger is a legitimate state before the first run, and
            # a catastrophic one after it. The tool cannot tell which, so it
            # refuses to call it a pass and says both.
            print(
                f"{args.ledger} holds no decisions. That is either a run that "
                "has not started, or one whose record is gone. This tool "
                "cannot tell the two apart, so it does not call it a pass."
            )
            return 2
        print(f"{count} decision(s) verified: the chain holds.")
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
    if not Path(args.ledger).exists():
        print(_absent(Path(args.ledger), "a rule that still reproduces"))
        return 2

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
    if not Path(args.ledger).exists():
        print(_absent(Path(args.ledger), "a run that cost nothing"))
        return 2

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
    if not Path(args.ledger).exists():
        print(_absent(Path(args.ledger), "an action with no cause"))
        return 2

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

    models = sub.add_parser(
        "models", help="check this account really exposes the three tiers we route between"
    )
    models.add_argument("--api-key-env", default="NEBIUS_API_KEY")
    models.add_argument("--base-url", default=DEFAULT_BASE_URL)
    models.set_defaults(run=_models)

    verify = sub.add_parser("verify", help="re-chain the ledger and resolve every citation")
    verify.add_argument("ledger", type=Path)
    verify.add_argument("--evidence", type=Path, default=None)
    # Les deux moitiés de l'engagement sont séparées exprès : un compte seul
    # attrape une coupure, une tête seule attrape une réécriture, et seuls les
    # deux ensemble attrapent les quatre attaques que la chaîne laisse passer.
    verify.add_argument("--expect-count", type=int, default=None,
                        help="fail unless the ledger holds exactly this many decisions")
    verify.add_argument("--expect-head", type=str, default=None,
                        help="fail unless the chain ends on this hash")
    verify.set_defaults(run=_verify)

    head = sub.add_parser(
        "head",
        help="print the count and head hash to record elsewhere")
    head.add_argument("ledger", type=Path)
    head.set_defaults(run=_head)

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
