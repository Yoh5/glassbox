# Glass Box passé à l'OWASP Top 10 for LLM Applications 2026

Fait le 8 octobre 2026, sur le code à `3248ef3`. Le classement OWASP 2026 a été
publié le 4 août 2026 et il est, pour la première fois, **ordonné contre des
incidents réels** plutôt que sur l'avis de praticiens.

Trois constats, trois points solides, quatre sans objet. Les constats d'abord.

---

## ⚠️ n° 8 — Exposition de contexte caché

**Le registre n'enregistre ni la question posée au modèle, ni sa réponse.**

```json
"asks": [{"tier": "nano", "cost_usd": 2.676e-05, "calls": 2,
          "escalated_from": null, "changed_on_escalation": null}]
```

Il porte **qu'**un modèle a été interrogé, à quel palier, pour combien. Un
auditeur qui lit le registre ne peut pas reconstituer ce que l'agent a demandé
ni ce qu'on lui a répondu.

**Et deux documents affirment le contraire.** `submission/SUBMISSION.md:56` :
*« A decision carries what it read (the bytes, by hash), **what it asked a
model**, what it did, and what it cost. »* Et `README.md:93` : *« what it read,
what it asked and at which tier, what it did. »*

**Le dessin est défendable, la formulation ne l'est pas.** `README.md:12`
revendique explicitement de se distinguer des traceurs de prompt — *« Not which
prompt — which document, fetched when, from where »* — et c'est un choix
cohérent : l'information sur laquelle la décision reposait est dans les preuves,
adressées par contenu. Mais alors il ne faut pas écrire ailleurs qu'on
enregistre la question.

C'est exactement la classe de défaut que ce projet existe pour détecter chez les
autres : **une page qui affirme ce que la ligne de commande dément.**

**À faire :** corriger les deux phrases. Et décider si l'omission reste un choix
— auquel cas le dire — ou si un condensé de la question (longueur, hachage)
mérite d'entrer au registre, ce qui permettrait de prouver que deux décisions
ont posé la même question sans jamais stocker son texte.

## ⚠️ n° 6 — Consommation non bornée

**Aucun plafond de dépense.** Le routeur boucle sur les paliers × les
échantillons sans budget total. Un appel isolé est borné — `max_tokens=512`,
délais de 60 et 120 secondes — mais rien n'arrête une série.

Le paradoxe est que **le projet mesure le coût par appel et par décision**. Il a
la donnée pour poser un plafond et ne le pose pas. Un `max_cost_usd` sur le
`Router`, qui refuse plutôt que de dépasser, serait quelques lignes.

## ⚠️ n° 1 — Injection de prompt (partiel)

Glass Box n'est pas vulnérable : c'est l'outil qui **enregistre** une injection
réussie, et `examples/injected_page.py` fait précisément la démonstration.

Mais `ask(prompt)` prend une chaîne unique. **La bibliothèque n'offre aucun
moyen de passer une preuve comme donnée plutôt que comme texte de prompt**, et
son propre exemple interpole la page dans la question :

```python
answer = d.ask(f"Summarise this page: {page.payload.decode()}")
```

Un `ask(instruction, evidence=[...])` qui séparerait les deux à la construction
du message rendrait la distinction impossible à oublier. En l'état, l'exemple
enseigne le geste dangereux.

---

## ✅ Ce qui tient

**n° 4 — Chaîne d'approvisionnement.** Le point le plus fort : **aucune
dépendance d'exécution**. `json`, `hashlib`, `http.server`, `urllib`. Un outil
d'audit dont la chaîne compte douze paquets plaide contre lui-même.

**n° 7 — Désinformation.** Traité avec un soin rare. Le signal d'escalade repose
sur deux échantillons qui divergent, pas sur la confiance déclarée du modèle ;
`replay` dit explicitement quand il ne prouve rien ; et la réserve sur le bruit
d'échantillonnage est publiée à côté du gain annoncé, test à l'appui.

**n° 10 — Mauvaise gestion des sorties.** Le visualiseur échappe chaque valeur,
n'insère jamais de HTML, ne sert aucun JavaScript, et son en-tête pose la règle :
*« Everything it displays is hostile input. »* Le plantage sur des octets dans
une action a été corrigé le 7 octobre (`3248ef3`).

**n° 2 — Divulgation d'information sensible.** Couvert le 7 octobre pour les
paramètres d'action, le nom de décision, les preuves, l'issue et le chemin
d'erreur. **Limite inhérente à dire :** `Redactor` ne rédige que les secrets
qu'on lui a nommés à la construction. Un secret non déclaré passe.

---

## ○ Sans objet

**n° 3 — Agentivité excessive.** Glass Box observe, il ne contraint pas. Il dit
après coup ce qu'un agent a fait ; il n'a aucun modèle de permission et
n'empêche rien. C'est le dessin, mais c'est à dire plutôt qu'à sous-entendre —
le n° 3 est le troisième risque réel du classement.

**n° 5 — Empoisonnement.** Rien n'est entraîné. Le magasin de preuves est
adressé par contenu : une charge substituée casse son propre identifiant.

**n° 9 — Vecteurs et plongements.** Aucun.

---

## Ce que l'exercice a montré

**Trois des dix risques du classement 2026 décrivent des défauts corrigés dans
ce dépôt la veille de cet audit** — le n° 2 (un secret en clair dans une
action), le n° 10 (des octets qui faisaient planter l'enregistreur), et le n° 3
qui est la raison d'être entière du projet.

Ils n'ont pas été trouvés en lisant OWASP. Ils ont été trouvés en marchant le
produit et en mesurant ce que les tests atteignaient. Le classement confirme
qu'ils comptent ; il ne les aurait pas révélés.

**L'inverse est vrai aussi :** le n° 8 et le n° 6 étaient là depuis le début, et
il a fallu une liste pour aller les chercher.
