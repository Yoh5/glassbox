"""A small read-only viewer for a ledger.

Three questions, one page each: is this log telling the truth, what was this
decision standing on, and what did the whole run cost. It renders from the
files on disk and computes nothing of its own — the banner is
`Ledger.verify()`, the totals are `Ledger.stats()` — so the page can never
claim something `python -m glassbox verify` would deny.

**Everything it displays is hostile input.** The payloads it shows are bytes
an attacker chose, taken off a page the agent was made to read; the whole
point of this project is the case where those bytes carried an instruction.
A viewer that rendered them as markup would execute the payload it was built
to investigate, so every value that reaches the page goes through
`html.escape` and nothing is ever inserted as HTML. There is no JavaScript on
these pages at all — not as a precaution, as an absence of attack surface.

It binds to the loopback interface. A decision ledger is an agent's most
sensitive artifact: what it read, what it was told, what it did. That is not
something to put on a network by default.
"""

from __future__ import annotations

import html
import json
from functools import partial
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Mapping

from .evidence import UnknownEvidence
from .ledger import Ledger

_STYLE = """
:root { color-scheme: dark; }
* { box-sizing: border-box; }
body { margin: 0; padding: 2rem 1rem 4rem; background: #0e1116; color: #d7dde5;
       font: 15px/1.6 ui-sans-serif, system-ui, -apple-system, Segoe UI, sans-serif; }
main { max-width: 52rem; margin: 0 auto; }
h1 { font-size: 1.35rem; margin: 0 0 .25rem; letter-spacing: -.01em; }
h2 { font-size: .8rem; text-transform: uppercase; letter-spacing: .09em;
     color: #7d8796; margin: 2.2rem 0 .7rem; font-weight: 600; }
a { color: #8ab4f8; text-decoration: none; }
a:hover { text-decoration: underline; }
.sub { color: #7d8796; margin: 0 0 1.6rem; font-size: .9rem; }
.banner { border-radius: 8px; padding: .85rem 1rem; margin: 0 0 1.5rem;
          border: 1px solid; font-size: .93rem; }
.ok { border-color: #1f4d33; background: #0f2419; color: #7ee2a8; }
.bad { border-color: #5c2222; background: #2a1112; color: #ff9a92; }
.bad ul { margin: .5rem 0 0; padding-left: 1.1rem; }
.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(8.5rem, 1fr)); gap: .6rem; }
.cell { background: #161b22; border: 1px solid #222a35; border-radius: 8px; padding: .7rem .8rem; }
.cell .n { font-size: 1.25rem; font-weight: 600; color: #e8edf3; }
.cell .k { font-size: .73rem; text-transform: uppercase; letter-spacing: .07em; color: #7d8796; }
ol.runs { list-style: none; margin: 0; padding: 0; }
ol.runs li { border-bottom: 1px solid #1d232c; }
ol.runs a { display: flex; gap: .8rem; align-items: baseline; padding: .7rem .2rem; color: inherit; }
ol.runs a:hover { background: #141a21; text-decoration: none; }
ol.runs .pos { color: #566070; font-variant-numeric: tabular-nums; min-width: 2.2rem; }
ol.runs .name { font-weight: 600; }
ol.runs .when { margin-left: auto; color: #7d8796; font-size: .85rem; }
.tag { display: inline-block; font-size: .72rem; padding: .1rem .45rem; border-radius: 4px;
       background: #1d232c; color: #9aa6b5; border: 1px solid #262f3b; }
.tag.act { background: #2a1d0f; color: #f0b464; border-color: #4a3316; }
dl { display: grid; grid-template-columns: max-content 1fr; gap: .35rem 1.2rem; margin: 0; }
dt { color: #7d8796; font-size: .85rem; }
dd { margin: 0; }
code, pre { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: .85rem; }
pre { background: #0b0f14; border: 1px solid #1d232c; border-radius: 8px; padding: .9rem 1rem;
      overflow-x: auto; white-space: pre-wrap; word-break: break-word; color: #c4cdd8; margin: .6rem 0 0; }
.ev { border: 1px solid #222a35; border-radius: 8px; padding: .9rem 1rem; margin-bottom: .9rem;
      background: #131820; }
.muted { color: #7d8796; }
footer { max-width: 52rem; margin: 3rem auto 0; color: #566070; font-size: .82rem;
         border-top: 1px solid #1d232c; padding-top: 1rem; }
"""


