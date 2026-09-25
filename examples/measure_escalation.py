"""A real run against Nemotron, to find out what escalating actually buys.

Twelve questions of rising ambiguity. The cheap tier answers each one twice; a
disagreement sends the question up a tier. Everything lands in a ledger, and
`glassbox stats` adds it up afterwards from the record.

    python examples/measure_escalation.py
"""

from pathlib import Path

from glassbox.nebius import nebius_call
from glassbox.recorder import Recorder
from glassbox.router import Router

QUESTIONS = [
    "In one word, what is the capital of France?",
    "In one word, is 17 a prime number? Answer yes or no.",
    "In one word, what colour is a ripe banana?",
    "In one word, how many continents are there?",
    "In one word, is 1 a prime number? Answer yes or no.",
    "In one word, is a tomato a fruit or a vegetable?",
    "In one word, is 0.999... equal to 1? Answer yes or no.",
    "In one word, is a hot dog a sandwich? Answer yes or no.",
    "In one word, was the year 1900 a leap year? Answer yes or no.",
    "In one word, is Pluto a planet? Answer yes or no.",
    "In one word, does a straw have one hole or two? Answer one or two.",
    "In one word, is water wet? Answer yes or no.",
]


def main() -> None:
    values = dict(
        line.split("=", 1)
        for line in Path(".env").read_text(encoding="utf-8").splitlines()
        if "=" in line and not line.strip().startswith("#")
    )
    key = values["NEBIUS_API_KEY"].strip()
    base = values.get("NEBIUS_BASE_URL", "https://api.tokenfactory.nebius.com/v1").strip()

    router = Router(nebius_call(api_key=key, base_url=base, max_tokens=700))
    rec = Recorder("runs/escalation", agent_version="measure-1", secrets=[key], router=router)

    for question in QUESTIONS:
        with rec.decision("answer") as d:
            answer = d.ask(question)
            d.outcome(action="answered", reason=answer.text[:80])
        mark = f"  -> {answer.tier}" + (
            f" (changed: {answer.changed_on_escalation})" if answer.escalated_from else ""
        )
        print(f"{question[:58]:<60}{answer.text[:18]:<20}{mark}")

    print()
    print("verify:", rec.verify() or "the chain holds")
    print(f"ledger: {rec.ledger.path}")


if __name__ == "__main__":
    main()
