"""A credential passed to `act()` must not reach the ledger.

`redact.py` opens by stating why: the ledger is append-only and hash-chained, so
a secret written into it cannot be scrubbed afterwards without breaking the
chain, and the only resolution is to redact before writing rather than after.
The recorder then wrote an action's parameters in raw.

    self._actions.append({"kind": kind, **fields})                  # raw
    self._outcome = {..., "reason": self._recorder.redact(str(fields))}   # redacted

The same dictionary, redacted in the copy and verbatim in the original — so the
author had already seen that fields carry secrets. And an action's parameters
are exactly where one appears: `d.act("call-api", token=...)`,
`d.act("send-email", api_key=...)`, a webhook URL with the secret in the path.

Found by pushing one secret through every channel into the ledger and grepping
for it: evidence source, evidence payload, `refuse`, `outcome`, the error path
and the decision name were all clean. `act` was not. 186 tests did not see it,
because none of them put a secret in an action.
"""

from __future__ import annotations

import json
import pathlib

from glassbox.recorder import Recorder

SECRET = "sk-live-this-must-never-appear-42"


def recorder(tmp_path: pathlib.Path, *secrets: str) -> Recorder:
    return Recorder(tmp_path, agent_version="a1b2c3d", secrets=secrets or (SECRET,))


def ledger_text(rec: Recorder) -> str:
    return rec.ledger.path.read_text(encoding="utf-8")


def only_action(rec: Recorder) -> dict:
    return json.loads(ledger_text(rec).splitlines()[0])["actions"][0]


def test_a_secret_in_an_action_field_never_reaches_the_ledger(tmp_path):
    rec = recorder(tmp_path)
    with rec.decision("call-api") as d:
        d.act("call-api", url="https://api.example.com", token=SECRET)

    assert SECRET not in ledger_text(rec)


def test_it_reaches_into_nested_structures(tmp_path):
    """Headers are a dict and tags are a list. A walk that stops at the top
    level would redact `token=` and publish `headers={"authorization": ...}`."""
    rec = recorder(tmp_path)
    with rec.decision("call-api") as d:
        d.act(
            "call-api",
            headers={"authorization": f"Bearer {SECRET}"},
            tags=["public", SECRET],
        )

    assert SECRET not in ledger_text(rec)
    action = only_action(rec)
    assert action["headers"]["authorization"] == "Bearer [redacted]"
    assert action["tags"] == ["public", "[redacted]"]


def test_a_secret_used_as_a_key_is_redacted_too(tmp_path):
    rec = recorder(tmp_path)
    with rec.decision("call-api") as d:
        d.act("call-api", headers={SECRET: "value"})

    assert SECRET not in ledger_text(rec)


def test_what_is_not_text_keeps_its_type(tmp_path):
    """The lazy fix is `str(fields)`, which redacts and turns 3 into "3".

    An action whose numbers have become strings is a worse record than one with
    a secret in it is a better one — both are wrong, and this guard keeps the
    repair from trading one for the other.
    """
    rec = recorder(tmp_path)
    with rec.decision("call-api") as d:
        d.act("call-api", retries=3, ok=True, ratio=0.5, nothing=None)

    action = only_action(rec)
    assert action["retries"] == 3 and isinstance(action["retries"], int)
    assert action["ok"] is True
    assert action["ratio"] == 0.5
    assert action["nothing"] is None


def test_the_action_is_still_readable_after_redaction(tmp_path):
    """Redaction that ate the useful half would make the record useless.

    The point of recording an action is to know what the agent did. The URL it
    called is not the credential and must survive.
    """
    rec = recorder(tmp_path)
    with rec.decision("call-api") as d:
        d.act("call-api", url="https://api.example.com/v1/send", token=SECRET)

    action = only_action(rec)
    assert action["kind"] == "call-api"
    assert action["url"] == "https://api.example.com/v1/send"
    assert action["token"] == "[redacted]"


def test_a_secret_in_the_decision_name_is_redacted(tmp_path):
    """Unlikely, and it costs one call to cover. The name is hashed into the
    chain like everything else, so it is just as permanent."""
    rec = recorder(tmp_path)
    with rec.decision(f"fetch-{SECRET}") as d:
        d.refuse("nothing to do")

    assert SECRET not in ledger_text(rec)


def test_every_other_channel_stays_clean(tmp_path):
    """The channels that were already right, held in place.

    This is the probe that found the defect, kept as a test so the next repair
    to any one of them cannot quietly open another hole.
    """
    rec = recorder(tmp_path)

    with rec.decision("read") as d:
        d.evidence(source=f"https://api.example.com?key={SECRET}",
                   payload=f"<p>token {SECRET}</p>".encode())
        d.refuse(f"the key {SECRET} is invalid")

    with rec.decision("report") as d:
        d.outcome(action="none", reason=f"saw {SECRET}")

    try:
        with rec.decision("boom"):
            raise ValueError(f"exploded on {SECRET}")
    except ValueError:
        pass

    assert SECRET not in ledger_text(rec)
    for fichier in (rec.store.root).rglob("*"):
        if fichier.is_file():
            assert SECRET not in fichier.read_text(encoding="utf-8", errors="replace")


def test_the_chain_still_holds_over_redacted_records(tmp_path):
    """Redaction runs before hashing, so the hash covers what was stored.

    If it ran after, every redacted record would read as tampered — which is
    the failure this ordering exists to prevent.
    """
    rec = recorder(tmp_path)
    with rec.decision("call-api") as d:
        d.act("call-api", token=SECRET)

    assert rec.verify() == []
