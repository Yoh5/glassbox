# Glass Box — cadrage

**Pour** : Nebius x NVIDIA Global AI Hackathon, piste *Coding and Agentic Engineering*.
**Échéance** : 30 octobre 2026, 10:00 PDT. **Solo.** Écrit le 25 septembre 2026.

> **Glass Box — vos agents prennent des décisions ; celui-ci vous dit lesquelles, pourquoi,
> avec quelles informations, et ce que ça a coûté. Et si quelqu'un réécrit l'histoire, ça se
> voit.**

---

## 1. Le problème, et pour qui

Tout le monde déploie des agents. Personne ne peut dire pourquoi son agent a fait ce qu'il a
fait.

Les outils actuels tracent des *appels au modèle* : le prompt, la réponse, la latence, le
coût. Utile pour déboguer une formulation. Inutile le jour où un agent a écrit dans un
fichier qu'il ne devait pas toucher, envoyé un message qu'il ne devait pas envoyer, ou
dépensé mille dollars en un après-midi. Les trois questions qu'on pose alors n'ont pas de
réponse :

1. **Sur quelle information cette décision reposait-elle ?** Pas « quel prompt », mais quel
   document, récupéré quand, à quelle adresse.
2. **Referait-elle la même chose aujourd'hui ?** Sans rejeu déterministe, on ne peut pas
   distinguer un bug d'un aléa.
3. **Est-ce que ce journal dit la vérité ?** Un journal modifiable après coup n'est pas une
   preuve, c'est un témoignage.

**L'audience** : les équipes qui mettent un agent en production et qui devront un jour
expliquer un incident à quelqu'un — un client, un responsable conformité, un juge. C'est
aussi exactement le public de ce hackathon : les juges sont des ingénieurs NVIDIA et des
relations développeurs qui déploient des agents toute la journée.

## 2. Ce que c'est, et ce que ce n'est pas

Une bibliothèque Python qu'on branche sur un agent existant en trois lignes, plus un
visualiseur web.

**C'est** : un enregistreur de décisions inviolable, avec rejeu déterministe et traçabilité
d'incident.

**Ce n'est pas** : un outil d'observabilité de plus (il n'enregistre pas des appels, il
enregistre des décisions), ni un framework d'agents (il ne dit pas comment écrire l'agent),
ni un tableau de bord de coûts (le coût y est un attribut, pas le sujet).

## 3. Les trois choses qu'aucun outil ne fait aujourd'hui

### a. La chaîne de hachage — le journal devient une preuve

Chaque enregistrement contient le hachage du précédent. On ne peut ni réécrire une décision,
ni en supprimer une, ni en insérer une après coup sans casser la chaîne. `glassbox verify`
le dit en une seconde.

C'est le mécanisme de Runway transposé : là-bas, chaque course porte l'empreinte de sa
politique et la version du code qui a décidé, et `verify-record` rejoue la décision sur les
faits enregistrés pour prouver qu'elle en découle.

### b. La traçabilité d'injection — la réponse à incident qui manque

C'est le cœur sécurité, et c'est le problème du moment : un agent qui lit une page web, un
PDF ou un e-mail ingère du contenu que personne ne contrôle. L'injection de prompt est le
n° 1 de l'OWASP LLM Top 10, et aujourd'hui, quand un agent dérape, **personne ne peut dire
quelle page l'a fait dérailler.**

Glass Box le peut : chaque décision cite ses preuves par empreinte, et chaque preuve garde
sa source, son horodatage de collecte et sa charge brute. On remonte de l'action fautive à
l'octet de contenu qui l'a provoquée. Ce n'est pas une protection — c'est de la réponse à
incident, et c'est ce qui manque.

### c. Le routage mesuré Nano → Super → Ultra

Leur propre texte invite à répartir les appels entre les étages Nemotron. Glass Box en fait
une **mesure**, ce que personne ne publie :

- **Nano** répond en premier.
- Escalade vers **Super** puis **Ultra** sur un signal déterministe, pas sur une confiance
  auto-déclarée : on échantillonne deux fois le petit modèle, et si les deux réponses
  divergent — ou si la réponse ne cite aucune preuve, ou ne respecte pas le schéma — la
  question monte d'un étage.
- Le visualiseur affiche, sur la série : **le taux d'escalade, le coût évité, et le chiffre
  qui intéresse tout le monde — dans quel pourcentage des escalades la réponse a réellement
  changé.**

Si Ultra donne le même résultat que Nano huit fois sur dix, c'est une information que toutes
les équipes veulent et que personne ne mesure. Elle sort gratuitement de l'enregistrement.

## 4. Architecture

```
  agent (n'importe lequel)
        |
   glassbox.Recorder ──── evidence store (content-addressed, horodaté, brut conservé)
        |                        |
   router Nano/Super/Ultra ──────┤   Nebius Token Factory
        |                        |
   decision records ─── hash chain ─── write-once storage
        |
   glassbox verify   (CLI, rejeu déterministe + intégrité de chaîne)
        |
   viewer (FastAPI + HTML statique, déployé sur Nebius Serverless Endpoints)
```

**L'API, telle qu'on veut l'écrire** :

```python
from glassbox import Recorder

rec = Recorder(run="daily-triage", agent_version=git_sha())

with rec.decision("summarise-page") as d:
    page = d.evidence(source=url, payload=html)          # haché, horodaté, conservé
    thesis = d.ask("Summarise and list actions",          # routé, enregistré, coût capturé
                   cites=[page], floor="nano")
    d.act("write-file", target="notes.md", reason=thesis.reason)
```

