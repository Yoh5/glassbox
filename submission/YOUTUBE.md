# La vidéo sur YouTube — titre, description, chapitres

Le règlement Nebius exige une vidéo **publique sur YouTube**, de **moins de
trois minutes**, sans musique sous droits. Tout ce qui suit est en anglais :
c'est ce que le juré lit.

Deux choses que la page YouTube doit faire, et qu'on oublie parce qu'on pense
d'abord à la vidéo :

- **être lisible sans le son.** Un juré qui parcourt des dizaines de projets en
  regarde une partie en silence. La description doit donc dire ce que la vidéo
  montre, pas inviter à la regarder.
- **porter les liens.** C'est la seule page de la soumission qu'on atteint
  depuis l'extérieur de Devpost.

---

## Titre (83 caractères — la limite est 100)

```
Glass Box: an agent's decisions, sealed. Edit one record and the verifier names it.
```

L'alternative, si tu préfères nommer la technologie d'entrée — « Technological
Implementation » est un quart de la note, et Nemotron y est cité (77) :

```
Glass Box: a tamper-evident ledger for AI agent decisions, on NVIDIA Nemotron
```

---

## Description — à coller telle quelle

```
Everyone is deploying agents. Nobody can say why their agent did what it did.

The tools we had trace model calls: the prompt, the response, the latency, the
cost. That is useful for debugging a phrasing, and useless the day an agent
wrote to a file it should not have touched or spent a thousand dollars in an
afternoon. Glass Box records the decision instead.

A decision carries what it read, addressed by content hash, that it asked a
model and at which tier, what it did, and what it cost. Each record commits to
the one before it, so a record rewritten afterwards is visible rather than
silent.

What the video shows, on a real run of twelve decisions:

· One record in full, including prev, the hash of the record before it.
· The twelve links drawn with their real tiers and their real costs. The
  running total on screen is summed from the records being drawn, so it cannot
  say one thing while the chain says another.
· Both escalations, side by side. The expensive one, super to ultra at
  $0.0016, changed nothing. The cheap one, nano to super at $0.0008, changed
  the answer. Paying more did not buy a different answer, and without the
  ledger nobody could know that.
· One field added to a sealed copy, and nothing else touched. No hash covers
  it, so the chain breaks at that record. The verifier does not report that the
  log looks fine: it names the record it cannot vouch for. That refusal is
  executed while the video renders, not copied from an earlier run.
· The five commands that are the whole audit surface.

Twelve decisions, $0.0029, on NVIDIA Nemotron 3 through Nebius Token Factory.
329 tests, no runtime dependencies, Apache 2.0.

CHAPTERS
0:00 Twelve decisions, and nobody can say which
0:11 A log you can edit is testimony, not proof
0:21 One record, in full
0:37 Each decision seals the one before
0:57 What the run cost
1:08 Two escalations, two outcomes
1:23 One field added to a sealed copy
1:47 What an auditor types
2:01 Glass Box

LINKS
Code (Apache 2.0): https://github.com/Yoh5/glassbox
Live viewer: https://glassbox-demo.onrender.com
Upstream: https://github.com/nebius/token-factory-cookbook/pull/73 and issue #74

BUILT ON
NVIDIA Nemotron 3 (Nano 30B, Super, Ultra) served by Nebius Token Factory, for
the Nebius x NVIDIA Global AI Hackathon.

The narration is a synthetic voice. No human voice is recorded, and there is no
music. Every figure on screen is read from the run's own ledger at render time.
```

---

## Avant de publier

- **Visibilité : publique.** Le règlement dit *publicly visible on YouTube*.
- **Les horodatages des chapitres sont ceux du montage réel**, imprimés par
  `python submission/video/keynote.py` à la fin du rendu. Si tu changes une
  phrase de `NARRATION`, les durées bougent : recopie la liste que le script
  réaffiche, sinon un chapitre tombe au mauvais endroit et un juré qui clique
  apprend quelque chose sur le soin porté au reste.
- **Sous-titres** : laisse YouTube les générer, puis **relis-les**. Il massacre
  les montants (`$0.0029`) et écrit « Nemotron » n'importe comment.
- **Pas de musique**, le règlement l'interdit explicitement — et il n'y en a
  pas dans le rendu.
- La dernière ligne sur la voix de synthèse n'est pas de la modestie : elle
  répond à la question avant qu'elle soit posée, et un gagnant d'un hackathon
  AWS a pris le bronze avec une voix Polly déclarée.
- **Le lecteur en ligne dort.** C'est une instance gratuite : le premier
  chargement après une période calme prend une vingtaine de secondes (21,5 s
  mesurées le 15/10/2026). Ouvre le lien toi-même avant de le donner, et le
  workflow `keep-awake` s'occupe du reste.
