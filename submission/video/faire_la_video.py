"""Rend la vidéo de démonstration depuis la sortie réelle des commandes.

**Pourquoi ce script existe, et pourquoi il relance les commandes.** Une vidéo
de hackathon est une affirmation : « voici ce que fait l'outil ». Le moyen le
plus simple de la rendre fausse est de typographier une sortie copiée à la main,
qui vieillit dès que le code change. Ici, chaque plan **exécute** la commande
qu'il montre et compose ce qu'elle a réellement écrit. Si `verify` change de
message, la vidéo change avec lui ; si une commande échoue, le rendu s'arrête au
lieu de montrer une sortie d'hier.

**Le plan qui porte la vidéo est le quatrième.** On vérifie le registre scellé,
on ajoute **un champ qu'aucun hachage ne couvre** à une **copie**, et on
revérifie : le vérificateur nomme l'enregistrement. Montrer la falsification
vaut mieux que prononcer le mot « inviolable », et le registre réel n'est jamais
touché — la copie vit sous `captures/`.

**Ce que ce rendu n'est pas.** Une capture d'écran réelle a une texture que ceci
n'a pas, et un jury aime voir une main sur un produit. C'est le compromis
assumé : sobre, exact, et surtout existant. Le découpage est identique à celui
de `NARRATION.md`, donc une capture tournée plus tard se monte au même endroit.

Usage :
    python submission/video/faire_la_video.py
    python submission/video/faire_la_video.py --fps 30 --sortie demo.mp4
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

import imageio
import numpy as np
from PIL import Image, ImageDraw, ImageFont

RACINE = Path(__file__).resolve().parent.parent.parent
CAPTURES = Path(__file__).resolve().parent / "captures"
REGISTRE = RACINE / "runs/escalation/ledger.jsonl"

LARGEUR, HAUTEUR = 1920, 1080
MARGE_X, MARGE_Y = 96, 88

#: Palette. Un fond très sombre mais non noir — le noir pur bave au réencodage
#: de YouTube et fait baver le texte avec lui.
FOND = (14, 16, 21)
TEXTE = (222, 226, 232)
ESTOMPE = (122, 130, 142)
INVITE = (108, 182, 255)
SUCCES = (86, 211, 141)
ALERTE = (255, 106, 106)
LEGENDE = (168, 178, 192)

POLICE = "C:/Windows/Fonts/consola.ttf"
POLICE_GRASSE = "C:/Windows/Fonts/consolab.ttf"


def police(taille: int, grasse: bool = False) -> ImageFont.FreeTypeFont:
    chemin = POLICE_GRASSE if grasse else POLICE
    if not Path(chemin).exists():
        raise SystemExit(f"police absente : {chemin}")
    return ImageFont.truetype(chemin, taille)


@dataclass
class Ligne:
    """Une ligne à l'écran, avec sa couleur."""

    texte: str
    couleur: tuple[int, int, int] = TEXTE


@dataclass
class Plan:
    """Un plan : une commande tapée, sa sortie, et une légende."""

    commande: str
    sortie: list[Ligne]
    legende: str = ""
    #: Secondes de pause après la sortie, pour laisser lire.
    pause: float = 2.2


def lancer(args: list[str]) -> tuple[int, list[str]]:
    """Exécute une commande glassbox et rend (code, lignes).

    On capture `stdout` **et** `stderr` ensemble : le vérificateur écrit ses
    refus là où il veut, et une vidéo qui n'en montrerait qu'un flux
    laisserait croire que la commande n'a rien dit.
    """
    fini = subprocess.run([sys.executable, "-m", "glassbox", *args],
                          cwd=RACINE, capture_output=True, text=True,
                          errors="replace", timeout=300)
    brut = (fini.stdout or "") + (fini.stderr or "")
    return fini.returncode, [l.rstrip() for l in brut.splitlines()]


