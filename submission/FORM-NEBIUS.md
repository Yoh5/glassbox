# Additional info — les réponses à coller

Tout ce qui suit sort du dépôt ou d'une course mesurée. Les deux notes sur dix
sont des jugements, pas des mesures : elles sont justifiées pour que tu puisses
les déplacer en connaissance de cause.

---

## Which track? — **Best Apps and Agents**, pas « Coding and Agentic Engineering »

`SUBMISSION.md` annonçait la piste *Coding and Agentic Engineering* depuis le
cadrage. **C'est la mauvaise**, et le règlement la définit noir sur blanc :

> *Coding and Agentic Engineering Track — Build coding agents and developer
> tools: **agents that write, run, and test code** in Token Factory.*

Glass Box n'écrit pas de code, n'en exécute pas, n'en teste pas. Il enregistre
ce qu'un agent a décidé. Et l'étape un du jugement est un **pass/fail** sur
« le projet correspond-il vraiment au thème de la piste, et non un
rebadgeage superficiel ». Se tromper de piste, c'est risquer d'être écarté
avant que quoi que ce soit d'autre soit lu.

L'autre piste décrit littéralement ce que fait le routeur :

> *Best Apps and Agents Track — … **Reach for Nemotron 3 Ultra when you need
> serious reasoning, and let Nano or Super handle the fast, everyday calls, so
> your app stays responsive and your credits stretch further.***

C'est le routeur « le moins cher d'abord » de Glass Box, mot pour mot. Et il ne
se contente pas de le faire : il **mesure si ça valait le coup**, ce qui donne
la trouvaille inconfortable que personne ne publie — l'escalade chère n'a rien
changé, la moins chère si.

---

## Is your project new or existing prior to August 26, 2026?

**New.**

Le premier commit du dépôt est daté du **25 septembre 2026**, soit un mois
après l'ouverture de la période de soumission. Rien n'est repris d'un projet
antérieur. (`git log --reverse` le montre, et le champ d'explication qui suit
peut rester vide.)

---

## Public code repository

```
https://github.com/Yoh5/glassbox
```

Apache 2.0, détectée par GitHub dans l'encart « About ». Le README porte les
instructions d'installation, et une section dit où Nemotron et Token Factory
interviennent.

## Working demo

```
https://glassbox-demo.onrender.com
```

> Instance gratuite : le premier chargement après une période calme prend une
> vingtaine de secondes (21,5 s mesurées le 15/10/2026). Un workflow
> `keep-awake` la tient éveillée, mais ouvre le lien toi-même avant de le
> donner.

---

## Which model(s) did you use, and why did you choose that size/variant?

```
All three public Nemotron 3 tiers, because the project is about what choosing
between them costs and buys:

- nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B   $0.06 / $0.24 per M tokens
- nvidia/nemotron-3-super-120b-a12b       $0.30 / $0.90
- nvidia/Nemotron-3-Ultra-550b-a55b       $1.00 / $3.00

Those are the ids GET /v1/models returns, not the ones the product pages show;
two of the three differ, and we only got it right because we compared.

We did not pick one size. The product is a router that asks the 30B model
first and escalates only on a signal that means something, so the point was to
have a real spread to escalate across: a factor of twelve between the cheapest
and the dearest on output is what makes the question worth measuring at all.

On a run of twelve questions of rising ambiguity, Nano answered most of them
on its own -- Paris, 17 is prime, seven continents. Two escalated. The whole
run cost $0.0029.
```

## How would you rate Nemotron's output quality for your use case? (1–10)

**8** — et voici pourquoi ce n'est ni 10 ni 6 :

```
8.

What worked: on twelve questions the 30B tier answered the factual ones
correctly and on its own, which is the whole premise of a cheap-first router
and not something we assumed. Instruction-following was good enough that we
never needed a system prompt.

What cost us an afternoon is not quality, it is a behaviour nobody warns you
about: Nemotron 3 reasons before it answers. When max_tokens runs out inside
the thinking, the response is a well-formed 200 and
choices[0].message.content is null. Our first client crashed there, and the
failure reads as a bug in your own code. The text is in reasoning_content.
That is an operational sharp edge rather than a quality problem, and it is the
single thing that would move this score to a 9 if documented.

The one thing we cannot claim: twelve questions is twelve questions, not a
study. We publish it as measured, and we say out loud which part we cannot
separate from sampling noise.
```

