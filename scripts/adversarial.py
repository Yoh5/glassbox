"""Adversarial bench: which attacks on a ledger does Glass Box actually catch?

The README opens with *"if someone rewrites the history, it shows"*. That is a
claim about an adversary, and a claim about an adversary is only worth what the
attempts against it are worth. The test suite covers four tampering cases, all
of them edits. An edit is the attack you think of first, and it is not the one
an operator with something to hide would use.

So this bench runs a set of attacks against a real ledger, reports which are
caught and — the part that matters — **which are not**. Every row is produced by
running the shipped `glassbox verify`, not by reasoning about what it ought to
do.

Three of these attacks cannot be caught by a hash chain alone, and saying so is
the point. A chain proves that the records it contains follow one another. It
proves nothing about records it does not contain, and nothing about *when* any
of them was written. An honest tool states its perimeter instead of letting a
reader assume a wider one.

    python scripts/adversarial.py
    python scripts/adversarial.py --json bench.json

Exit code 1 if an attack that is expected to be caught is not — so the bench is
a regression test for the guarantee, not only a document.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from glassbox.ledger import _canonical, _chain_hash  # noqa: E402

#: Le registre de référence : celui que la soumission publie. Douze décisions,
#: et aucune pièce citée.
#:
#: **Ce n'est pas un oubli, et la première version de ce commentaire le
#: présentait à tort comme tel.** `scripts/hosted.py` documente la raison et
#: dit l'avoir vérifiée plutôt que supposée : un registre de décisions est
#: l'artefact le plus sensible d'un agent — ce qu'il a lu, ce qu'on lui a dit,
#: ce qu'il a fait — et celui qu'on publie ne porte donc ni prompt, ni réponse,
#: ni octet de preuve. C'est précisément ce que le projet défend, appliqué à
#: lui-même.
REGISTRE = RACINE / "runs" / "escalation" / "ledger.jsonl"

#: D'où la seconde base : la course d'injection de `examples/injected_page.py`,
#: qui cite de vraies pièces. Le banc la régénère plutôt que de la stocker, pour
#: qu'elle ne puisse pas vieillir à côté du code.
#:
#: Ce détour n'est pas une commodité : la première version de ce banc annonçait
#: que « pièce jointe modifiée » n'était pas attrapée. Faux deux fois — le
#: registre visé ne citait aucune pièce, et `verify` ne contrôle le magasin que
#: si on lui passe `--evidence`. Le banc accusait l'outil de sa propre erreur.
EXEMPLE_INJECTION = RACINE / "examples" / "injected_page.py"


def _base_avec_pieces() -> tuple[Path, Path]:
    """Génère une course qui cite des pièces, et rend (registre, magasin)."""
    r = subprocess.run([sys.executable, str(EXEMPLE_INJECTION)],
                       capture_output=True, text=True, cwd=str(RACINE),
                       timeout=180)
    if r.returncode != 0:
        raise SystemExit("l'exemple d'injection a échoué : " + r.stderr)
    registre = magasin = None
    for ligne in r.stdout.splitlines():
        if ligne.startswith("ledger:"):
            registre = Path(ligne.split(":", 1)[1].strip())
        elif ligne.startswith("evidence:"):
            magasin = Path(ligne.split(":", 1)[1].strip())
    if not registre or not magasin:
        raise SystemExit("impossible de localiser la course générée")
    return registre, magasin


@dataclass
class Attaque:
    """Une attaque, ce qu'elle modélise, et ce qu'on attend du vérificateur."""
    nom: str
    modele: str
    #: `True` si la garantie annoncée exige que ce soit attrapé.
    doit_etre_attrapee: bool
    appliquer: Callable[[List[dict], Path], List[dict]]
    #: `True` quand l'attaque n'a de sens que sur une course citant des pièces.
    exige_pieces: bool = False
    #: Appelé sur le fichier de registre APRÈS écriture. Les attaques ci-dessus
    #: manipulent des enregistrements, donc elles ne peuvent produire que du
    #: JSON valide — et c'est précisément l'angle mort que ce banc a eu : il
    #: n'avait jamais essayé de simplement casser le fichier.
    apres: Optional[Callable[[Path], None]] = None
    #: Rempli à l'exécution : avec la chaîne seule, puis avec l'engagement.
    attrapee: Optional[bool] = None
    attrapee_avec_engagement: Optional[bool] = None
    sortie: str = ""
    code: Optional[int] = None
    consequence: str = ""


def _lire(chemin: Path) -> List[dict]:
    return [json.loads(l) for l in chemin.read_text(encoding="utf-8").splitlines() if l.strip()]


def _ecrire(enregistrements: List[dict], chemin: Path) -> None:
    chemin.write_text(
        "\n".join(json.dumps(e, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False) for e in enregistrements) + "\n",
        encoding="utf-8")


def _rechainer(enregistrements: List[dict]) -> List[dict]:
    """Recalcule toute la chaîne — ce que fait quiconque tient l'outil d'écriture."""
    prev = None
    for e in enregistrements:
        corps = {k: v for k, v in e.items() if k not in ("prev", "chain")}
        e["prev"] = prev
        e["chain"] = _chain_hash(corps, prev)
        prev = e["chain"]
    return enregistrements


# --------------------------------------------------------------------------- #
# Les attaques
# --------------------------------------------------------------------------- #
def champ_modifie(e: List[dict], _: Path) -> List[dict]:
    e[5]["outcome"] = {**e[5]["outcome"], "reason": "Something else"}
    return e


def enregistrement_supprime(e: List[dict], _: Path) -> List[dict]:
    del e[5]
    return e


def enregistrements_permutes(e: List[dict], _: Path) -> List[dict]:
    e[4], e[5] = e[5], e[4]
    return e


def horodatage_recule(e: List[dict], _: Path) -> List[dict]:
    e[5]["started_at"] = "2020-01-01T00:00:00Z"
    return e


def cout_minore(e: List[dict], _: Path) -> List[dict]:
    """Le mobile le plus banal : faire paraître une facture plus basse."""
    appels = e[5].get("model_calls") or []
    if appels:
        appels[0] = {**appels[0], "cost_usd": 0.0}
    return e


def troncature(e: List[dict], _: Path) -> List[dict]:
    """On n'altère rien : on arrête l'histoire plus tôt.

    C'est l'attaque de l'opérateur qui n'a rien à réécrire — juste des dernières
    décisions à ne pas montrer.
    """
    return e[:8]


def retour_en_arriere(e: List[dict], _: Path) -> List[dict]:
    """Republier une version antérieure, valide, du même registre."""
    return e[:3]


def ajout_force(e: List[dict], _: Path) -> List[dict]:
    """Ajouter une décision qui n'a jamais eu lieu, correctement chaînée."""
    faux = json.loads(json.dumps(e[-1]))
    faux["name"] = "approved-by-nobody"
    faux["outcome"] = {"action": "approved", "reason": "looks fine"}
    corps = {k: v for k, v in faux.items() if k not in ("prev", "chain")}
    faux["prev"] = e[-1]["chain"]
    faux["chain"] = _chain_hash(corps, e[-1]["chain"])
    return e + [faux]