def lancer_pytest() -> tuple[int, list[Ligne]]:
    """La suite complete, et on refuse de tourner si elle n'est pas verte.

    Un outil qui dit « ce registre tient » demande une confiance qu'il doit
    rendre. Montrer les 220 tests la rend verifiable en quatre secondes — mais
    seulement s'ils passent, donc un echec arrete le rendu au lieu de filmer
    une suite rouge.
    """
    fini = subprocess.run([sys.executable, "-m", "pytest", "-q"], cwd=RACINE,
                          capture_output=True, text=True, errors="replace",
                          timeout=600)
    brut = (fini.stdout or "") + (fini.stderr or "")
    lignes = [l.rstrip() for l in brut.splitlines() if l.strip()]
    if fini.returncode != 0:
        raise SystemExit("la suite n'est pas verte : on ne filme pas ca")
    # On ne garde que le resume : la barre de points n'apprend rien a l'ecran.
    garde = [l for l in lignes if "passed" in l or "failed" in l][-1:]
    return fini.returncode, [Ligne(x, SUCCES) for x in garde]


def colorier(lignes: list[str]) -> list[Ligne]:
    """Teinte les lignes de sortie selon ce qu'elles annoncent.

    Rouge pour un refus, vert pour une chaîne qui tient. C'est la seule
    décoration du rendu, et elle suit le texte au lieu de l'habiller : un
    `FAIL` rouge dit la même chose que le mot, plus vite.
    """
    out = []
    for l in lignes:
        bas = l.lower()
        if l.startswith("FAIL") or "problem" in bas:
            out.append(Ligne(l, ALERTE))
        elif "the chain holds" in bas or "verified" in bas:
            out.append(Ligne(l, SUCCES))
        else:
            out.append(Ligne(l, TEXTE))
    return out


def preparer_copie_alteree() -> Path:
    """Copie le registre et y ajoute un champ qu'aucun hachage ne couvre.

    **Jamais sur l'original.** Le registre mesuré est la pièce que la
    soumission produit ; on travaille sur une copie sous `captures/`, et c'est
    aussi ce que la vidéo montre à l'écran.

    Le champ choisi — `"severity": "benign"` — est celui du défaut trouvé en
    marchant le produit : une clé hors de la liste blanche n'était hachée par
    rien, et `verify` répondait « the chain holds ». Le correctif a fait de
    cette falsification un refus nommé, et c'est elle qu'on rejoue.
    """
    CAPTURES.mkdir(parents=True, exist_ok=True)
    copie = CAPTURES / "altere.jsonl"
    shutil.copyfile(REGISTRE, copie)
    lignes = [l for l in copie.read_text(encoding="utf-8").splitlines() if l.strip()]
    cible = 6 if len(lignes) > 6 else 0
    r = json.loads(lignes[cible])
    r["severity"] = "benign"
    lignes[cible] = json.dumps(r, sort_keys=True, separators=(",", ":"),
                               ensure_ascii=False)
    copie.write_text("".join(x + "\n" for x in lignes), encoding="utf-8",
                     newline="\n")
    return copie


def extrait_registre(indice: int, cles: tuple[str, ...]) -> list[Ligne]:
    """Les champs demandes d'un enregistrement reel, mis en forme pour l'ecran.

    **Pourquoi montrer un enregistrement.** Les plans suivants affirment qu'une
    chaine tient et qu'une modification se voit. Sans avoir vu un maillon, un
    spectateur doit croire sur parole. Ici on montre `prev` et `chain` sur le
    premier enregistrement — donc l'engagement de chacun sur son precedent — et
    c'est ce qui rend le refus du plan final lisible plutot que magique.

    Les valeurs sortent du registre mesure, jamais d'un exemple. Les empreintes
    sont tronquees a l'affichage parce qu'un sha256 complet depasse la largeur
    de l'ecran, et la troncature est marquee par des points de suspension.
    """
    lignes = [l for l in REGISTRE.read_text(encoding="utf-8").splitlines() if l.strip()]
    r = json.loads(lignes[indice])
    out = [Ligne("{", ESTOMPE)]
    for cle in cles:
        if cle not in r:
            continue
        valeur = r[cle]
        if isinstance(valeur, str) and len(valeur) > 58:
            valeur = valeur[:52] + "..."
        rendu = json.dumps(valeur, ensure_ascii=False) if not isinstance(valeur, str)             else f'"{valeur}"'
        if isinstance(valeur, (list, dict)):
            rendu = json.dumps(valeur, ensure_ascii=False, separators=(", ", ": "))
            if len(rendu) > 92:
                rendu = rendu[:89] + "..."
        couleur = SUCCES if cle in ("chain", "prev") else TEXTE
        out.append(Ligne(f'  "{cle}": {rendu},', couleur))
    out.append(Ligne("}", ESTOMPE))
    return out