Ce que la bibliothèque garantit, et que l'agent n'a pas à gérer :

- toute preuve est hachée et conservée telle quelle avant d'être lue par un modèle ;
- tout appel modèle est enregistré avec sa requête, sa réponse, son étage et son coût ;
- **aucun secret n'atteint le journal** : rédaction à la frontière contre l'ensemble des
  identifiants connus, y compris ceux que les fournisseurs enfouissent dans l'URL — le piège
  déjà rencontré et corrigé dans Runway ;
- toute action déclarée est chaînée à la décision qui l'a produite. Une action sans décision
  derrière elle est signalée par `verify`, exactement comme une écriture non mappée dans
  Runway.

## 5. Le plan, huit jours

| Jour | Livrable |
|---|---|
| 1 | Format d'enregistrement, chaîne de hachage, magasin de preuves adressé par contenu |
| 2 | `Recorder` : décisions, preuves, actions, rédaction des secrets à la frontière |
| 3 | Routeur Nano/Super/Ultra sur Token Factory, avec capture du coût et du motif d'escalade |
| 4 | `glassbox verify` : intégrité de chaîne, rejeu déterministe, actions non mappées |
| 5 | Visualiseur : chronologie, détail d'une décision, preuves, étages, coûts |
| 6 | Visualiseur : vue série — taux d'escalade, coût évité, % d'escalades qui changent la réponse |
| 7 | Agent de démonstration + le scénario d'injection (voir §6), déploiement serverless |
| 8 | README, licence Apache 2.0, retour outillage, vidéo |

Marge volontairement absente du tableau : la vidéo se tourne le jour 8 et se retourne le 9
si elle est mauvaise. Rien d'autre n'est prévu ce jour-là.

**Hors périmètre, assumé** : pas d'intégration avec les frameworks d'agents existants
(LangChain, CrewAI) — un décorateur générique suffit ; pas de multi-utilisateur ; pas de
stockage géré, le visualiseur lit un dossier ou un compartiment.

## 6. La démonstration — trois moments, moins de trois minutes

**0:00 — 0:35 · Le problème, en le vivant.** Un agent banal résume une page web. La page
contient une injection cachée, trois lignes en blanc sur blanc, qui lui ordonnent de lire un
fichier local et de le recopier dans son résumé. L'agent obéit. Aucun commentaire : on
montre juste qu'il obéit.

**0:35 — 1:45 · La réponse.** On ouvre Glass Box. On clique sur la décision fautive. On voit
la preuve citée, son horodatage de collecte, sa source — et la ligne exacte qui a provoqué
l'action. On rejoue la décision : même entrée, même sortie, ce n'était pas un aléa. Puis on
modifie l'enregistrement pour effacer l'incident : `verify` casse et le dit.

**1:45 — 2:40 · Ce que ça coûte.** La vue série : 412 décisions, 87 % traitées par Nano, 11 %
montées à Super, 2 % à Ultra ; le coût évité ; et le chiffre qui fait réfléchir — sur les
escalades, la réponse n'a changé que dans une fraction des cas. Un mot sur Token Factory et
sur les modèles NVIDIA utilisés, comme leur règlement l'exige.

**2:40 — 2:55 · Une phrase.** Le dépôt, la licence, l'URL de démonstration.

## 7. La liste de soumission

- [ ] Dépôt public, **licence Apache 2.0 visible en haut de la page**
- [ ] README avec installation et mode d'emploi, et une section explicite sur l'usage de
      Nemotron et de Token Factory
- [ ] URL de démonstration qui répond (visualiseur avec une série d'exemple chargée)
- [ ] Vidéo YouTube publique ≤ 3 min, avec audio couvrant Token Factory et les modèles NVIDIA
- [ ] Piste choisie : *Coding and Agentic Engineering*
- [ ] Retour sur Token Factory et les outils NVIDIA (champ obligatoire, et il y a 10 × 100 $
      pour les meilleurs retours)
- [ ] **Déclarer honnêtement la réutilisation** : les mécanismes de chaîne, de rédaction et
      de rejeu viennent de `Yoh5/runway`, public. Le code de Glass Box est écrit pour ce
      hackathon ; la dette intellectuelle se dit, elle ne se cache pas.

## 8. Les risques, et ce qu'on en fait

| Risque | Réponse |
|---|---|
| Un outil de développeur séduit moins vite qu'une application grand public sur le critère « impact » | Le scénario d'injection : trente secondes où un juge se reconnaît |
| Le routage ne montre pas d'écart intéressant | Alors le chiffre lui-même est le résultat, et on le publie tel quel. Un résultat négatif mesuré vaut mieux qu'une promesse |
| Huit jours en solo, en parallèle d'autres échéances | Périmètre coupé d'avance (§5), et rien ne commence avant la réponse de Binance |
| « C'est juste de l'observabilité » | La réponse tient en trois mots que les autres n'ont pas : chaîne, rejeu, traçabilité d'injection |

## 9. Ce qui vient après

Le banc d'essai adverse (voir la mémoire `idee-banc-essai-adverse`) : il attaque, Glass Box
prouve le chemin qu'a pris l'attaque. Dans cet ordre, c'est une gamme cohérente — et le
second projet a déjà sa démonstration toute faite.
