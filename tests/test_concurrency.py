"""Plusieurs fils qui décident en même temps.

Trouvé en branchant la bibliothèque sur un vrai agent : son deep-dive tourne
sur quatre fils, et chacun voulait écrire une décision. Le chaînage lit la
dernière ligne pour calculer la suivante — deux fils qui font ça ensemble
produisent deux records qui pointent le même prédécesseur, et la chaîne casse.

Le contournement (collecter puis écrire) marche, mais une bibliothèque qui
oblige à le découvrir est une bibliothèque qui casse chez quelqu'un d'autre.
"""

from concurrent.futures import ThreadPoolExecutor

from glassbox.evidence import EvidenceStore
from glassbox.ledger import Ledger
from glassbox.recorder import Recorder


def test_douze_decisions_ecrites_par_quatre_fils_gardent_une_chaine_valide(tmp_path):
    led = Ledger(tmp_path / "ledger.jsonl")

    def write(index: int) -> None:
        led.append(name=f"d{index}", started_at="2026-10-14T09:31:07Z", agent_version="v1")

    with ThreadPoolExecutor(max_workers=4) as ex:
        list(ex.map(write, range(12)))

    assert len(led.records()) == 12
    assert led.verify() == []


def test_aucune_decision_n_est_perdue_sous_concurrence(tmp_path):
    led = Ledger(tmp_path / "ledger.jsonl")

    with ThreadPoolExecutor(max_workers=8) as ex:
        list(ex.map(
            lambda i: led.append(name=f"d{i}", started_at="2026-10-14T09:31:07Z",
                                 agent_version="v1"),
            range(40),
        ))

    assert {r.name for r in led.records()} == {f"d{i}" for i in range(40)}


def test_le_recorder_refuse_toujours_deux_blocs_imbriques_dans_un_meme_fil(tmp_path):
    # Le verrou protège le fichier, pas la sémantique : un bloc dans un bloc
    # décrirait encore deux décisions en une.
    rec = Recorder(tmp_path, agent_version="v1")

    try:
        with rec.decision("outer"):
            with rec.decision("inner"):
                pass
    except RuntimeError as error:
        assert "already" in str(error)
    else:
        raise AssertionError("l'imbrication doit rester refusée")


def test_le_magasin_de_preuves_supporte_les_ecritures_paralleles(tmp_path):
    store = EvidenceStore(tmp_path / "evidence")

    with ThreadPoolExecutor(max_workers=6) as ex:
        items = list(ex.map(
            lambda i: store.put(source=f"https://example.org/{i}",
                                payload=f"page {i}".encode(),
                                fetched_at="2026-10-14T09:31:00Z"),
            range(30),
        ))

    assert len({i.id for i in items}) == 30
    assert store.verify() == []