def reecriture_complete(e: List[dict], _: Path) -> List[dict]:
    """L'adversaire tient l'outil d'écriture et recalcule toute la chaîne."""
    e[5]["outcome"] = {**e[5]["outcome"], "reason": "Something else"}
    return _rechainer(e)


def piece_jointe_modifiee(e: List[dict], travail: Path) -> List[dict]:
    """Le registre est intact ; c'est la pièce citée qui a changé sur le disque."""
    pieces = travail / "evidence"
    for f in sorted(pieces.rglob("*")) if pieces.exists() else []:
        if f.is_file():
            f.write_bytes(f.read_bytes() + b" altered")
            break
    return e


def octet_corrompu(registre: Path) -> None:
    """Un octet ajouté à la fin. L'attaque la moins chère qui existe.

    Elle faisait lever `JSONDecodeError` à `verify` au lieu de lui faire rendre
    un verdict : un auditeur ne pouvait pas distinguer un registre cassé d'un
    outil cassé, et un script non plus, les deux sortant non nuls. Et comme
    `append` lit la dernière chaîne avant d'écrire, le greffier ne pouvait plus
    rien enregistrer — un déni d'enregistrement pour un octet.
    """
    registre.write_text(registre.read_text(encoding="utf-8") + "x\n",
                        encoding="utf-8")


def ligne_remplacee_par_du_bruit(registre: Path) -> None:
    """Une décision écrasée par du bruit : une suppression déguisée en panne.

    Un lecteur qui se contenterait de sauter la ligne illisible rendrait cette
    attaque gratuite — sauter sans le dire est exactement la suppression.
    """
    lignes = registre.read_text(encoding="utf-8").splitlines()
    lignes[5] = "}{ ceci n'est pas une decision"
    registre.write_text("\n".join(lignes) + "\n", encoding="utf-8")