## Did you fine-tune, prompt-engineer, or use Nemotron out of the box?

```
Out of the box, deliberately, and one setting is load-bearing.

No fine-tuning. No system prompt. One user message, temperature 0.7,
max_tokens 512. The reason is that the product measures the model rather than
dressing it: if we had tuned a prompt per tier, the comparison between tiers
would be measuring our prompt-writing, not the models.

The one choice that is not a default is temperature, and it is enforced in
code rather than left to a comment. The router's escalation signal is two
samples of the cheap tier disagreeing with each other. At temperature 0 two
samples never disagree, so the signal is silently dead and the router quietly
becomes "always use the cheap tier". glassbox/nebius.py raises if temperature
is zero or below, with that sentence as the message.

The other deliberately small thing: what counts as "the same answer" when two
samples are compared. Case and trailing punctuation are not disagreements --
measured on a real run, where "Yellow" and "yellow" escalated a question about
the colour of a banana, and would have charged a 550B model for it.
```

## How did Nemotron's performance compare to other models you've used?

```
Honestly: we did not run a controlled comparison against another provider, so
we are not going to claim one. What would make such a claim worth anything --
same questions, same sampling, same normalisation, enough repetitions to
separate the result from noise -- is exactly the work we did inside the
Nemotron family and did not do across families.

What we did measure is the comparison the hackathon is actually about, between
the three tiers, and the result is uncomfortable enough to be worth reporting:

- #08, super -> ultra, $0.0016: the answer did NOT change.
- #11, nano -> super, $0.0008: the answer DID change.

The expensive escalation bought nothing. The cheap one bought the answer.
Paying more did not buy a different answer, and without a ledger nobody would
be able to tell -- which is the finding the project exists to make possible,
and it happens to be about Nemotron.
```

## Which Nebius platform capabilities were most valuable, and how?

```
Token Factory's inference API, and one field in it above everything else.

The usage block. Every chat completion returns prompt_tokens and
completion_tokens, so a cost is read off the response rather than estimated
over the prompt. That sounds small and it is the reason this project exists in
the form it does: Glass Box records what a decision cost, and a recorded number
that drifts from the bill is worse than no number at all. We never wrote a
tokenizer. The figure in the ledger is the provider's own count, and that is
what makes the one number we publish -- what escalating bought -- defensible.

The OpenAI-compatible surface. POST /v1/chat/completions with a bearer token
is forty lines of urllib and no SDK, which is why the whole project has zero
third-party runtime dependencies and anyone auditing what we send can read the
client in full. For a project about auditability that is not a convenience,
it is the point.

GET /v1/models, which returns exactly what the account can actually call. It
is how we confirmed our three tier ids, and `glassbox models` now uses it to
tell a user which tiers their own key reaches rather than failing later.

To be precise about what we did not use: this project calls the Token Factory
inference API only. No GPU instance types, no Serverless Jobs, no Serverless
Endpoints, no DevPods. An agent recorder has nothing to put on a GPU, and
claiming otherwise would be easy and false.
```

## How likely are you to recommend running Nemotron on Nebius? (1–10)

**9.**

```
9.

For one specific reason beyond the models: the usage block makes the cost of a
decision a measured fact rather than an estimate. Anyone building something
that has to report what it spent gets that for free here.

And the Nemotron tiers are unusually well suited to a cheap-first router,
because the spread is large enough to matter and the three are close enough in
behaviour that the cheap one is a real first choice rather than a token one.

Not a 10 only because of the two documentation gaps below, both of which cost
a newcomer an hour and cost you nothing to fix.
```

## Experience running Nemotron inference on Nebius vs other environments? (1–10)

**8.**