def _e(value: Any) -> str:
    """The only way anything reaches a page. Quotes included: a source URL is
    printed inside an attribute, and an attacker chooses the URL."""
    return html.escape(str(value), quote=True)


def _document(title: str, body: str) -> str:
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        f"<title>{_e(title)}</title><style>{_STYLE}</style></head>"
        f"<body><main>{body}</main>"
        "<footer>Glass Box — rendered from the ledger on disk. "
        "Every value on this page is escaped: the payloads shown here are bytes "
        "somebody else chose.</footer></body></html>"
    )


def _chain_banner(ledger: Ledger) -> str:
    problems = ledger.verify()
    if not problems:
        count = len(ledger.records())
        return (
            f"<div class='banner ok'><strong>{count} decision(s) verified: "
            "the chain holds.</strong></div>"
        )
    items = "".join(f"<li>{_e(problem)}</li>" for problem in problems)
    return (
        "<div class='banner bad'><strong>This ledger does not hold.</strong>"
        f"<ul>{items}</ul></div>"
    )


def _cell(key: str, value: str) -> str:
    return f"<div class='cell'><div class='n'>{_e(value)}</div><div class='k'>{_e(key)}</div></div>"


def render_index(ledger: Ledger) -> str:
    stats = ledger.stats()
    cells = [
        _cell("decisions", str(stats["decisions"])),
        _cell("asks", str(stats["asks"])),
        _cell("cost", f"${stats['cost_usd']:.4f}"),
    ]
    for tier, calls in sorted(stats["calls_by_tier"].items()):
        cells.append(_cell(f"{tier} calls", str(calls)))

    share = stats["changed_share"]
    escalation = (
        "nothing was escalated"
        if share is None
        else f"{stats['escalated']} of {stats['asks']} ask(s) escalated, "
             f"and the answer changed in {share:.0%} of them"
    )

    rows = []
    for position, record in enumerate(ledger.records(), start=1):
        actions = "".join(
            f"<span class='tag act'>{_e(action.get('kind', '?'))}</span>"
            for action in record.actions
        ) or f"<span class='tag'>{_e(record.outcome.get('action', 'none'))}</span>"
        rows.append(
            f"<li><a href='/decision/{position}'>"
            f"<span class='pos'>#{position}</span>"
            f"<span class='name'>{_e(record.name)}</span>{actions}"
            f"<span class='when'>{_e(record.started_at)}</span></a></li>"
        )

    return _document(
        "Glass Box",
        "<h1>Decision ledger</h1>"
        f"<p class='sub'>{_e(ledger.path)}</p>"
        f"{_chain_banner(ledger)}"
        f"<h2>What the run cost</h2><div class='grid'>{''.join(cells)}</div>"
        f"<p class='sub' style='margin-top:.8rem'>{_e(escalation)}</p>"
        f"<h2>Decisions</h2><ol class='runs'>{''.join(rows)}</ol>",
    )


def _json_block(value: Mapping[str, Any] | Any) -> str:
    return f"<pre>{_e(json.dumps(value, indent=2, ensure_ascii=False))}</pre>"


def _evidence_block(ledger: Ledger, evidence_id: str) -> str:
    if ledger.store is None:
        return (
            "<div class='ev'><span class='muted'>"
            f"{_e(evidence_id)}<br>This ledger was opened without its evidence store, "
            "so the bytes behind this citation cannot be shown. Pass --evidence."
            "</span></div>"
        )
    try:
        item = ledger.store.get(evidence_id)
    except UnknownEvidence:
        return (
            "<div class='ev bad'><strong>Cited evidence the store does not have:</strong> "
            f"<code>{_e(evidence_id)}</code></div>"
        )

    text = item.payload.decode("utf-8", "replace")
    redacted = " <span class='tag'>redacted</span>" if item.redacted else ""
    return (
        "<div class='ev'>"
        f"<a href='{_e(item.source)}' rel='noreferrer noopener nofollow'>{_e(item.source)}</a>"
        f"{redacted}"
        f"<div class='muted'>fetched {_e(item.fetched_at)} · {_e(item.media_type)} · "
        f"sha256:{_e(item.payload_sha256[:16])}…</div>"
        f"<pre>{_e(text)}</pre></div>"
    )