def cles_retirees(registre: Path) -> None:
    """Une décision vidée de ses champs obligatoires, en restant du JSON valide."""
    lignes = registre.read_text(encoding="utf-8").splitlines()
    lignes[5] = json.dumps({"chain": "sha256:" + "0" * 64})
    registre.write_text("\n".join(lignes) + "\n", encoding="utf-8")


ATTAQUES = [
    Attaque("champ modifié", "une valeur réécrite dans une décision", True,
            champ_modifie),
    Attaque("enregistrement supprimé", "une décision retirée du milieu", True,
            enregistrement_supprime),
    Attaque("enregistrements permutés", "deux décisions interverties", True,
            enregistrements_permutes),
    Attaque("horodatage reculé", "une décision antidatée", True,
            horodatage_recule),
    Attaque("coût minoré", "une facture rendue plus basse qu'elle n'était", True,
            cout_minore),
    Attaque("pièce jointe modifiée", "la preuve citée changée sur le disque", True,
            piece_jointe_modifiee, exige_pieces=True),
    Attaque("troncature", "la fin de l'histoire coupée", False, troncature),
    Attaque("retour en arrière", "une version antérieure republiée", False,
            retour_en_arriere),
    Attaque("ajout forgé", "une décision inventée, correctement chaînée", False,
            ajout_force),
    Attaque("réécriture complète", "l'adversaire tient l'outil d'écriture", False,
            reecriture_complete),
    # Les trois suivantes ne passent pas par les enregistrements : elles
    # abîment le fichier. Ajoutées le 14/10/2026, parce que les dix premières
    # produisaient toutes du JSON valide — le banc vérifiait la solidité de la
    # chaîne et jamais celle du lecteur.
    Attaque("octet corrompu", "un octet ajouté à la fin du fichier", True,
            lambda e, _: e, apres=octet_corrompu),
    Attaque("ligne remplacée par du bruit", "une décision écrasée, pas retirée", True,
            lambda e, _: e, apres=ligne_remplacee_par_du_bruit),
    Attaque("champs obligatoires retirés", "du JSON valide qui n'est pas un enregistrement",
            True, lambda e, _: e, apres=cles_retirees),
]


# --------------------------------------------------------------------------- #
# Exécution
# --------------------------------------------------------------------------- #
def _verifier(registre: Path, pieces: Optional[Path],
              engagement: Optional[tuple[int, str]] = None) -> tuple[int, str]:
    """`verify`, avec le magasin quand il y en a un.

    Sans `--evidence`, `verify` ne regarde pas les pièces du tout : il re-chaîne
    le registre et s'arrête là. Oublier le drapeau fait donc passer une
    altération de preuve pour un trou de la garantie.
    """
    cmd = [sys.executable, "-m", "glassbox", "verify", str(registre)]
    if pieces is not None and pieces.exists():
        cmd += ["--evidence", str(pieces)]
    if engagement is not None:
        cmd += ["--expect-count", str(engagement[0]), "--expect-head", engagement[1]]
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(RACINE),
                       timeout=120)
    return r.returncode, (r.stdout + r.stderr).strip()


def _engagement(registre: Path) -> tuple[int, str]:
    """Le couple (compte, tête) tel qu'un tiers l'aurait noté avant l'attaque."""
    r = subprocess.run([sys.executable, "-m", "glassbox", "head", str(registre)],
                       capture_output=True, text=True, cwd=str(RACINE), timeout=120)
    compte = tete = None
    for ligne in r.stdout.splitlines():
        if ligne.startswith("decisions"):
            compte = int(ligne.split()[1])
        elif ligne.startswith("head"):
            tete = ligne.split()[1]
    if compte is None or tete is None:
        raise SystemExit("impossible de lire l'engagement : " + r.stdout + r.stderr)
    return compte, tete


def _stats(registre: Path) -> str:
    r = subprocess.run(
        [sys.executable, "-m", "glassbox", "stats", str(registre)],
        capture_output=True, text=True, cwd=str(RACINE), timeout=120)
    return (r.stdout + r.stderr).strip()