```
8.

Onboarding was fast, and the measure of that is the client: forty lines of
urllib, no SDK. Key from the console, bearer token, OpenAI-compatible
endpoint, first completion inside ten minutes.

The hour that was not fast went on two things, and neither is an API defect:

1. The model ids on the product pages are not the ids the API accepts. Two of
   our three tiers differ -- a case difference, or an extra prefix. Copying an
   id from a product page gives a 404, and a 404 on a model id is
   indistinguishable from a model that has been retired.

2. Which models have a public endpoint is not discoverable before you try.
   Llama-3_1-Nemotron-Ultra, Nano-Omni and Nano-V2-12b need a dedicated
   deployment, which is a different setup and a different bill. We found out
   by calling them.
```

## What additional features or improvements would have made it more effective?

```
Three, in the order they cost us time.

1. Price per million in GET /v1/models. We hard-code three price pairs read
   off the product pages, to turn a usage block into dollars. Hard-coded
   prices go stale silently, and we say so in the code because we could not
   fix it. This is the one field that would let a cost recorder stay correct
   without a human re-reading a page -- and cost is the thing your usage block
   already almost solves.

2. A documented contract for reasoning models. Say that content can be null,
   say that reasoning_content holds what was produced, and return a
   finish_reason that distinguishes "ran out inside the reasoning" from "ran
   out inside the answer". A long unattended run dies on one truncated answer
   otherwise, with an HTTP 200.

3. Mark the dedicated-only models on the catalogue, or return a 4xx that says
   "dedicated deployment required" rather than a generic not-found.

All three are documentation or one field. None requires changing a model.
```

## What do you most hope to see from the Nemotron team next?

```
Stable, published API ids that match the product pages, and a stated contract
for reasoning output -- the two things that turn an afternoon of guessing into
ten minutes.

Beyond that: published behaviour on the question this project ended up
measuring. Everyone ships tiers and tells you to escalate when the task is
hard. Nobody publishes how often escalating actually changes the answer. Our
run says the expensive escalation changed nothing and the cheap one changed
everything -- on twelve questions, which is twelve questions. A team with the
models and the volume could answer that properly, and it would be the most
useful number anyone could give a developer choosing a tier.
```

## Did you use Tavily in your project?

**No.** Vérifié : aucune occurrence de `tavily` dans le dépôt. Le projet ne
fait aucun appel de recherche web — ce serait une réponse fausse pour gagner
une case, et la qualification exige un appel réel à l'exécution.

## Builders & Brews — IRL Events City

À laisser vide, sauf si tu assistes vraiment à l'un des vingt événements
physiques. C'est une case d'éligibilité à un prix de ville, pas une
déclaration de résidence.

---

## Which AI tools have you leveraged while working on this project?

```
Three different things, kept apart on purpose, because this project's whole
argument is about which of them is allowed to decide anything.

1. NVIDIA Nemotron 3 inside the product, through Nebius Token Factory. Three
   tiers behind a router that asks the cheapest first and escalates only when
   two samples of that tier disagree. The model answers questions; it never
   decides what gets written to the ledger, and it cannot reach the ledger at
   all.

2. Claude (Claude Code) as a coding assistant, as the rules allow: library
   code, the 329-test suite, the viewer, the documentation and the video
   renderer. Every design decision, every published figure and this submission
   are mine, and I take responsibility for them.

3. A synthetic voice for the demo video (edge-tts). No human voice is
   recorded, there is no music, and the video says so.

What is not AI-generated: every figure in the video and on the cover image is
read from the run's own ledger at render time, and the verifier's refusal
shown on screen is executed while the video renders rather than copied from an
earlier run. The chain diagram is drawn from the real record hashes.
```

## Describe the level of learning you derived / Did you gain AI value for your career?

Ce sont des listes déroulantes, et c'est ton jugement, pas le mien. Ce que la
construction a réellement appris, si tu veux une réponse appuyée : le piège du
raisonnement tronqué (un 200 avec `content` à `null`), le fait qu'un routeur
d'escalade a besoin d'une température non nulle pour que son signal existe, et
qu'une escalade chère peut ne rien acheter du tout — ce qu'on ne peut constater
qu'en enregistrant.

## Upload a File

Facultatif, et rien n'y est obligatoire. S'il faut mettre quelque chose, le
plus utile pour un juré est `docs/devpost-cover.png` ou une capture du
vérificateur refusant le registre altéré — mais la vidéo et le dépôt portent
déjà les deux.