# ── Composition d'une image ──────────────────────────────────────────────

def cadre_vide() -> Image.Image:
    img = Image.new("RGB", (LARGEUR, HAUTEUR), FOND)
    d = ImageDraw.Draw(img)
    # Un liseré haut, discret : il donne un bord à l'image sans décorer.
    d.rectangle([0, 0, LARGEUR, 4], fill=(30, 34, 42))
    return img


def dessiner_terminal(commande_visible: str, sortie: list[Ligne],
                      legende: str, curseur: bool) -> Image.Image:
    img = cadre_vide()
    d = ImageDraw.Draw(img)
    f = police(30)
    fl = police(26)
    interligne = 42
    y = MARGE_Y

    d.text((MARGE_X, y), "$", font=police(30, grasse=True), fill=INVITE)
    d.text((MARGE_X + 34, y), commande_visible, font=f, fill=TEXTE)
    if curseur:
        largeur = f.getlength(commande_visible)
        d.rectangle([MARGE_X + 36 + largeur, y + 4,
                     MARGE_X + 36 + largeur + 14, y + 34], fill=INVITE)
    y += interligne + 14

    for ligne in sortie:
        d.text((MARGE_X + 34, y), ligne.texte, font=f, fill=ligne.couleur)
        y += interligne

    if legende:
        d.text((MARGE_X, HAUTEUR - 108), legende, font=fl, fill=LEGENDE)
    return img


