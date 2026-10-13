"""Rend la vidéo de démonstration image par image, depuis la sortie réelle du CLI.

**Pourquoi par le code plutôt qu'à la capture.** Rien ici n'est mis en scène :
chaque ligne affichée sort d'une commande réellement exécutée sur le registre
mesuré, et le plan de falsification altère une **copie** du registre puis montre
ce que `glassbox verify` répond vraiment. Un rendu programmatique est plus
sobre qu'une vraie capture d'écran, mais il ne peut pas mentir sur un chiffre —
et c'est le contraire de ce qu'on reproche d'habitude à une vidéo de hackathon.

**Ce que ce rendu ne montre pas, et pourquoi.** `trace` et `replay` ne figurent
pas : le registre de `runs/escalation/` vient d'une passe de **mesure** du
routeur, dont les douze enregistrements portent `actions: []` et
`evidence: []`. Il n'y a donc aucune action à tracer ni aucune preuve à
rejouer, et scripter ces plans aurait produit une démonstration infilmable.
Ils demandent une passe avec actions et preuves.

Sortie : `submission/video/glassbox-demo.mp4`, 1920×1080, 30 i/s, sous 3 min.

Usage :
    python submission/video/rendre.py
    python submission/video/rendre.py --sans-encodage   # n'ecrit que des PNG
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

RACINE = Path(__file__).resolve().parent.parent.parent
ICI = Path(__file__).resolve().parent
CAPTURES = ICI / "captures"

LARGEUR, HAUTEUR = 1920, 1080
IPS = 30

# Un thème sombre et sobre : le texte doit rester lisible sur un téléphone,
# puisque c'est là qu'un juré regardera peut-être.
FOND = (13, 17, 23)
PANNEAU = (22, 27, 34)
BORDURE = (48, 54, 61)
TEXTE = (201, 209, 217)
INVITE = (126, 231, 135)
COMMANDE = (255, 255, 255)
SUCCES = (63, 185, 80)
ALERTE = (248, 81, 73)
DISCRET = (110, 118, 129)
ACCENT = (121, 192, 255)

POLICE = "C:/Windows/Fonts/consola.ttf"
POLICE_GRASSE = "C:/Windows/Fonts/consolab.ttf"
POLICE_TITRE = "C:/Windows/Fonts/segoeui.ttf"


def police(chemin: str, taille: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(chemin, taille)


MONO = police(POLICE, 30)
MONO_GRAS = police(POLICE_GRASSE, 30)
TITRE = police(POLICE_TITRE, 62)
SOUS_TITRE = police(POLICE_TITRE, 34)
LEGENDE = police(POLICE_TITRE, 32)

HAUT_LIGNE = 42
MARGE = 90


@dataclass
class Plan:
    """Un plan : une commande tapée, sa sortie réelle, une légende, une durée."""

    commande: str
    sortie: list[str]
    legende: str = ""
    #: Secondes de maintien après que tout est affiché.
    tenue: float = 2.2
    #: Lignes dont la couleur change (index de ligne -> couleur).
    couleurs: dict[int, tuple[int, int, int]] = field(default_factory=dict)
    #: Lignes affichées avant la commande, comme un commentaire de contexte.
    contexte: list[str] = field(default_factory=list)


def cadre_terminal(titre: str = "glassbox") -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGB", (LARGEUR, HAUTEUR), FOND)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([MARGE - 30, 110, LARGEUR - MARGE + 30, HAUTEUR - 150],
                        radius=14, fill=PANNEAU, outline=BORDURE, width=2)
    d.line([MARGE - 30, 168, LARGEUR - MARGE + 30, 168], fill=BORDURE, width=2)
    for i, c in enumerate(((255, 95, 86), (255, 189, 46), (39, 201, 63))):
        d.ellipse([MARGE - 6 + i * 30, 131, MARGE + 10 + i * 30, 147], fill=c)
    d.text((MARGE + 110, 126), titre, font=police(POLICE, 26), fill=DISCRET)
    return img, d


def dessiner_plan(plan: Plan, caracteres_tapes: int, lignes_visibles: int) -> Image.Image:
    img, d = cadre_terminal()
    y = 210
    for l in plan.contexte:
        d.text((MARGE, y), l, font=MONO, fill=DISCRET)
        y += HAUT_LIGNE
    if plan.contexte:
        y += 12

    d.text((MARGE, y), "$", font=MONO_GRAS, fill=INVITE)
    tape = plan.commande[:caracteres_tapes]
    d.text((MARGE + 28, y), tape, font=MONO, fill=COMMANDE)
    if caracteres_tapes < len(plan.commande):
        # Le curseur, seulement pendant la frappe : un curseur qui clignote
        # pendant la tenue attire l'oeil loin de la sortie.
        x = MARGE + 28 + MONO.getlength(tape)
        d.rectangle([x + 2, y + 4, x + 16, y + 34], fill=TEXTE)
    y += HAUT_LIGNE + 14

    for i, ligne in enumerate(plan.sortie[:lignes_visibles]):
        d.text((MARGE, y), ligne, font=MONO, fill=plan.couleurs.get(i, TEXTE))
        y += HAUT_LIGNE

    if plan.legende:
        d.text((MARGE - 30, HAUT := HAUTEUR - 112), plan.legende,
               font=LEGENDE, fill=ACCENT)
    return img


def carte(lignes: list[tuple[str, ImageFont.FreeTypeFont, tuple[int, int, int]]]) -> Image.Image:
    """Un carton plein écran : titre d'ouverture, fin."""
    img = Image.new("RGB", (LARGEUR, HAUTEUR), FOND)
    d = ImageDraw.Draw(img)
    hauteurs = [f.getbbox(t)[3] - f.getbbox(t)[1] + 26 for t, f, _ in lignes]
    y = (HAUTEUR - sum(hauteurs)) // 2
    for (t, f, c), h in zip(lignes, hauteurs):
        d.text(((LARGEUR - f.getlength(t)) // 2, y), t, font=f, fill=c)
        y += h
    return img


def images_du_plan(plan: Plan):
    """Frappe, puis révélation ligne par ligne, puis tenue."""
    # ~42 caracteres par seconde : assez vif pour ne pas ennuyer, assez lent
    # pour qu'on lise la commande, ce qui est le point.
    par_image = 42 / IPS
    tapes = 0.0
    while tapes < len(plan.commande):
        tapes += par_image
        yield dessiner_plan(plan, int(tapes), 0)
    for _ in range(int(0.45 * IPS)):
        yield dessiner_plan(plan, len(plan.commande), 0)
    for n in range(1, len(plan.sortie) + 1):
        img = dessiner_plan(plan, len(plan.commande), n)
        for _ in range(max(1, int(0.12 * IPS))):
            yield img
    final = dessiner_plan(plan, len(plan.commande), len(plan.sortie))
    for _ in range(int(plan.tenue * IPS)):
        yield final


def images_de_carte(img: Image.Image, secondes: float):
    for _ in range(int(secondes * IPS)):
        yield img


def lire(nom: str) -> list[str]:
    chemin = CAPTURES / nom
    if not chemin.exists():
        raise SystemExit(
            f"capture absente : {chemin}\n"
            "Lancer d'abord `python submission/video/capturer.py`.")
    return [l.rstrip() for l in chemin.read_text(encoding="utf-8").splitlines()]


def construire() -> list:
    """La suite des plans, et c'est ici que se lit le découpage."""
    stats = lire("stats.txt")
    verify = lire("verify.txt")
    altere = lire("verify-altere.txt")

    sequences = []

    sequences.append(images_de_carte(carte([
        ("Un agent a pris douze decisions.", TITRE, TEXTE),
        ("", SOUS_TITRE, TEXTE),
        ("Voici comment savoir lesquelles, pourquoi,", SOUS_TITRE, DISCRET),
        ("et si le registre a ete touche.", SOUS_TITRE, DISCRET),
    ]), 7.0))

    sequences.append(images_du_plan(Plan(
        commande="glassbox stats runs/escalation/ledger.jsonl",
        sortie=stats,
        legende="l'escalade a change la reponse une fois sur deux — mesure, pas suppose",
        tenue=4.0,
        couleurs={i: ACCENT for i, l in enumerate(stats) if "escalation" in l or "cost" in l},
    )))

    sequences.append(images_du_plan(Plan(
        commande="glassbox verify runs/escalation/ledger.jsonl",
        sortie=verify,
        legende="la chaine tient sur les douze decisions",
        tenue=3.0,
        couleurs={0: SUCCES},
    )))

    sequences.append(images_du_plan(Plan(
        contexte=[
            "# on ajoute un seul champ a un enregistrement scelle",
            '# "severity": "benign"  —  rien ne le hache',
        ],
        commande="glassbox verify ledger-altere.jsonl",
        sortie=altere + ["", "$ echo $?", "1"],
        legende="un registre modifiable sans que ca se voie est un temoignage, pas une preuve",
        tenue=5.0,
        couleurs={0: ALERTE, 1: ALERTE, 3: ALERTE, 6: ALERTE},
    )))

    sequences.append(images_de_carte(carte([
        ("220 tests.  Apache 2.0.", TITRE, TEXTE),
        ("", SOUS_TITRE, TEXTE),
        ("github.com/Yoh5/glassbox", SOUS_TITRE, ACCENT),
    ]), 6.0))

    return sequences


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sortie", default=str(ICI / "glassbox-demo.mp4"))
    ap.add_argument("--sans-encodage", action="store_true",
                    help="ecrire des PNG d'apercu au lieu d'une video")
    args = ap.parse_args()

    sequences = construire()

    if args.sans_encodage:
        dossier = ICI / "apercu"
        dossier.mkdir(exist_ok=True)
        n = 0
        for seq in sequences:
            dernier = None
            for img in seq:
                dernier = img
            if dernier is not None:
                n += 1
                dernier.save(dossier / f"plan-{n:02d}.png")
        print(f"{n} apercus dans {dossier}")
        return 0

    import imageio.v2 as imageio

    ecrivain = imageio.get_writer(args.sortie, fps=IPS, codec="libx264",
                                  quality=8, macro_block_size=1)
    total = 0
    try:
        for i, seq in enumerate(sequences, 1):
            compte = 0
            for img in seq:
                ecrivain.append_data(np_de(img))
                compte += 1
            total += compte
            print(f"  plan {i} : {compte} images ({compte/IPS:.1f} s)", flush=True)
    finally:
        ecrivain.close()
    print(f"\n{total} images, {total/IPS:.1f} s -> {args.sortie}")
    if total / IPS > 180:
        print("ATTENTION : au-dela des 3 minutes autorisees.")
    return 0


def np_de(img: Image.Image):
    import numpy as np
    return np.asarray(img)


if __name__ == "__main__":
    raise SystemExit(main())
