# Glass Box — le dossier Devpost

Piste : **Coding and Agentic Engineering**.
Échéance : **30 octobre 2026, 10:00 PDT**.

---

## Project name

```
Glass Box
```

## Elevator pitch (200 caractères max)

```
Your agents make decisions. This one tells you which, on what information, what
it cost, and whether anyone rewrote the record afterwards.
```

138 caractères. L'alternative, plus concrète et plus longue (188) :

```
A flight recorder for AI agents: every decision, the bytes it stood on, what it
cost, and a hash chain that makes a rewritten record visible. Measured on
Nemotron: $0.0029 for twelve asks.
```

---

## Story — les sept titres du gabarit Devpost

### Inspiration

Everyone is deploying agents. Nobody can say why their agent did what it did.

The tools we had traced *model calls* — the prompt, the response, the latency,
the cost. That is useful for debugging a phrasing and useless the day an agent
wrote to a file it should not have touched, sent a message it should not have
sent, or spent a thousand dollars in an afternoon. The three questions you ask
then have no answer:

1. **What information was this decision standing on?** Not *which prompt* —
   which document, fetched when, from what address.
2. **Would it do the same thing today?** Without a deterministic replay you
   cannot tell a bug from a sampling accident.
3. **Is this log telling the truth?** A log that can be edited afterwards is
   not evidence, it is testimony.

### What it does

A Python library you attach to an existing agent in three lines, plus a
read-only viewer.

- **Records decisions, not calls.** A decision carries what it read (the bytes,
  by hash), that it asked a model and at which tier, what it did, and what it
  cost. Deliberately not the prompt: the information a decision stood on is the
  evidence, addressed by content, and a prompt log is the thing every other tool
  already keeps.
- **Chains them.** Each record commits to the previous one, so removing or
  editing an entry breaks the chain and `glassbox verify` names the first
  record that does not hold — "something is wrong somewhere" is not a finding.
- **Replays.** `glassbox replay` re-runs the rule over the evidence each
  decision cited, and says plainly when that proves nothing.
- **Traces an action back to a byte.** `glassbox trace` walks from "the agent
  did X" to the document that caused it.
- **Measures what tiering costs and buys.** The router tries the cheap model
  first and escalates on a signal that means something — two samples
  disagreeing — and the ledger records which asks escalated and whether the
  answer changed.

Nothing in the viewer computes anything of its own: the chain banner is
`Ledger.verify()`, the totals are `Ledger.stats()`. The page cannot claim
something the command line would deny.

### How we built it

Python, no runtime dependencies at all — `json`, `hashlib`, `http.server`,
`urllib`. That is a decision and not an accident: an auditing tool whose own
supply chain is a dozen packages is arguing against itself, and anyone can read
in full what this one sends.

The model side is `glassbox/nebius.py`, 40 lines of `urllib` against **Nebius
Token Factory**, calling three **NVIDIA Nemotron 3** tiers — Nano 30B, Super
120B, Ultra 550B — on their public endpoints. Cost is computed from the `usage`
block the API returns, never estimated over the prompt: a recorded number that
drifts from the bill is worse than no number.

The viewer binds to `127.0.0.1`. A decision ledger is an agent's most sensitive
artifact, and the hosted demo for this submission is one published snapshot
that says so on its own page.

### Challenges we ran into

The two worst defects in this project were found by *using* it, not by reading
it, and neither was visible to the suite. Both were in the product's own thesis.

- **Our auditing tool wrote credentials into a ledger its design makes
  unerasable.** `redact.py` opens by explaining that an append-only, hash-chained
  journal cannot be scrubbed afterwards without breaking the chain, so a secret
  must be redacted *before* it is written. The recorder then wrote an action's
  parameters in raw — `act("call-api", token=...)` landed verbatim and sealed.
  The line immediately below it redacted the same dictionary for the outcome
  text: the copy was protected and the original was not. Found by pushing one
  secret through every channel into the ledger and grepping for it; evidence,
  refusals, outcomes and the error path were all clean. 186 tests were not,
  because not one of them put a secret in an action. Redaction now walks the
  structure — keys as well as values, nested dictionaries and lists — while
  `retries=3` stays the integer 3, because `str(fields)` would have fixed the
  leak and turned every number into text.
- **"The chain holds" was true of nine fields and nothing else.** The chain
  hashes an allowlist, so that adding an optional field would not invalidate
  every ledger already on disk. The cost of that choice is that a key *outside*
  the list is hashed by nothing: appending `"severity": "benign"` to a sealed
  record left `verify` reporting a chain that holds. Every test mutated a field
  the chain already knew about, so the gate could only fail in the direction it
  was built to fail in. `verify` now names the record and the unhashed fields
  and exits non-zero — without calling it an edit, because a newer writer may
  simply know a field this reader does not. It does not call the record intact
  either: a verifier that cannot account for part of a record has no business
  doing so.
- **The first real run found a bug in the escalation signal.** "Yellow" and
  "yellow" counted as a disagreement, and sent a question about the colour of a
  banana to a model that costs twelve times more, which confirmed the same
  answer. Comparison is normalised now — the *comparison* only; the recorded
  answer is always what the model actually wrote. Escalations fell from 5 to 2
  and cost from $0.0048 to $0.0029 on the same twelve questions.