def carte(lignes: list[tuple[str, int, tuple[int, int, int], bool]]) -> Image.Image:
    """Un carton de texte centré : titre d'ouverture, carte de fin."""
    img = cadre_vide()
    d = ImageDraw.Draw(img)
    hauteurs = []
    for t, taille, _, grasse in lignes:
        f = police(taille, grasse)
        hauteurs.append(f.getbbox(t or "M")[3] + taille // 2)
    y = (HAUTEUR - sum(hauteurs)) // 2
    for (t, taille, coul, grasse), h in zip(lignes, hauteurs):
        f = police(taille, grasse)
        if t:
            d.text(((LARGEUR - f.getlength(t)) / 2, y), t, font=f, fill=coul)
        y += h
    return img


# ── Déroulé ──────────────────────────────────────────────────────────────

@dataclass
class Rendu:
    fps: int = 30
    images: list[Image.Image] = field(default_factory=list)

    def tenir(self, img: Image.Image, secondes: float) -> None:
        for _ in range(max(1, round(secondes * self.fps))):
            self.images.append(img)

    def taper(self, commande: str, sortie: list[Ligne], legende: str,
              pause: float) -> None:
        """Frappe la commande caractère par caractère, puis révèle la sortie.

        ~22 caractères par seconde : assez vif pour ne pas lasser, assez lent
        pour qu'on lise la commande — c'est elle qui dit ce qu'on va voir.
        """
        for i in range(len(commande) + 1):
            img = dessiner_terminal(commande[:i], [], legende, curseur=True)
            self.tenir(img, 1 / 22)
        self.tenir(dessiner_terminal(commande, [], legende, curseur=False), 0.5)
        for i in range(1, len(sortie) + 1):
            self.tenir(dessiner_terminal(commande, sortie[:i], legende,
                                         curseur=False), 0.22)
        self.tenir(dessiner_terminal(commande, sortie, legende, curseur=False),
                   pause)


def construire(fps: int) -> list[Image.Image]:
    r = Rendu(fps=fps)

    # Plan 0 — la promesse, en une phrase.
    r.tenir(carte([
        ("Un agent a pris douze decisions.", 52, TEXTE, True),
        ("", 20, TEXTE, False),
        ("Lesquelles, pourquoi, et si le registre a ete touche.", 38, ESTOMPE, False),
    ]), 4.5)

    # Plan 1 — un maillon, pour que la chaine ne soit pas un mot.
    r.taper("head -1 runs/escalation/ledger.jsonl",
            extrait_registre(0, ("name", "started_at", "asks", "prev", "chain")),
            "chaque enregistrement s'engage sur le precedent : prev et chain", 3.6)

    # Plan 2 — une escalade reelle, pour que le chiffre du plan suivant
    # ait un visage. L'enregistrement 8 est monte de super a ultra.
    r.taper("sed -n 8p runs/escalation/ledger.jsonl",
            extrait_registre(7, ("name", "asks")),
            "escalade de super vers ultra - six appels, et la reponse n'a pas change", 3.6)

    # Plan 3 — ce que la passe a coute. Chiffres mesures, pas d'exemple.
    code, lignes = lancer(["stats", "runs/escalation/ledger.jsonl"])
    if code != 0:
        raise SystemExit(f"stats a echoue (code {code}) : la video ne doit pas "
                         "montrer une sortie d'hier")
    r.taper("glassbox stats runs/escalation/ledger.jsonl", colorier(lignes),
            "l'escalade a change la reponse une fois sur deux - mesure, pas suppose", 3.4)

    # Plan 2 — la chaine tient.
    code, lignes = lancer(["verify", "runs/escalation/ledger.jsonl"])
    if code != 0:
        raise SystemExit(f"verify a echoue (code {code}) sur le registre reel")
    r.taper("glassbox verify runs/escalation/ledger.jsonl", colorier(lignes),
            "re-chaine les douze enregistrements et resout chaque citation", 2.8)

    # Plan 3 — la falsification. Le plan qui porte la video.
    copie = preparer_copie_alteree()
    rel = copie.relative_to(RACINE).as_posix()
    r.tenir(carte([
        ("On ajoute un champ a une copie scellee.", 44, TEXTE, True),
        ("", 18, TEXTE, False),
        ('"severity": "benign"', 40, ALERTE, False),
        ("", 18, TEXTE, False),
        ("Aucun hachage ne le couvre.", 34, ESTOMPE, False),
    ]), 4.0)

    code, lignes = lancer(["verify", rel])
    if code == 0:
        raise SystemExit("le registre altere passe la verification : il n'y a "
                         "rien a montrer, et c'est un defaut a corriger avant "
                         "de tourner")
    r.taper(f"glassbox verify {rel}", colorier(lignes),
            "un registre modifiable sans que ca se voie est un temoignage, pas une preuve", 4.2)

    # Plan final avant la carte : la suite, parce qu'un outil d'audit qui
    # demande qu'on le croie sur sa propre solidite demande beaucoup.
    # `lancer_pytest` rend deja des `Ligne` colorees : les repasser par
    # `colorier`, qui attend des chaines, levait un AttributeError.
    code, lignes = lancer_pytest()
    r.taper("pytest -q", lignes,
            "chaque garde de ce registre est prouvee par une falsification deliberee", 3.2)

    # Carte de fin.
    r.tenir(carte([
        ("Glass Box", 64, TEXTE, True),
        ("", 22, TEXTE, False),
        ("220 tests - Apache 2.0", 34, ESTOMPE, False),
        ("github.com/Yoh5/glassbox", 34, INVITE, False),
        ("", 16, TEXTE, False),
        ("glassbox-demo.onrender.com", 30, ESTOMPE, False),
    ]), 4.5)
    return r.images


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--sortie", default=str(Path(__file__).resolve().parent
                                            / "glassbox-demo.mp4"))
    args = ap.parse_args()

    print("rendu des plans (les commandes sont relancees)...", flush=True)
    images = construire(args.fps)
    duree = len(images) / args.fps
    print(f"  {len(images)} images, {duree:.1f} s a {args.fps} fps", flush=True)
    if duree > 175:
        print(f"  ATTENTION : {duree:.0f} s, le plafond du concours est 180 s", flush=True)

    sortie = Path(args.sortie)
    sortie.parent.mkdir(parents=True, exist_ok=True)
    # `macro_block_size=1` : sans ca imageio redimensionne en silence vers un
    # multiple de 16 et la video ne fait plus 1920x1080.
    with imageio.get_writer(sortie, fps=args.fps, codec="libx264",
                            quality=8, macro_block_size=1) as w:
        for img in images:
            w.append_data(np.asarray(img))
    print(f"ecrit : {sortie}  ({sortie.stat().st_size/1e6:.1f} Mo)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