def _consequence(avant: str, apres: str) -> str:
    """Ce que l'attaque fait dire à `stats` — car un adversaire ne falsifie pas
    pour le plaisir, il falsifie pour qu'un chiffre change."""
    a = {l.split()[0]: " ".join(l.split()[1:]) for l in avant.splitlines() if l.split()}
    b = {l.split()[0]: " ".join(l.split()[1:]) for l in apres.splitlines() if l.split()}
    ecarts = [f"{k} : {a[k]} -> {b[k]}" for k in a if k in b and a[k] != b[k]]
    return " ; ".join(ecarts[:2])


def lancer(attaques=ATTAQUES) -> List[Attaque]:
    reg_pieces, magasin = _base_avec_pieces()
    bases = {
        False: (_lire(REGISTRE), None, _stats(REGISTRE)),
        True: (_lire(reg_pieces), magasin, _stats(reg_pieces)),
    }
    engagements = {False: _engagement(REGISTRE), True: _engagement(reg_pieces)}
    for att in attaques:
        base, pieces, avant = bases[att.exige_pieces]
        with tempfile.TemporaryDirectory() as d:
            travail = Path(d)
            if pieces is not None:
                shutil.copytree(pieces, travail / "evidence")
            cible = travail / "ledger.jsonl"
            _ecrire(att.appliquer(json.loads(json.dumps(base)), travail), cible)
            if att.apres is not None:
                att.apres(cible)
            magasin_cible = travail / "evidence" if pieces is not None else None
            att.code, att.sortie = _verifier(cible, magasin_cible)
            att.attrapee = att.code != 0
            # Seconde passe : ce que voit quelqu'un qui avait noté la tête.
            code2, _ = _verifier(cible, magasin_cible, engagements[att.exige_pieces])
            att.attrapee_avec_engagement = code2 != 0
            att.consequence = _consequence(avant, _stats(cible))
    return attaques


def rapport(attaques: List[Attaque]) -> int:
    largeur = max(len(a.nom) for a in attaques)
    print("BANC D'ESSAI ADVERSE — ce que le vérificateur attrape, et ce qu'il laisse\n")
    print(f"{'attaque':<{largeur}}  {'ce quelle modélise':<44} "
          f"{'chaîne':>7} {'+ tête notée':>13}")
    print("-" * (largeur + 70))
    surprises = []
    for a in attaques:
        m1 = "oui" if a.attrapee else "NON"
        m2 = "oui" if a.attrapee_avec_engagement else "NON"
        print(f"{a.nom:<{largeur}}  {a.modele:<44} {m1:>7} {m2:>13}")
        if a.attrapee != a.doit_etre_attrapee:
            surprises.append(a)

    laissees = [a for a in attaques if not a.attrapee]
    if laissees:
        print("\nCE QUI PASSE, ET CE QUE ÇA PERMET DE RACONTER :\n")
        for a in laissees:
            print(f"  {a.nom} — {a.modele}")
            print(f"      le vérificateur dit : {a.sortie.splitlines()[0][:72]}")
            if a.consequence:
                print(f"      et les chiffres suivent : {a.consequence}")
            print()

    attrapees = sum(1 for a in attaques if a.attrapee)
    avec = sum(1 for a in attaques if a.attrapee_avec_engagement)
    print(f"Avec la chaîne seule : {attrapees} attaque(s) sur {len(attaques)}.")
    print(f"Avec une tête notée ailleurs : {avec} sur {len(attaques)}.")
    restantes = [a for a in attaques if not a.attrapee_avec_engagement]
    if restantes:
        print("\nCe qui passe encore : " + ", ".join(a.nom for a in restantes))
    else:
        print("\nToutes sont attrapées — à condition que la tête ait été notée")
        print("par quelqu'un que l'adversaire ne contrôle pas. C'est la")
        print("condition, et elle n'est pas technique : rien ici ne prouve")
        print("QUAND un enregistrement a été écrit — c'est à ça que sert un")
        print("ancrage externe.")
    if surprises:
        print("\nREGRESSIONS — attendues attrapées et passées quand même :")
        for a in surprises:
            print(f"  - {a.nom}")
        return 1
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", help="écrire le détail dans ce fichier")
    args = ap.parse_args()
    attaques = lancer()
    code = rapport(attaques)
    if args.json:
        Path(args.json).write_text(json.dumps([{
            "nom": a.nom, "modele": a.modele, "attrapee": a.attrapee,
            "attendue_attrapee": a.doit_etre_attrapee, "code": a.code,
            "sortie": a.sortie, "consequence": a.consequence,
        } for a in attaques], ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\necrit : {args.json}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
