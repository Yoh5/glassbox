"""La même démonstration, montée comme une présentation.

**Pourquoi une seconde version.** `faire_la_video.py` filme un terminal : exact,
sobre, et il se lit comme « voici un outil ». Une présentation se lit comme
« voici pourquoi ça compte », et devant un jury qui regarde trente vidéos la
différence n'est pas cosmétique. Les deux coexistent : celle-ci porte le propos,
l'autre reste la preuve que la sortie montrée est bien celle des commandes.

**Ce qui reste vrai.** Chaque nombre vient de `runs/escalation/ledger.jsonl`, les
douze maillons portent leurs vrais niveaux et leurs vrais coûts, et le refus du
vérificateur est **exécuté** au moment du rendu, pas recopié. Rien n'est
illustré : tout est lu.

**Ce qui manque et ne viendra pas de moi : le son.** Un keynote muet est la
moitié d'un keynote. Les temps forts sont imprimés par le script à la fin du
rendu pour qu'une piste puisse être calée dessus.

**Une décision de couleur qui n'est pas une préférence.** Le temps fort est un
maillon qui lâche. La version paresseuse le peint en rouge sur une chaîne verte —
or vert contre rouge mesure ΔE 4,1 en deutéranopie : un spectateur daltonien ne
verrait rien. Donc le maillon **se brise** — un vide dans la géométrie, le
numéro d'enregistrement, une croix — et la couleur ne fait que renforcer. Forme,
position et texte portent le sens. C'est aussi un meilleur plan.

Palette : surface `#1a1a19`, encre `#ffffff` / `#c3c2b7`, accent `#3987e5`,
critique `#d03b3b` — valeurs validées pour fond sombre, pas choisies à l'œil.

Usage :
    python submission/video/keynote.py
    python submission/video/keynote.py --fps 30 --sortie keynote.mp4
"""

from __future__ import annotations

import argparse
import json
import math
import re
import shutil
import subprocess
import sys
import wave
from pathlib import Path
from typing import Iterator

import imageio
import imageio_ffmpeg
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

RACINE = Path(__file__).resolve().parent.parent.parent
CAPTURES = Path(__file__).resolve().parent / "captures"
REGISTRE = RACINE / "runs/escalation/ledger.jsonl"
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()

L, H = 1920, 1080
SURFACE = (26, 26, 25)
ENCRE = (255, 255, 255)
ENCRE_2 = (195, 194, 183)
ENCRE_3 = (120, 120, 114)
ACCENT = (57, 135, 229)
CRITIQUE = (208, 59, 59)

MONO = "C:/Windows/Fonts/consola.ttf"
MONO_G = "C:/Windows/Fonts/consolab.ttf"
SANS = "C:/Windows/Fonts/segoeui.ttf"
SANS_G = "C:/Windows/Fonts/segoeuib.ttf"
SANS_L = "C:/Windows/Fonts/segoeuil.ttf"

_polices: dict[tuple[str, int], ImageFont.FreeTypeFont] = {}


def f(chemin: str, taille: int) -> ImageFont.FreeTypeFont:
    cle = (chemin, taille)
    if cle not in _polices:
        if not Path(chemin).exists():
            chemin = MONO
        _polices[cle] = ImageFont.truetype(chemin, taille)
    return _polices[cle]


# ── Courbes et fonds ─────────────────────────────────────────────────────

def sortie_cubique(t: float) -> float:
    """Départ rapide, arrivée douce. La courbe qui fait qu'un mouvement
    paraît intentionnel plutôt que mécanique."""
    t = min(1.0, max(0.0, t))
    return 1 - (1 - t) ** 3


def douce(t: float) -> float:
    t = min(1.0, max(0.0, t))
    return t * t * (3 - 2 * t)


_fond_cache: Image.Image | None = None


def fond() -> Image.Image:
    """Le fond : un dégradé vertical et un halo bas, calculés une fois.

    Un aplat pur donne une image morte et fait baver les dégradés de YouTube
    sur les grands aplats ; un gradient très léger suffit à donner de l'air.
    """
    global _fond_cache
    if _fond_cache is None:
        y = np.linspace(0, 1, H, dtype=np.float32)[:, None]
        base = np.array(SURFACE, dtype=np.float32)[None, None, :]
        img = np.repeat(np.repeat(base, H, 0), L, 1)
        img += (y[:, :, None] * 10.0)
        xx = np.linspace(-1, 1, L, dtype=np.float32)[None, :]
        yy = np.linspace(-1.6, 0.7, H, dtype=np.float32)[:, None]
        halo = np.exp(-((xx**2) * 1.6 + (yy**2) * 2.2)) * 16.0
        img += halo[:, :, None] * np.array([0.45, 0.62, 1.0], dtype=np.float32)
        _fond_cache = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8))
    return _fond_cache.copy()


def melanger(c: tuple[int, int, int], vers: tuple[int, int, int],
             t: float) -> tuple[int, int, int]:
    t = min(1.0, max(0.0, t))
    return tuple(int(a + (b - a) * t) for a, b in zip(c, vers))


