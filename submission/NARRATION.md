# Vidéo Glass Box — script de tournage

Contrainte : **YouTube public, moins de 3 minutes**. Visé : **2 min 40**, pour
garder de la marge au montage.

Le script sert dans les deux cas — que tu captures l'écran et que je monte, ou
que je rende tout par le code. Les commandes sont celles du CLI réel
(`models`, `verify`, `trace`, `replay`, `stats`, `serve`), et les chiffres sont
ceux du registre mesuré, pas des exemples.

**Principe de montage : on ne pitche pas, on montre.** Chaque plan est une
commande et sa sortie. Un juré qui regarde trente vidéos reconnaît une démo
réelle d'un diaporama en cinq secondes.

---

## Plan 0 — la phrase, sur fond noir (0:00 → 0:08)

Texte à l'écran, pas de voix :

> **Un agent a pris douze décisions.**
> **Voici comment savoir lesquelles, pourquoi, et si le registre a été touché.**

*Pourquoi commencer par là :* la promesse en une phrase, et elle annonce le
plan final. Pas de logo, pas de musique montante, pas de « imaginez un
monde ».

---

## Plan 1 — l'agent tourne pour de vrai (0:08 → 0:45)

Terminal. Lancer le run d'escalade qui produit `runs/escalation/ledger.jsonl`.

Ce qu'on doit voir défiler : les décisions prises, les niveaux appelés
(nano → super → ultra), et le fait que **ça appelle un vrai modèle hébergé chez
Nebius**, pas un bouchon.

Légende incrustée, courte :

> *trois niveaux, escalade seulement quand la règle n'est pas sûre*

*À ne pas faire :* accélérer au point qu'on ne lise rien. Mieux vaut couper
une partie du run que de le rendre illisible.

---

## Plan 2 — ce que ça a coûté (0:45 → 1:05)

```
glassbox stats runs/escalation/ledger.jsonl
```

Les chiffres du registre mesuré, à l'écran tels qu'ils sortent :
**0,0029 $**, **24 nano / 4 super / 2 ultra**, **2 escalades sur 12**, dont
**50 % ont changé de réponse**.

Voix off ou légende, une phrase :

> *L'escalade a changé la réponse une fois sur deux. C'est mesuré, pas supposé.*

*Pourquoi ce plan existe :* il prouve que l'outil répond à « combien ça a
coûté » sans qu'on lise une ligne de code — et le « une fois sur deux » est
honnête, il ne dit pas que l'escalade sert toujours.

---

## Plan 3 — pourquoi cette action (1:05 → 1:35)

```
glassbox trace runs/escalation/ledger.jsonl <action>
glassbox replay runs/escalation/ledger.jsonl
```

`trace` remonte des décisions à l'action, avec les preuves citées. `replay`
rejoue la règle sur ces mêmes preuves et montre qu'elle décide pareil.

Légende :

> *la décision, ses preuves, et la même règle rejouée dessus*

---

## Plan 4 — le plan qui porte la vidéo (1:35 → 2:20)

**C'est le seul plan qu'il ne faut pas rater.**

```
glassbox verify runs/escalation/ledger.jsonl
```

→ la chaîne tient sur les douze décisions.

Puis, à l'écran, **modifier un seul octet** dans le registre scellé — ou
ajouter un champ que rien ne hache, par exemple `"severity": "benign"` — et
relancer :

```
glassbox verify runs/escalation/ledger.jsonl
```

→ le vérificateur **nomme l'enregistrement** et dit ce qui ne tient plus.

Légende, en deux temps :

> *un registre qu'on peut modifier sans que ça se voie est un témoignage,*
> *pas une preuve*

*Pourquoi c'est le climax :* tout le reste est de l'instrumentation. Ça, c'est
la propriété que le produit vend, et elle se démontre en dix secondes. Montrer
la modification à l'écran — pas en parler — est ce qui distingue cette vidéo de
toutes celles qui affirment « inviolable ».

---

## Plan 5 — la page, pour qui ne tapera rien (2:20 → 2:35)

```
glassbox serve runs/escalation/ledger.jsonl
```

ou directement la démo en ligne : **https://glassbox-demo.onrender.com**

Faire défiler la page : les décisions, les coûts, la chaîne vérifiée.

⚠️ **Render endort les services gratuits.** Ouvrir le lien 30 secondes avant de
tourner, sinon on filme un écran de chargement.

---

## Plan 6 — fin (2:35 → 2:40)

Texte, fond noir :

> **220 tests. Apache 2.0.**
> **github.com/Yoh5/glassbox**

Pas de remerciements, pas de « merci d'avoir regardé ».

---

## Ce qu'il faut capturer, si c'est toi qui enregistres

- **Terminal plein écran**, police grossie (18-20 pt au moins) : un juré
  regarde peut-être sur un téléphone.
- **Thème sombre**, et une seule fenêtre. Pas de barre de tâches, pas de
  notifications.
- **Une prise par plan**, sans chercher à tout enchaîner. Je recolle.
- Ne corrige pas les hésitations : coupe et refais le plan. Un plan refait se
  monte, un plan hésitant ne se sauve pas.
- Capture en **1920×1080**, et ne redimensionne rien avant de me l'envoyer.

## Ce que je fais ensuite

Coupes, légendes incrustées, calage des plans sur la durée, titres de début et
de fin, et l'export final sous 3 minutes. Si tu veux une voix off, écris-la ou
lis le texte des plans — je ne peux pas la dire.

## Si c'est moi qui rends tout par le code

Même découpage, mais les plans 1 à 4 sont composés image par image depuis la
**sortie réelle** des commandes : je lance, je capture le texte, je le typographie
avec un effet de frappe. Le plan 5 passe par des captures de la page web.
Honnête, exact, et sans un seul pixel inventé — mais plus sobre qu'une vraie
capture. Un encodeur est nécessaire (`imageio-ffmpeg`, ~25 Mo).