- **Two runs at a non-zero temperature are not a controlled experiment.** The
  banana case is certain; the size of the saving is not, because part of that
  gap is sampling noise. Both numbers are published as measured, with that
  sentence next to them.
- **Nemotron reasons before it answers**, and when `max_tokens` runs out inside
  the thinking the API returns a well-formed response with `content: null`. Our
  client crashed there on the first attempt; a fourteen-day run would have died
  on one truncated answer. The text is in `reasoning_content`.
- **A model id copied from a product page is a 404.** Two of our three tiers
  differ between the displayed id and what `GET /v1/models` returns. We only got
  it right by calling the endpoint and comparing.
- **Temperature zero would have made the whole measurement meaningless.** The
  escalation signal is two samples disagreeing; at zero they never disagree, the
  check never fires, and a check that cannot fail proves nothing. The library
  refuses the setting rather than reporting a perfect agreement rate.

### Accomplishments that we're proud of

The numbers are measured on real models and read off the ledger afterwards with
`glassbox stats`, not printed at the time — which is the same discipline the
product asks of its users. Twelve asks, $0.0029, two escalations, and the answer
changed in half of them. The 30B model answered *Paris*, *17 is prime* and
*seven continents* alone; only *is a hot dog a sandwich* went to the 550B. That
is the whole idea working.

212 tests, no runtime dependencies, and every command that reads a ledger exits
non-zero when there is none — printing an empty table would read as "nothing
happened" rather than "nothing was recorded", which is the one confusion this
project exists to prevent.

### What we learned

**A record nobody can check is a story.** The hash chain was the easy part; the
hard part was making every surface refuse to overstate. The viewer recomputes
instead of caching. `replay` says when it proves nothing. The published snapshot
names what it is. Each of those started as a place where the tool would have
sounded more confident than it was entitled to be.

And one about measurement: our own escalation number was wrong the first time,
and it was wrong in the flattering direction — it made the expensive tier look
necessary. A project that publishes a saving has to be most suspicious of the
run that makes it look good.

And the one we will carry into the next project: **a suite proves the rules it
was written from, and only those.** Ours was green through both defects above,
and green for the same reason in each — every test mutated something the code
already knew to look at. The two holes were in what the code did *not* know to
look at, and the only way we found them was to behave like a user: push a secret
down every path that reaches the ledger, and edit a sealed record the way
someone covering their tracks would. Neither took an hour. Both were invisible
from inside the test suite that had grown to 186 cases around them.

### What's next for Glass Box

Recording a real agent in production rather than a measurement harness, an
exporter so a ledger can be anchored externally (the chain proves tampering,
not *when* a record was written), and the dedicated-endpoint Nemotron models,
which need a deployment rather than a public endpoint.

---

## What was significantly updated during the submission period

Le règlement demande, pour un projet antérieur, *"a written explanation of what
was significantly updated during the Submission Period"*. L'historique est la
preuve, pas l'affirmation :

| | |
|---|---|
| Premier commit | **25 septembre 2026** |
| Commits | 13, du 25 septembre au 6 octobre 2026 |
| Écrit avant le hackathon | rien |

Texte à coller :

```
Glass Box did not exist before this hackathon. The first commit is 25 September
2026 and the repository is the record.

What was built during the window, in the order it happened: the chained ledger
with redaction and the incident path; the cheap-first router and an escalation
signal that means something; replay, and the sentence that says when a replay
proves nothing; cost added up from the record rather than from what was printed
at the time; the first run against real Nemotron on Nebius Token Factory, which
found the bug in the escalation signal described above; thread-safe appending,
because a real agent writes from several threads; CI on the three Python
versions the packaging claims to support; a viewer for the reader who will not
type a command; a `models` command that shows what each tier costs; every
ledger-reading command exiting non-zero when there is no ledger; and the hosted
read-only snapshot that this submission links to.
```

---

## Built with

Relevé dans `pyproject.toml` (`dependencies = []`) et dans les imports :

```
python, nebius-token-factory, nvidia-nemotron, urllib, hashlib, json,
http-server, pytest, render
```

## Links to fill in at submission

- **Repository (public, Apache 2.0):** https://github.com/Yoh5/glassbox
- **Working demo:** https://glassbox-demo.onrender.com — instantané en lecture
  seule du registre mesuré. Vérifié le 8 octobre 2026 : la chaîne tient sur les
  12 décisions, et les totaux de la page (0,0029 $, 24 nano / 4 super / 2 ultra,
  2 escalades sur 12 dont 50 % ont changé de réponse) sont identiques à ceux que
  rend `glassbox stats runs/escalation/ledger.jsonl` en local.
  ⚠️ Render endort les services gratuits : prévoir ~30 s au premier chargement,
  et ouvrir le lien avant de le donner à un juré.
- **Video (public, YouTube, under 3 minutes):** à tourner
- **Upstream contribution:** à faire — voir le point C du plan

## Product feedback

Les quatre réponses du formulaire sont dans `submission/FEEDBACK.md`, et chacune
sort d'une friction rencontrée en construisant `glassbox/nebius.py`.