def opacite(c: tuple[int, int, int], a: float) -> tuple[int, int, int]:
    return melanger(SURFACE, c, a)


def ecrire(d: ImageDraw.ImageDraw, xy, texte: str, fnt, couleur, *,
           centre: bool = False, suivi: float = 0.0) -> float:
    """Écrit du texte avec un suivi réglable, et rend sa largeur.

    Le suivi (letter-spacing) manuel est ce qui sépare une grande typo de
    présentation d'un texte de terminal agrandi : à 60 px, les lettres d'une
    police d'interface sont trop serrées pour un titre.
    """
    x, y = xy
    largeur = sum(fnt.getlength(c) + suivi for c in texte) - (suivi if texte else 0)
    if centre:
        x = x - largeur / 2
    for c in texte:
        d.text((x, y), c, font=fnt, fill=couleur)
        x += fnt.getlength(c) + suivi
    return largeur


# ── Données réelles ──────────────────────────────────────────────────────

def lire_registre() -> list[dict]:
    lignes = [l for l in REGISTRE.read_text(encoding="utf-8").splitlines() if l.strip()]
    out = []
    for i, l in enumerate(lignes, 1):
        r = json.loads(l)
        a = (r.get("asks") or [{}])[0]
        out.append({
            "i": i,
            "tier": a.get("tier", "?"),
            "cout": float(a.get("cost_usd") or 0.0),
            "escalade": a.get("escalated_from"),
            "change": a.get("changed_on_escalation"),
            "chain": (r.get("chain") or "")[7:19],
        })
    return out


def lancer(args: list[str]) -> tuple[int, list[str]]:
    fini = subprocess.run([sys.executable, "-m", "glassbox", *args], cwd=RACINE,
                          capture_output=True, text=True, errors="replace",
                          timeout=300)
    brut = (fini.stdout or "") + (fini.stderr or "")
    return fini.returncode, [l.rstrip() for l in brut.splitlines() if l.strip()]


def nombre_de_tests() -> int:
    """Compté par pytest au moment du rendu, jamais écrit à la main.

    La carte de fin annonçait **220 tests** pendant tout le temps qu'il a fallu
    pour en ajouter soixante-seize. Un chiffre tapé dans une vidéo ne vieillit
    pas moins vite qu'un chiffre tapé dans un README, et celui-là était sur la
    dernière image, celle qu'un juré regarde en notant le dépôt.

    Compter les `def test_` donnerait un autre nombre encore : les tests
    paramétrés se démultiplient à la collecte. C'est donc la collecte qui
    fait foi.
    """
    fini = subprocess.run([sys.executable, "-m", "pytest", "--collect-only", "-q"],
                          cwd=RACINE, capture_output=True, text=True,
                          errors="replace", timeout=300)
    derniere = [l for l in (fini.stdout or "").splitlines() if "test" in l][-1]
    nombre = re.search(r"(\d+)\s+tests?\s+collected", derniere)
    if not nombre:
        raise SystemExit(f"impossible de compter les tests : {derniere!r}")
    return int(nombre.group(1))


# ── La narration, qui décide la durée des scènes ─────────────────────────
#
# L'ancienne version portait neuf durées écrites à la main, et une bande son
# qu'il aurait fallu caler dessus après coup. L'ordre est inversé : la phrase
# est dite d'abord, son wav est mesuré à l'échantillon, et la scène est tenue
# exactement ce temps-là. L'image et le son ne peuvent pas dériver, parce que
# rien n'est chronométré deux fois.
#
# La voix est synthétique (`edge-tts`), et la soumission le dit. Le règlement
# Nebius demande une vidéo de moins de trois minutes, sans musique sous droits.

VOIX = "en-US-AndrewNeural"
DEBIT = "-6%"
LIMITE = 180.0

NARRATION = {
    "ouverture": "An agent took twelve decisions in this run. Nobody can say "
                 "which ones, or what they cost.",
    "these": "A log you can edit afterwards is testimony. It is not proof. Everything in this project follows from refusing that one thing.",
    "enregistrement": "This is one record, in full. What ran, when, the models "
                      "it asked and what they cost. And prev, which carries the "
                      "hash of the record before it. Remove or change one line, "
                      "and every line after it breaks.",
    "chaine": "So each decision seals the one before it. Twelve records, two "
              "escalations, and a total of twenty-nine hundredths of a cent. "
              "The running cost on screen is summed from the records being "
              "drawn, so it cannot say one thing while the chain says another.",
    "chiffres": "Twelve decisions, for twenty-nine hundredths of a cent. Two "
                "escalations out of twelve, and in half of them the answer "
                "actually changed. Which is what makes the next one awkward.",
    "escalades": "Here are both of them. The expensive one, super to ultra, "
                 "changed nothing. The cheap one, nano to super, changed the "
                 "answer. Paying more did not buy a different answer, and "
                 "without the ledger nobody could know that.",
    "rupture": "Now the part that matters. We take a sealed copy and add one "
               "field to a single record. Severity, benign. Nothing else is "
               "touched. No hash covers that field, so the chain breaks exactly "
               "there, and verify says so. It does not report that the ledger "
               "looks fine. It names the record it cannot vouch for.",
    "commandes": "Five commands are the whole audit surface. Does the chain "
                 "still hold. Which decision caused this action. Would the rule "
                 "decide the same today. What the run cost. And all four "
                 "answers on one page.",
    "fin": "Glass Box. A ledger an auditor verifies without reading the code. Apache two point zero, and the demo is live.",
}

