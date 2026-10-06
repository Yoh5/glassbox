# Retour produit — Nebius Token Factory et les modèles NVIDIA

Le formulaire demande *"feedback on Token Factory, AI Cloud, and the NVIDIA
tools you used"*. Tout ce qui suit a été rencontré en construisant
`glassbox/nebius.py` et en lançant la mesure d'escalade ; rien n'est une
impression générale.

---

## What worked well

```
The usage block. Every chat completion comes back with prompt_tokens and
completion_tokens, so a cost is read off the response rather than estimated
over the prompt. That sounds small and it is the reason this project exists in
the form it does: Glass Box records what a decision cost, and a recorded number
that drifts from the bill is worse than no number. We never had to write a
tokenizer, and the figure in the ledger is the provider's own count.

The OpenAI-compatible surface. `POST /v1/chat/completions` with a bearer token
is 40 lines of urllib and no SDK, which means the client has zero third-party
dependencies and can be read in full by anyone auditing what we send. For a
project about auditability, that is not a convenience, it is the point.

GET /v1/models works and is honest. It returns exactly what the account can
call, which is how we confirmed our tier ids and how `glassbox models` tells a
user which of the three tiers their key actually reaches.

Three Nemotron tiers on public endpoints, with a factor of twelve between the
cheapest and the dearest on output ($0.24 and $3.00 per million). That spread is
what makes a cheap-first router worth building and worth measuring. On twelve
questions of rising ambiguity, the 30B model answered Paris, 17 is prime and
seven continents alone; only the contested one — is a hot dog a sandwich — went
to the 550B. Total cost $0.0029.
```

## What needs work

```
1. The model ids on the product pages are not the ids the API accepts.
Two of the three tiers we use differ between what is displayed and what
GET /v1/models returns — a difference of case, or an extra prefix. Copying an
id from a product page gives a 404, and a 404 on a model id is indistinguishable
from a model that has been retired. We only got it right because we called
/v1/models and compared. Fix: show the API id on the model page, labelled as
such, or make the lookup case-insensitive.

2. Nemotron 3 reasons before it answers, and nothing warns you.
When max_tokens runs out inside the thinking, the response is well-formed and
`choices[0].message.content` is null. The first version of our client crashed
there. A long run would have died on one truncated answer — and the failure
reads as a bug in your own code, because the HTTP status is 200. The content is
in `reasoning_content`, which we found by printing the whole body. Fix: document
that content can be null on a reasoning model, say that reasoning_content holds
what was produced, and ideally return a finish_reason that distinguishes "ran
out inside the reasoning" from "ran out inside the answer".

3. Which models have a public endpoint is not discoverable before you try.
Llama-3_1-Nemotron-Ultra, Nano-Omni and Nano-V2-12b need a dedicated
deployment, which is a different setup and a different bill. We found out by
calling them. Fix: mark the dedicated-only models on the catalogue page, or
return a 4xx that says "dedicated deployment required" rather than a generic
not-found.

4. Per-model pricing is on the product pages and not in the API.
We hard-code three price pairs in `glassbox/nebius.py`, read off those pages, to
turn a usage block into dollars. Hard-coded prices go stale silently and we say
so in the code. Fix: expose price per million in GET /v1/models. It is the one
field that would let a cost recorder stay correct without a human re-reading a
page.
```

## Onboarding

```
Fast, and the measure of that is that the client is 40 lines of urllib with no
SDK. Key from the console, bearer token, OpenAI-compatible endpoint, first
completion inside ten minutes.

The hour that was not fast was spent on the two items above: a 404 from a model
id copied off a product page, and a null content field from a model that was
still thinking. Both are documentation gaps rather than API defects, which is
why they are worth reporting — they cost a newcomer an hour each and they cost
you nothing to fix.
```

## Would you build with these again

```
Yes, and for one specific reason beyond the models: the usage block makes the
cost of a decision a measured fact rather than an estimate. Glass Box publishes
one number — what escalating bought — and that number is only defensible
because the provider returns its own token counts.

The Nemotron tiers are also unusually well suited to a cheap-first router,
because the spread is large enough to matter and the three are close enough in
behaviour to make the cheap one a real first choice rather than a token one.
Our measurement is twelve questions, which is twelve questions and not a study —
it is published as measured, with the part we cannot separate from sampling
noise said out loud.

What would make us build more here: price in the models endpoint, and a
documented contract for reasoning models. Both are small, and both are the
difference between a cost recorder that stays true and one that quietly drifts.
```
