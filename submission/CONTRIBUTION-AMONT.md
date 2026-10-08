# Contribution en amont — `nebius/token-factory-cookbook`

Brouillon du 8 octobre 2026. **Non publié.**

Le champ *Upstream contribution* du dossier Devpost attend ceci.

---

## Le constat

**L'exemple de code de la page Nemotron-3-Nano-30B-A3B rend 404.** La page
documente l'identifiant en minuscules ; l'API ne sert que la forme en casse
mixte.

```
200  nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B
404  nvidia/nvidia-nemotron-3-nano-30b-a3b
     {"detail":"The model `nvidia/nvidia-nemotron-3-nano-30b-a3b` does not exist."}
```

**Et le dépôt se contredit.** `models/nemotron/README.md:16` emploie la bonne
forme dans son lien playground ; `models/nemotron/nemotron3-nano-30b.md` emploie
la mauvaise aux lignes 30 (l'exemple de code) et 38 (le lien playground).

C'est donc l'extrait que l'utilisateur copie qui est cassé, pendant que la page
d'index d'à côté est juste.

## Portée, et ce qui n'en fait pas partie

Les trois autres pages Nemotron ont été vérifiées contre `GET /v1/models` sur un
compte réel. **Seul le Nano est fautif :**

| Page | Identifiant documenté | Servi par l'API |
|---|---|---|
| `nemotron3-nano-30b.md` | `nvidia/nvidia-nemotron-3-nano-30b-a3b` | ❌ |
| `nemotron3-super-120B.md` | `nvidia/nemotron-3-super-120b-a12b` | ✅ |
| `nemotron3-ultra-550b-a55b.md` | `nvidia/Nemotron-3-Ultra-550b-a55b` | ✅ |

**`nemotron3-nano-omni.md` n'est pas signalé.** Son identifiant
(`nvidia/nemotron-3-nano-omni`) n'apparaît pas dans les 25 modèles que ce compte
peut appeler, mais cela peut tenir à la région, au palier, ou à un point d'accès
dédié. Je ne sais pas, donc je ne le rapporte pas.

## Le correctif proposé

Deux lignes dans `models/nemotron/nemotron3-nano-30b.md` :

```diff
-    model="nvidia/nvidia-nemotron-3-nano-30b-a3b",
+    model="nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B",
```

```diff
-https://tokenfactory.nebius.com/playground?models=nvidia/nvidia-nemotron-3-nano-30b-a3b
+https://tokenfactory.nebius.com/playground?models=nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B
```

## Comment c'est vérifiable

```bash
export NEBIUS_API_KEY=...
for id in nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B nvidia/nvidia-nemotron-3-nano-30b-a3b; do
  printf '%s -> ' "$id"
  curl -s -o /dev/null -w '%{http_code}\n' \
    -H "Authorization: Bearer $NEBIUS_API_KEY" -H 'Content-Type: application/json' \
    -d "{\"model\":\"$id\",\"max_tokens\":4,\"messages\":[{\"role\":\"user\",\"content\":\"hi\"}]}" \
    https://api.tokenfactory.nebius.com/v1/chat/completions
done
```

Et `GET /v1/models` donne la liste qui fait foi.

---

## Un second constat, à déposer séparément si l'on y tient

**La troncature rend des jetons facturés sous un champ que rien ne documente.**
Avec `max_tokens` épuisé pendant la réflexion, la réponse est un HTTP 200 où
`content` vaut `null` et le texte se trouve dans **`reasoning`** — pas dans
`reasoning_content`, nom employé par d'autres fournisseurs et vers lequel un
client porté depuis ailleurs se tournera naturellement.

```
finish_reason      length
content            None
reasoning          84 caracteres
reasoning_content  None
usage              completion_tokens: 24
```

Ce n'est pas un défaut : les jetons sont là et la réponse est bien formée. C'est
une absence de documentation, et elle nous a coûté un bogue — notre propre
client lisait `reasoning_content` et rendait une chaîne vide sur chaque réponse
tronquée, sans rien signaler.

**Deux dépôts séparés plutôt qu'un.** Le premier est un correctif de deux lignes
sur un fait vérifiable ; le second est une demande de documentation. Les mêler
ferait attendre le petit derrière le grand — c'est la règle que `ISSUES.md` de
KeeperHub formule, et elle vaut partout.

## Décision à prendre avant publication

Une **pull request** pour le premier (deux lignes, fait vérifiable, rien à
négocier) et une **issue** pour le second. Une PR fusionnée pèse plus qu'une
issue ouverte dans un dossier de hackathon, et le premier constat n'appelle
aucune discussion.