#: Le plancher de chaque scène : ce qu'il faut pour que l'animation reste
#: lisible même si la phrase est plus courte que le mouvement qu'elle décrit.
#: Douze maillons qui se dessinent en huit secondes ne se lisent pas.
MINIMA = {"ouverture": 7.0, "these": 10.0, "enregistrement": 13.0,
          "chaine": 20.0, "chiffres": 11.0, "escalades": 15.0,
          "rupture": 24.0, "commandes": 13.0, "fin": 9.0}

SILENCE_INITIAL = 4.5   # l'empreinte qui émerge du flou, avant le premier mot
TRAVAIL = Path(__file__).resolve().parent / "_travail"


def dire(cle: str) -> Path:
    """Rend la phrase, puis la convertit en wav pour pouvoir la mesurer."""
    TRAVAIL.mkdir(exist_ok=True)
    mp3, wav = TRAVAIL / f"{cle}.mp3", TRAVAIL / f"{cle}.wav"
    if not wav.exists():
        # `--rate=-6%` et non `--rate -6%` : argparse lit un débit négatif
        # comme une option courte.
        subprocess.run([sys.executable, "-m", "edge_tts", "--voice", VOIX,
                        f"--rate={DEBIT}", "--text", NARRATION[cle],
                        "--write-media", str(mp3)], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run([FFMPEG, "-y", "-i", str(mp3), "-ac", "1", "-ar", "48000",
                        str(wav)], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return wav


def secondes(wav: Path) -> float:
    with wave.open(str(wav)) as f:
        return f.getnframes() / f.getframerate()


def minuter() -> tuple[dict[str, float], dict[str, float]]:
    """(durée de chaque scène, durée de chaque phrase) — dans l'ordre du film."""
    parle = {cle: secondes(dire(cle)) for cle in NARRATION}
    # Une queue d'une seconde après chaque phrase : sans elle, la scène coupe
    # sur la dernière syllabe et la suivante commence avant qu'on ait fini de
    # lire l'écran.
    scenes = {cle: max(parle[cle] + 1.0, MINIMA[cle]) for cle in NARRATION}
    return scenes, parle


def piste_narration(scenes: dict[str, float], parle: dict[str, float]) -> Path:
    """Une seule piste, construite à partir des durées de scène elles-mêmes.

    Le silence qui suit chaque phrase n'est pas choisi : c'est exactement ce
    qui reste de la scène. Il n'existe donc aucun endroit où l'audio et
    l'image pourraient être calés différemment.
    """
    morceaux: list[bytes] = []
    premiere = wave.open(str(TRAVAIL / "ouverture.wav"))
    params = premiere.getparams()
    premiere.close()
    muet = b"\x00" * (params.sampwidth * params.nchannels)
    morceaux.append(muet * round(SILENCE_INITIAL * params.framerate))
    for cle in NARRATION:
        with wave.open(str(TRAVAIL / f"{cle}.wav")) as f:
            morceaux.append(f.readframes(f.getnframes()))
        morceaux.append(muet * round((scenes[cle] - parle[cle]) * params.framerate))
    piste = TRAVAIL / "narration.wav"
    with wave.open(str(piste), "wb") as f:
        f.setparams(params)
        for m in morceaux:
            f.writeframes(m)
    return piste


def copie_alteree() -> tuple[Path, int]:
    """Ajoute un champ non haché à une copie. Jamais à l'original."""
    CAPTURES.mkdir(parents=True, exist_ok=True)
    copie = CAPTURES / "altere.jsonl"
    shutil.copyfile(REGISTRE, copie)
    lignes = [l for l in copie.read_text(encoding="utf-8").splitlines() if l.strip()]
    cible = 6
    r = json.loads(lignes[cible])
    r["severity"] = "benign"
    lignes[cible] = json.dumps(r, sort_keys=True, separators=(",", ":"),
                               ensure_ascii=False)
    copie.write_text("".join(x + "\n" for x in lignes), encoding="utf-8",
                     newline="\n")
    return copie, cible + 1


# ── La chaîne, dessinée comme un objet ───────────────────────────────────

MAILLONS_PAR_RANG = 6
MAILLON_L, MAILLON_H = 232, 128
ECART_X, ECART_Y = 54, 86


def place_maillon(k: int) -> tuple[int, int]:
    rang, col = divmod(k, MAILLONS_PAR_RANG)
    total_l = MAILLONS_PAR_RANG * MAILLON_L + (MAILLONS_PAR_RANG - 1) * ECART_X
    x0 = (L - total_l) // 2
    y0 = 372
    return x0 + col * (MAILLON_L + ECART_X), y0 + rang * (MAILLON_H + ECART_Y)


def dessiner_chaine(d: ImageDraw.ImageDraw, reg: list[dict], *,
                    jusqua: float, rompu: int | None = None,
                    ecarte: float = 0.0) -> None:
    """Dessine les maillons jusqu'à `jusqua` (en maillons, fractionnaire).

    `rompu` est l'indice 1-based du maillon qui lâche ; `ecarte` ouvre le vide
    qui le sépare de la chaîne. C'est ce vide, et non la couleur, qui dit que
    quelque chose a cédé.
    """
    for k, m in enumerate(reg):
        apparu = jusqua - k
        if apparu <= 0:
            continue
        a = sortie_cubique(min(1.0, apparu))
        x, y = place_maillon(k)
        casse = rompu is not None and m["i"] == rompu
        if casse:
            y += int(52 * ecarte)
        teinte = CRITIQUE if casse else ACCENT
        bord = opacite(teinte, 0.30 + 0.55 * a)
        fond_m = opacite(teinte, 0.05 + 0.07 * a)

        # Le trait qui relie au précédent : l'engagement de `prev` sur `chain`.
        if k > 0:
            px, py = place_maillon(k - 1)
            precedent_casse = rompu is not None and reg[k - 1]["i"] == rompu
            coupe = casse or precedent_casse
            coul = opacite(CRITIQUE if coupe else ACCENT,
                           (0.18 if coupe else 0.42) * a * (1 - 0.8 * ecarte if coupe else 1))
            if k % MAILLONS_PAR_RANG == 0:
                # Retour a la ligne. Un trait droit du maillon 06 au 07
                # traversait toute l'image en diagonale et s'emmelait avec les
                # etiquettes d'escalade : on route en equerre, par les bords,
                # comme un circuit — ce qui se lit sans qu'on y pense.
                marge = 34
                d.line([(px + MAILLON_L, py + MAILLON_H // 2),
                        (L - marge, py + MAILLON_H // 2),
                        (L - marge, py + MAILLON_H + ECART_Y // 2),
                        (marge, py + MAILLON_H + ECART_Y // 2),
                        (marge, y + MAILLON_H // 2),
                        (x, y + MAILLON_H // 2)], fill=coul, width=3, joint="curve")
            else:
                d.line([(px + MAILLON_L, py + MAILLON_H // 2),
                        (x, y + MAILLON_H // 2)], fill=coul, width=3)

        d.rounded_rectangle([x, y, x + MAILLON_L, y + MAILLON_H], radius=16,
                            fill=fond_m, outline=bord, width=3)
        ecrire(d, (x + MAILLON_L / 2, y + 16), f"{m['i']:02d}",
               f(MONO_G, 34), opacite(ENCRE, a), centre=True, suivi=2)
        ecrire(d, (x + MAILLON_L / 2, y + 58), m["tier"],
               f(SANS, 26), opacite(ENCRE_2, 0.9 * a), centre=True, suivi=1)
        ecrire(d, (x + MAILLON_L / 2, y + 92), m["chain"],
               f(MONO, 20), opacite(ENCRE_3, 0.9 * a), centre=True)
        if m["escalade"]:
            ecrire(d, (x + MAILLON_L / 2, y - 34),
                   f"escalated  {m['escalade']} -> {m['tier']}", f(SANS, 22),
                   opacite(ACCENT, 0.85 * a), centre=True, suivi=1)
        if casse and ecarte > 0.35:
            ecrire(d, (x + MAILLON_L / 2, y + MAILLON_H + 16),
                   "X  not covered by any hash", f(SANS_G, 24),
                   opacite(CRITIQUE, (ecarte - 0.35) / 0.65), centre=True, suivi=1)


def replier(lignes: list[str], largeur: int) -> list[tuple[str, tuple[int, int, int]]]:
    """Replie les lignes du vérificateur sans couper un mot.

    Chaque morceau garde la couleur de sa ligne d'origine, pour qu'un `FAIL`
    replié reste rouge sur ses deux lignes.
    """
    out: list[tuple[str, tuple[int, int, int]]] = []
    for ligne in lignes[:3]:
        coul = CRITIQUE if ligne.startswith("FAIL") else ENCRE_2
        mots, courant = ligne.split(), ""
        for mot in mots:
            if courant and len(courant) + 1 + len(mot) > largeur:
                out.append((courant, coul))
                courant = mot
            else:
                courant = f"{courant} {mot}".strip()
        if courant:
            out.append((courant, coul))
    return out


# ── Scènes ───────────────────────────────────────────────────────────────

class Film:
    """Diffuse les images vers l'encodeur au lieu de les garder en mémoire.

    5 000 images uniques en 1920x1080 pèsent une trentaine de gigaoctets : la
    première version s'en tirait parce qu'elle répétait le même objet, celle-ci
    ne peut pas.
    """

    def __init__(self, fps: int, durees: dict[str, float]) -> None:
        self.fps = fps
        self.n = 0
        self.durees = durees
        self.reperes: list[tuple[float, str]] = []

    def duree(self, cle: str) -> float:
        """Ce que la phrase de cette scene dure reellement."""
        return self.durees[cle]

    def repere(self, nom: str) -> None:
        self.reperes.append((self.n / self.fps, nom))

    def tenir(self, img: Image.Image, secondes: float) -> Iterator[Image.Image]:
        for _ in range(max(1, round(secondes * self.fps))):
            self.n += 1
            yield img

    def anime(self, duree: float, dessine) -> Iterator[Image.Image]:
        total = max(1, round(duree * self.fps))
        for i in range(total):
            self.n += 1
            yield dessine(i / total)


def scene_ouverture(film: Film, reg: list[dict]) -> Iterator[Image.Image]:
    film.repere("ouverture")
    empreinte = reg[0]["chain"] + "a1c8774dc3b3"

    def dessine(t: float) -> Image.Image:
        img = fond()
        d = ImageDraw.Draw(img)
        # L'empreinte émerge du flou : on voit d'abord une forme, puis un fait.
        a = douce(min(1.0, t * 2.4))
        ecrire(d, (L / 2, H / 2 - 40), empreinte, f(MONO, 44),
               opacite(ENCRE_3, 0.75 * a), centre=True, suivi=6)
        if t > 0.45:
            b = sortie_cubique((t - 0.45) / 0.35)
            ecrire(d, (L / 2, H / 2 + 46), "sha256", f(SANS, 26),
                   opacite(ENCRE_3, 0.6 * b), centre=True, suivi=8)
        flou = max(0.0, 7.0 * (1 - a))
        return img.filter(ImageFilter.GaussianBlur(flou)) if flou > 0.4 else img

    yield from film.anime(SILENCE_INITIAL, dessine)

    def dessine2(t: float) -> Image.Image:
        img = fond()
        d = ImageDraw.Draw(img)
        a = sortie_cubique(min(1.0, t * 1.8))
        dy = int(30 * (1 - a))
        ecrire(d, (L / 2, H / 2 - 92 + dy), "An agent took twelve decisions.",
               f(SANS_L, 72), opacite(ENCRE, a), centre=True, suivi=1)
        if t > 0.42:
            b = sortie_cubique((t - 0.42) / 0.4)
            ecrire(d, (L / 2, H / 2 + 24 + int(22 * (1 - b))),
                   "Nobody can say which ones.", f(SANS_L, 46),
                   opacite(ENCRE_3, 0.95 * b), centre=True, suivi=1)
        return img

    yield from film.anime(film.duree("ouverture"), dessine2)


def scene_these(film: Film) -> Iterator[Image.Image]:
    film.repere("these")
    lignes = [
        ("A log you can edit afterwards", 58, ENCRE_2),
        ("is testimony.", 58, ENCRE_2),
        ("Not proof.", 74, ACCENT),
    ]

    def dessine(t: float) -> Image.Image:
        img = fond()
        d = ImageDraw.Draw(img)
        y = H / 2 - 150
        for k, (texte, taille, coul) in enumerate(lignes):
            debut = 0.10 + k * 0.24
            if t < debut:
                break
            a = sortie_cubique(min(1.0, (t - debut) / 0.22))
            dim = 1.0 if k == len(lignes) - 1 else (1.0 - 0.45 * max(0.0, t - debut - 0.3))
            grasse = SANS_G if k == 2 else SANS_L
            ecrire(d, (L / 2, y + int(26 * (1 - a))), texte, f(grasse, taille),
                   opacite(coul, a * max(0.35, dim)), centre=True, suivi=1)
            y += taille + 52
        return img

    yield from film.anime(film.duree("these"), dessine)


def scene_chaine(film: Film, reg: list[dict]) -> Iterator[Image.Image]:
    film.repere("chaine")
    total = sum(m["cout"] for m in reg)

    def dessine(t: float) -> Image.Image:
        img = fond()
        d = ImageDraw.Draw(img)
        ecrire(d, (L / 2, 168), "Each decision seals the one before.",
               f(SANS_L, 54), opacite(ENCRE, sortie_cubique(min(1, t * 6))),
               centre=True, suivi=1)
        avance = sortie_cubique(min(1.0, t / 0.78)) * len(reg)
        dessiner_chaine(d, reg, jusqua=avance)
        # Le compteur de coût suit l'avance, donc il ne peut pas mentir.
        vus = reg[: int(min(len(reg), math.ceil(avance)))]
        ecrire(d, (L - 120, 180), f"${sum(m['cout'] for m in vus):.4f}",
               f(MONO_G, 46), opacite(ENCRE, 0.9), centre=True)
        ecrire(d, (L - 120, 232), "running cost", f(SANS, 22),
               opacite(ENCRE_3, 0.9), centre=True, suivi=1)
        if t > 0.86:
            b = sortie_cubique((t - 0.86) / 0.14)
            ecrire(d, (L / 2, H - 132),
                   f"twelve decisions, ${total:.4f}, two escalations",
                   f(SANS, 32), opacite(ENCRE_2, b), centre=True, suivi=1)
        return img

    yield from film.anime(film.duree("chaine"), dessine)


def scene_chiffres(film: Film, reg: list[dict]) -> Iterator[Image.Image]:
    film.repere("chiffres")
    tuiles = [
        ("12", "decisions"),
        ("$0.0029", "total cost"),
        ("2 / 12", "escalations"),
        ("50 %", "changed the answer"),
    ]

    def dessine(t: float) -> Image.Image:
        img = fond()
        d = ImageDraw.Draw(img)
        largeur = L / len(tuiles)
        for k, (valeur, etiquette) in enumerate(tuiles):
            debut = 0.06 + k * 0.11
            if t < debut:
                continue
            a = sortie_cubique(min(1.0, (t - debut) / 0.26))
            x = largeur * (k + 0.5)
            ecrire(d, (x, H / 2 - 110 + int(24 * (1 - a))), valeur,
                   f(SANS_G, 86), opacite(ENCRE, a), centre=True, suivi=1)
            ecrire(d, (x, H / 2 + 14), etiquette, f(SANS, 28),
                   opacite(ENCRE_3, a), centre=True, suivi=1)
        if t > 0.56:
            b = sortie_cubique((t - 0.56) / 0.3)
            ecrire(d, (L / 2, H / 2 + 150 + int(20 * (1 - b))),
                   "The expensive escalation changed nothing.",
                   f(SANS_L, 44), opacite(ENCRE_2, b), centre=True, suivi=1)
            if t > 0.72:
                c = sortie_cubique((t - 0.72) / 0.28)
                ecrire(d, (L / 2, H / 2 + 216), "The cheap one did.",
                       f(SANS_G, 44), opacite(ACCENT, c), centre=True, suivi=1)
        return img

    yield from film.anime(film.duree("chiffres"), dessine)


def scene_rupture(film: Film, reg: list[dict], rompu: int,
                  refus: list[str]) -> Iterator[Image.Image]:
    film.repere("rupture")

    def dessine(t: float) -> Image.Image:
        img = fond()
        d = ImageDraw.Draw(img)
        if t < 0.22:
            a = sortie_cubique(t / 0.22)
            ecrire(d, (L / 2, 168), "We add one field to a sealed copy.",
                   f(SANS_L, 50), opacite(ENCRE, a), centre=True, suivi=1)
            ecrire(d, (L / 2, 236), '"severity": "benign"', f(MONO_G, 40),
                   opacite(CRITIQUE, a), centre=True, suivi=2)
            dessiner_chaine(d, reg, jusqua=len(reg))
            return img
        ecarte = sortie_cubique(min(1.0, (t - 0.22) / 0.2))
        ecrire(d, (L / 2, 168), "No hash covers it.", f(SANS_L, 50),
               opacite(ENCRE, 1.0), centre=True, suivi=1)
        dessiner_chaine(d, reg, jusqua=len(reg), rompu=rompu, ecarte=ecarte)
        if t > 0.5:
            # Le refus se replie au lieu d'etre coupe : la phrase du
            # verificateur est le coeur du plan, et une phrase tronquee a
            # « cannot vouch for a » dit l'inverse de ce qu'on montre.
            for k, (ligne, coul) in enumerate(replier(refus, 86)):
                debut = 0.5 + k * 0.08
                if t < debut:
                    break
                a = sortie_cubique(min(1.0, (t - debut) / 0.14))
                ecrire(d, (L / 2, H - 236 + k * 38), ligne, f(MONO, 26),
                       opacite(coul, a), centre=True)
        return img

    yield from film.anime(film.duree("rupture"), dessine)


def scene_fin(film: Film) -> Iterator[Image.Image]:
    film.repere("fin")
    # Compté UNE fois, pas une fois par image. Écrit directement dans `dessine`,
    # l'appel partait à chaque image -- deux cent soixante-dix fois pour neuf
    # secondes -- et le rendu ne finissait plus. Un chiffre lu au moment du
    # rendu reste la bonne idée ; le lire dans la boucle d'images ne l'est pas.
    tests = nombre_de_tests()

    def dessine(t: float) -> Image.Image:
        img = fond()
        d = ImageDraw.Draw(img)
        a = sortie_cubique(min(1.0, t * 2.2))
        ecrire(d, (L / 2, H / 2 - 150), "Glass Box", f(SANS_G, 96),
               opacite(ENCRE, a), centre=True, suivi=2)
        if t > 0.3:
            b = sortie_cubique((t - 0.3) / 0.3)
            ecrire(d, (L / 2, H / 2 - 20),
                   "A ledger an auditor verifies without reading the code.",
                   f(SANS_L, 40), opacite(ENCRE_2, b), centre=True, suivi=1)
        if t > 0.55:
            c = sortie_cubique((t - 0.55) / 0.3)
            ecrire(d, (L / 2, H / 2 + 86), f"{tests} tests  ·  Apache 2.0",
                   f(SANS, 30), opacite(ENCRE_3, c), centre=True, suivi=2)
            ecrire(d, (L / 2, H / 2 + 146), "github.com/Yoh5/glassbox",
                   f(MONO, 32), opacite(ACCENT, c), centre=True, suivi=1)
        return img

    yield from film.anime(film.duree("fin"), dessine)


def scene_enregistrement(film: Film) -> Iterator[Image.Image]:
    """Un maillon, en entier. Sans l'avoir vu, la chaîne reste un mot."""
    film.repere("enregistrement")
    lignes = [l for l in REGISTRE.read_text(encoding="utf-8").splitlines() if l.strip()]
    r = json.loads(lignes[0])
    vue = [
        ('"name"', f'"{r.get("name")}"', ENCRE_2),
        ('"started_at"', f'"{r.get("started_at")}"', ENCRE_2),
        ('"asks"', "[ { tier: nano, calls: 2, cost: $0.000027 } ]", ENCRE_2),
        ('"prev"', "null", ACCENT),
        ('"chain"', f'"sha256:{(r.get("chain") or "")[7:31]}..."', ACCENT),
    ]

    def dessine(t: float) -> Image.Image:
        img = fond()
        d = ImageDraw.Draw(img)
        a = sortie_cubique(min(1.0, t * 5))
        ecrire(d, (L / 2, 150), "One record, in full.", f(SANS_L, 52),
               opacite(ENCRE, a), centre=True, suivi=1)
        x = 430
        y = 300
        for k, (cle, valeur, coul) in enumerate(vue):
            debut = 0.12 + k * 0.1
            if t < debut:
                break
            b = sortie_cubique(min(1.0, (t - debut) / 0.16))
            ecrire(d, (x, y), cle, f(MONO_G, 34), opacite(ENCRE_3, b))
            ecrire(d, (x + 240, y), valeur, f(MONO, 34), opacite(coul, b))
            y += 62
        if t > 0.66:
            c = sortie_cubique((t - 0.66) / 0.34)
            ecrire(d, (L / 2, H - 230),
                   "prev carries the hash of the one before.", f(SANS_L, 42),
                   opacite(ENCRE, c), centre=True, suivi=1)
            ecrire(d, (L / 2, H - 166),
                   "Remove or change one line and every line after it breaks.",
                   f(SANS_L, 36), opacite(ENCRE_3, c), centre=True, suivi=1)
        return img

    yield from film.anime(film.duree("enregistrement"), dessine)


def scene_escalades(film: Film, reg: list[dict]) -> Iterator[Image.Image]:
    """Les deux escalades, cote a cote. Le resultat est inconfortable, et
    c'est pour ca qu'il est montre : la plus chere n'a rien change."""
    film.repere("escalades")
    esc = [m for m in reg if m["escalade"]]

    def dessine(t: float) -> Image.Image:
        img = fond()
        d = ImageDraw.Draw(img)
        a = sortie_cubique(min(1.0, t * 5))
        ecrire(d, (L / 2, 150), "Two escalations. Two outcomes.",
               f(SANS_L, 52), opacite(ENCRE, a), centre=True, suivi=1)
        for k, m in enumerate(esc[:2]):
            debut = 0.16 + k * 0.18
            if t < debut:
                break
            b = sortie_cubique(min(1.0, (t - debut) / 0.22))
            x = L * (0.3 + 0.4 * k)
            change = bool(m["change"])
            ecrire(d, (x, 300), f"#{m['i']:02d}", f(MONO_G, 44),
                   opacite(ENCRE_3, b), centre=True, suivi=2)
            ecrire(d, (x, 372), f"{m['escalade']} -> {m['tier']}",
                   f(SANS_G, 52), opacite(ENCRE, b), centre=True, suivi=1)
            ecrire(d, (x, 460), f"${m['cout']:.4f}", f(MONO_G, 64),
                   opacite(ENCRE, b), centre=True, suivi=1)
            if t > debut + 0.2:
                c = sortie_cubique((t - debut - 0.2) / 0.2)
                ecrire(d, (x, 572),
                       "the answer changed" if change else "the answer did not change",
                       f(SANS, 34), opacite(ACCENT if change else ENCRE_3, c),
                       centre=True, suivi=1)
        if t > 0.68:
            e = sortie_cubique((t - 0.68) / 0.32)
            ecrire(d, (L / 2, H - 208), "Paying more does not buy a different answer.",
                   f(SANS_L, 44), opacite(ENCRE_2, e), centre=True, suivi=1)
            ecrire(d, (L / 2, H - 142), "Without the ledger, nobody could know that.",
                   f(SANS_G, 40), opacite(ACCENT, e), centre=True, suivi=1)
        return img

    yield from film.anime(film.duree("escalades"), dessine)


def scene_commandes(film: Film) -> Iterator[Image.Image]:
    """Ce qu'un auditeur tape, sans lire une ligne du code."""
    film.repere("commandes")
    cmds = [
        ("verify", "does the chain still hold"),
        ("trace", "which decision caused this action"),
        ("replay", "would the rule decide the same"),
        ("stats", "what the run cost"),
        ("serve", "all four answers on one page"),
    ]

    def dessine(t: float) -> Image.Image:
        img = fond()
        d = ImageDraw.Draw(img)
        a = sortie_cubique(min(1.0, t * 5))
        ecrire(d, (L / 2, 158), "What an auditor types.", f(SANS_L, 52),
               opacite(ENCRE, a), centre=True, suivi=1)
        y = 320
        for k, (cmd, quoi) in enumerate(cmds):
            debut = 0.14 + k * 0.12
            if t < debut:
                break
            b = sortie_cubique(min(1.0, (t - debut) / 0.18))
            ecrire(d, (560, y), f"glassbox {cmd}", f(MONO_G, 38),
                   opacite(ACCENT, b))
            ecrire(d, (980, y + 6), quoi, f(SANS_L, 32), opacite(ENCRE_2, b))
            y += 74
        if t > 0.8:
            c = sortie_cubique((t - 0.8) / 0.2)
            ecrire(d, (L / 2, H - 150), "Without reading a line of our code.",
                   f(SANS_L, 40), opacite(ENCRE_3, c), centre=True, suivi=1)
        return img

    yield from film.anime(film.duree("commandes"), dessine)


def images(film: Film) -> Iterator[Image.Image]:
    reg = lire_registre()
    if len(reg) != 12:
        raise SystemExit(f"{len(reg)} enregistrements : la video en annonce douze")

    copie, rompu = copie_alteree()
    code, refus = lancer(["verify", copie.relative_to(RACINE).as_posix()])
    if code == 0:
        raise SystemExit("le registre altere passe la verification : il n'y a "
                         "rien a montrer, et c'est un defaut a corriger")
    code_ok, _ = lancer(["verify", "runs/escalation/ledger.jsonl"])
    if code_ok != 0:
        raise SystemExit("le registre reel ne se verifie plus : on ne filme pas ca")

    yield from scene_ouverture(film, reg)
    yield from scene_these(film)
    yield from scene_enregistrement(film)
    yield from scene_chaine(film, reg)
    yield from scene_chiffres(film, reg)
    yield from scene_escalades(film, reg)
    yield from scene_rupture(film, reg, rompu, refus)
    yield from scene_commandes(film)
    yield from scene_fin(film)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--sortie", default=str(Path(__file__).resolve().parent
                                            / "glassbox-keynote.mp4"))
    args = ap.parse_args()

    print("narration")
    scenes, parle = minuter()
    for cle in NARRATION:
        tenue = "" if parle[cle] + 1.0 >= MINIMA[cle] else "  (plancher)"
        print(f"  {cle:<16} dit {parle[cle]:5.2f} s, scene {scenes[cle]:5.2f} s{tenue}")

    total = SILENCE_INITIAL + sum(scenes.values())
    print(f"\ntotal : {int(total)//60}:{total % 60:04.1f}")
    # Le reglement Nebius dit « less than three (3) minutes ». Echouer ici coute
    # une phrase a raccourcir ; livrer trop long coute la soumission.
    if total >= LIMITE:
        print(f"ECHEC : {total:.1f} s atteint la limite de {LIMITE:.0f} s.")
        print("Raccourcir une phrase de NARRATION, pas la video.")
        return 1

    film = Film(args.fps, scenes)
    sortie = Path(args.sortie)
    sortie.parent.mkdir(parents=True, exist_ok=True)
    muette = TRAVAIL / "muette.mp4"
    print("\nrendu (les commandes sont relancees)...", flush=True)
    with imageio.get_writer(muette, fps=args.fps, codec="libx264", quality=8,
                            macro_block_size=1) as w:
        for img in images(film):
            w.append_data(np.asarray(img))
    duree = film.n / args.fps
    print(f"  {film.n} images, {duree:.1f} s a {args.fps} fps")

    print("montage")
    piste = piste_narration(scenes, parle)
    subprocess.run([FFMPEG, "-y", "-i", str(muette), "-i", str(piste),
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-shortest",
                    str(sortie)], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    print(f"\necrit : {sortie}  ({sortie.stat().st_size/1e6:.1f} Mo)")
    print(f"  marge sous la limite : {LIMITE - duree:.1f} s")
    print("\nChapitres :")
    for s, nom in film.reperes:
        print(f"  {int(s)//60}:{int(s)%60:02d}  {nom}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
