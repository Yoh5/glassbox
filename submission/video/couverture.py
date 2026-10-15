"""La bannière du dépôt : ce que le projet fait, en une image.

**Ce qu'une couverture doit faire.** Quelqu'un qui tombe sur le dépôt décide en
deux secondes s'il lit la suite. Une couverture qui répète le nom en gros ne
l'aide pas ; une qui montre **le mécanisme** le renseigne. Ici : une chaîne de
décisions scellées, et un maillon qui a lâché.

C'est le même geste que la vidéo, et pour la même raison — la rupture passe par
la **géométrie** et non par la couleur. Vert contre rouge mesure ΔE 4,1 en
deutéranopie : un lecteur daltonien ne verrait pas le maillon fautif si sa seule
marque était sa teinte. Il sort donc de la ligne, s'écarte, et porte une croix.

Palette validée pour fond sombre : surface `#1a1a19`, encre `#ffffff` /
`#c3c2b7`, accent `#3987e5`, critique `#d03b3b`.

Deux formats, parce que GitHub en veut deux :

- `cover.png` (2400x900) — la bannière du README, nette sur écran dense ;
- `social.png` (1280x640) — l'aperçu social, dont GitHub impose la taille ;
- `devpost-cover.png` (1800x1200) — la couverture Devpost. **3:2**, parce que
  la galerie sert ses vignettes en 333x222 et les affiche en 269x179 : c'est
  mesuré sur la galerie, pas supposé, et une image 16:9 y serait rognée.

Usage :
    python submission/video/couverture.py
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from keynote import (ACCENT, CRITIQUE, ENCRE, ENCRE_2, ENCRE_3, MONO, MONO_G,
                     REGISTRE, SANS, SANS_G, SANS_L, SURFACE, ecrire, f,
                     melanger, nombre_de_tests, opacite)

#: Les couvertures sont des actifs du depot, pas du dossier de soumission :
#: le README les reference, donc elles vivent sous `docs/`.
SORTIE = Path(__file__).resolve().parent.parent.parent / "docs"


def fond(l: int, h: int) -> Image.Image:
    """Dégradé vertical et halo, calculés pour la taille demandée.

    Un aplat pur donne une image morte et se dégrade mal à la recompression
    que GitHub applique aux aperçus.
    """
    y = np.linspace(0, 1, h, dtype=np.float32)[:, None]
    img = np.repeat(np.repeat(np.array(SURFACE, dtype=np.float32)[None, None, :],
                              h, 0), l, 1)
    img += y[:, :, None] * 12.0
    xx = np.linspace(-1.5, 0.9, l, dtype=np.float32)[None, :]
    yy = np.linspace(-1.1, 1.3, h, dtype=np.float32)[:, None]
    halo = np.exp(-((xx**2) * 1.3 + (yy**2) * 1.7)) * 22.0
    img += halo[:, :, None] * np.array([0.42, 0.60, 1.0], dtype=np.float32)
    return Image.fromarray(np.clip(img, 0, 255).astype(np.uint8))


def chaine(d: ImageDraw.ImageDraw, x0: int, y: int, n: int, larg: int,
           haut: int, ecart: int, rompu: int, echelle: float) -> None:
    """Une rangée de maillons, dont un qui a lâché.

    Le maillon rompu descend et son trait d'entrée s'efface : c'est le vide,
    pas la teinte, qui dit que la chaîne ne tient plus.
    """
    empreintes = []
    for ligne in REGISTRE.read_text(encoding="utf-8").splitlines()[:n]:
        if ligne.strip():
            empreintes.append((json.loads(ligne).get("chain") or "")[7:7 + 8])

    for k in range(n):
        x = x0 + k * (larg + ecart)
        casse = k == rompu
        yy = y + (int(haut * 0.42) if casse else 0)
        teinte = CRITIQUE if casse else ACCENT
        if k > 0:
            coupe = casse or (k - 1) == rompu
            d.line([(x - ecart, y + haut // 2), (x, yy + haut // 2)],
                   fill=opacite(CRITIQUE if coupe else ACCENT,
                                0.12 if coupe else 0.45),
                   width=max(2, int(3 * echelle)))
        d.rounded_rectangle([x, yy, x + larg, yy + haut],
                            radius=int(14 * echelle),
                            fill=opacite(teinte, 0.10 if casse else 0.07),
                            outline=opacite(teinte, 0.85 if casse else 0.55),
                            width=max(2, int(3 * echelle)))
        if k < len(empreintes):
            ecrire(d, (x + larg / 2, yy + haut / 2 - int(13 * echelle)),
                   empreintes[k], f(MONO, max(11, int(19 * echelle))),
                   opacite(ENCRE_3 if not casse else CRITIQUE, 0.95),
                   centre=True)
        if casse:
            ecrire(d, (x + larg / 2, yy + haut + int(16 * echelle)), "X",
                   f(SANS_G, max(14, int(26 * echelle))),
                   opacite(CRITIQUE, 1.0), centre=True)


def composer(l: int, h: int, echelle: float) -> Image.Image:
    img = fond(l, h)
    d = ImageDraw.Draw(img)

    marge = int(l * 0.075)
    ecrire(d, (marge, int(h * 0.22)), "Glass Box", f(SANS_G, int(92 * echelle)),
           ENCRE, suivi=2 * echelle)
    ecrire(d, (marge, int(h * 0.44)),
           "An agent's decisions, sealed and verifiable.",
           f(SANS_L, int(40 * echelle)), ENCRE_2, suivi=echelle)
    ecrire(d, (marge, int(h * 0.555)),
           "Change one byte and the verifier names the record.",
           f(SANS_L, int(34 * echelle)), ENCRE_3, suivi=echelle)

    n, larg = 8, int(l * 0.078)
    haut, ecart = int(h * 0.145), int(l * 0.022)
    total = n * larg + (n - 1) * ecart
    chaine(d, marge, int(h * 0.70), n, larg, haut, ecart, rompu=4,
           echelle=echelle)

    ecrire(d, (marge + total + int(l * 0.04), int(h * 0.735)),
           f"{nombre_de_tests()} tests", f(MONO_G, int(26 * echelle)),
           opacite(ENCRE_2, 0.95))
    ecrire(d, (marge + total + int(l * 0.04), int(h * 0.80)),
           "Apache 2.0", f(MONO, int(24 * echelle)), opacite(ENCRE_3, 0.95))
    return img


# ── La couverture Devpost : 3:2, et lisible en 269 pixels ────────────────
#
# Mesuré plutôt que supposé : Devpost sert la vignette de galerie en 333x222
# et l'affiche en **269x179**. C'est du 3:2, pas du 16:9 -- une couverture
# large y serait rognée haut et bas, et le maillon rompu avec.
#
# 269 pixels, c'est la contrainte qui décide tout le reste. À cette taille le
# texte d'un hachage ne se lit plus, et une chaîne de huit maillons devient une
# bouillie. Donc cinq maillons seulement, deux fois plus gros, et une seule
# chose à comprendre d'un coup d'oeil : il y en a un qui est rouge et qui est
# tombé de la ligne. Le reste est pour la page du projet, où l'image est
# grande.

def composer_devpost(l: int, h: int, echelle: float) -> Image.Image:
    img = fond(l, h)
    d = ImageDraw.Draw(img)
    marge = int(l * 0.08)

    ecrire(d, (marge, int(h * 0.13)), "Glass Box", f(SANS_G, int(150 * echelle)),
           ENCRE, suivi=3 * echelle)
    ecrire(d, (marge, int(h * 0.30)),
           "Every decision an agent made,", f(SANS_L, int(62 * echelle)),
           ENCRE_2, suivi=echelle)
    ecrire(d, (marge, int(h * 0.385)),
           "sealed so a rewrite shows.", f(SANS_L, int(62 * echelle)),
           ENCRE_2, suivi=echelle)

    # Cinq maillons, larges : à la vignette on ne lit pas les empreintes, on
    # voit une chaîne et un trou. C'est tout ce que la vignette doit dire.
    n = 5
    larg = int(l * 0.155)
    ecart = int(l * 0.035)
    haut = int(h * 0.165)
    total = n * larg + (n - 1) * ecart
    x0 = (l - total) // 2
    chaine(d, x0, int(h * 0.58), n, larg, haut, ecart, rompu=2,
           echelle=echelle * 1.9)

    ecrire(d, (l / 2, int(h * 0.885)),
           "the verifier names the record it cannot vouch for",
           f(SANS_L, int(40 * echelle)), opacite(ENCRE_3, 0.95), centre=True,
           suivi=echelle)
    ecrire(d, (l / 2, int(h * 0.945)),
           f"{nombre_de_tests()} tests  ·  Apache 2.0  ·  NVIDIA Nemotron on Nebius Token Factory",
           f(MONO, int(28 * echelle)), opacite(ENCRE_3, 0.75), centre=True)
    return img


def main() -> int:
    SORTIE.mkdir(parents=True, exist_ok=True)
    formats = {
        "cover.png": (composer, 2400, 900, 1.0),
        "social.png": (composer, 1280, 640, 0.62),
        # 3:2, le rapport que Devpost sert vraiment. 1800 de large pour que la
        # vignette de 333 soit un sous-échantillonnage net, pas un étirement.
        "devpost-cover.png": (composer_devpost, 1800, 1200, 1.0),
    }
    for nom, (fabrique, l, h, e) in formats.items():
        img = fabrique(l, h, e)
        chemin = SORTIE / nom
        img.save(chemin, optimize=True)
        print(f"ecrit : {chemin.name}  {l}x{h}  "
              f"({chemin.stat().st_size/1024:.0f} Ko)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