def render_decision(ledger: Ledger, position: int) -> tuple[int, str]:
    records = ledger.records()
    if not 1 <= position <= len(records):
        return 404, _document(
            "Not found",
            f"<h1>No decision #{_e(position)}</h1>"
            f"<p class='sub'>This ledger holds {len(records)}. "
            "<a href='/'>Back to the ledger</a></p>",
        )

    record = records[position - 1]
    rule = (
        f"<code>{_e(record.rule_digest)}</code>"
        if record.rule_digest
        else "<span class='muted'>no rule recorded — a replay of this decision would be "
             "checked against an assumed rule</span>"
    )

    asks = "".join(
        "<div class='ev'>"
        f"<span class='tag'>{_e(ask.get('tier'))}</span> "
        f"{_e(ask.get('calls', 0))} call(s) · ${float(ask.get('cost_usd', 0.0)):.4f}"
        + (
            f" · <strong>escalated from {_e(ask.get('escalated_from'))}</strong>"
            f" and the answer {'changed' if ask.get('changed_on_escalation') else 'did not change'}"
            if ask.get("escalated_from")
            else ""
        )
        + "</div>"
        for ask in record.asks
    ) or "<p class='muted'>No model was asked anything.</p>"

    actions = "".join(_json_block(dict(action)) for action in record.actions) or (
        "<p class='muted'>Nothing was done.</p>"
    )
    evidence = "".join(_evidence_block(ledger, i) for i in record.evidence) or (
        "<p class='muted'>This decision cited no evidence.</p>"
    )

    return 200, _document(
        f"#{position} {record.name}",
        f"<h1>#{_e(position)} · {_e(record.name)}</h1>"
        f"<p class='sub'><a href='/'>← the ledger</a></p>"
        "<h2>Identity</h2>"
        "<dl>"
        f"<dt>started</dt><dd>{_e(record.started_at)}</dd>"
        f"<dt>agent</dt><dd><code>{_e(record.agent_version)}</code></dd>"
        f"<dt>rule</dt><dd>{rule}</dd>"
        f"<dt>chain</dt><dd><code>{_e(record.chain[:23])}…</code></dd>"
        "</dl>"
        f"<h2>What it read</h2>{evidence}"
        f"<h2>What it asked</h2>{asks}"
        f"<h2>What it did</h2>{actions}"
        f"<h2>Outcome</h2>{_json_block(dict(record.outcome))}",
    )


def render(path: str, ledger: Ledger) -> tuple[int, str]:
    """Routing, as a pure function: a path in, a status and a page out."""
    if path in ("/", "/index.html"):
        return 200, render_index(ledger)

    if path.startswith("/decision/"):
        raw = path[len("/decision/"):].strip("/")
        if raw.isdigit():
            return render_decision(ledger, int(raw))

    return 404, _document(
        "Not found",
        f"<h1>Nothing at {_e(path)}</h1><p class='sub'><a href='/'>Back to the ledger</a></p>",
    )


class _Handler(BaseHTTPRequestHandler):
    server_version = "glassbox"

    def __init__(self, *args: Any, ledger: Ledger, **kwargs: Any) -> None:
        self._ledger = ledger
        super().__init__(*args, **kwargs)

    def do_GET(self) -> None:  # noqa: N802 - the name http.server requires
        # Re-read on every request rather than caching: a ledger being written
        # while it is watched is the interesting case, and a viewer showing a
        # stale chain would be worse than no viewer.
        status, body = render(self.path.split("?", 1)[0], self._ledger)
        payload = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        # It renders no markup from the data and runs no script; the header
        # says so, so a browser enforces it even if this code one day slips.
        self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args: Any) -> None:
        """Silent: the terminal is where the auditor is reading the CLI."""


def serve(ledger: Ledger, *, host: str = "127.0.0.1", port: int = 8000) -> None:
    server = HTTPServer((host, port), partial(_Handler, ledger=ledger))
    print(f"Glass Box on http://{host}:{port}  (ctrl-c to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("")
    finally:
        server.server_close()
