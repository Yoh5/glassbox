"""Une question dit sur quelles preuves elle repose.

Les preuves étaient citées sur la **décision**, jamais sur la question. Une
décision qui lit trois documents et pose deux questions ne laissait aucun moyen
de savoir laquelle reposait sur lequel — alors que « sur quelle information
cette décision reposait-elle » est la première des trois questions auxquelles ce
projet existe pour répondre.

Trouvé en passant l'OWASP Top 10 for LLM Applications 2026 sur ce dépôt, sous le
risque n° 1. Le volet sécurité est le plus connu et c'est le plus petit : la
bibliothèque n'offrait aucun moyen de passer une preuve autrement qu'en la
concaténant dans l'instruction, et son propre exemple écrivait
`ask(f"Summarise this page: {page.payload.decode()}")`.

**Rien ici n'empêche une injection de prompt, et rien ne doit le laisser croire.**
Aucun délimiteur n'est une frontière de sécurité. Ce qu'on gagne est que le
registre dit quels octets ont été offerts comme matière — de sorte que lorsqu'un
agent obéit à une instruction injectée, `trace` remonte jusqu'au document exact.
"""

from __future__ import annotations

import json
import pathlib

from glassbox.recorder import Recorder
from glassbox.router import Router


def routeur(reponse: str = "ok"):
    """Un routeur qui retient le prompt réellement envoyé."""
    vus: list[str] = []

    def appeler(tier: str, prompt: str) -> tuple[str, float]:
        vus.append(prompt)
        return reponse, 0.0001

    return Router(appeler, tiers=("nano",), samples=2), vus


def enregistreur(tmp_path, reponse: str = "ok"):
    r, vus = routeur(reponse)
    return Recorder(tmp_path, agent_version="a1b2c3d", router=r), vus


def registre(rec: Recorder) -> dict:
    return json.loads(rec.ledger.path.read_text(encoding="utf-8").splitlines()[0])


def test_sans_preuve_l_instruction_part_telle_quelle(tmp_path):
    """Les appelants existants ne doivent voir aucune différence, et un prompt
    enrobé sans raison rendrait les anciennes mesures incomparables."""
    rec, vus = enregistreur(tmp_path)
    with rec.decision("ask") as d:
        d.ask("quelle est la capitale de la France ?")

    assert vus[0] == "quelle est la capitale de la France ?"


def test_la_preuve_est_annoncee_par_sa_source_et_sa_date(tmp_path):
    rec, vus = enregistreur(tmp_path)
    with rec.decision("resumer") as d:
        page = d.evidence(source="https://blog.example.net/post", payload=b"<p>bonjour</p>")
        d.ask("Resume cette page", evidence=[page])

    envoye = vus[0]
    assert envoye.startswith("Resume cette page")
    assert "https://blog.example.net/post" in envoye
    assert page.fetched_at in envoye
    assert "<p>bonjour</p>" in envoye


def test_la_question_enregistre_les_preuves_sur_lesquelles_elle_reposait(tmp_path):
    """Le cœur du correctif : deux questions, deux documents, et le registre
    dit laquelle reposait sur lequel."""
    rec, _ = enregistreur(tmp_path)
    with rec.decision("deux-questions") as d:
        a = d.evidence(source="https://example.org/a", payload=b"document A")
        b = d.evidence(source="https://example.org/b", payload=b"document B")
        d.ask("question sur A", evidence=[a])
        d.ask("question sur B", evidence=[b])

    asks = registre(rec)["asks"]
    assert len(asks) == 2
    assert asks[0]["evidence"] == [a.id]
    assert asks[1]["evidence"] == [b.id]
    assert a.id != b.id


def test_une_preuve_passee_a_une_question_est_aussi_citee_par_la_decision(tmp_path):
    """Sinon la chaîne de traçabilité se coupe : `trace` part des preuves de la
    décision, et une preuve connue de la seule question serait invisible."""
    rec, _ = enregistreur(tmp_path)
    store = rec.store
    item = store.put(source="https://example.org/x", payload=b"hors decision",
                     fetched_at="2026-10-08T00:00:00Z")
    with rec.decision("ask") as d:
        d.ask("une question", evidence=[item])

    assert registre(rec)["evidence"] == [item.id]


def test_une_preuve_n_est_pas_citee_deux_fois(tmp_path):
    rec, _ = enregistreur(tmp_path)
    with rec.decision("ask") as d:
        page = d.evidence(source="https://example.org/p", payload=b"p")
        d.ask("premiere", evidence=[page])
        d.ask("seconde", evidence=[page])

    assert registre(rec)["evidence"] == [page.id]


def test_plusieurs_preuves_sont_numerotees_et_refermees(tmp_path):
    """Deux blocs non délimités se lisent comme un seul document."""
    rec, vus = enregistreur(tmp_path)
    with rec.decision("ask") as d:
        a = d.evidence(source="https://example.org/a", payload=b"AAA")
        b = d.evidence(source="https://example.org/b", payload=b"BBB")
        d.ask("compare", evidence=[a, b])

    envoye = vus[0]
    assert "--- evidence 1:" in envoye and "--- end of evidence 1 ---" in envoye
    assert "--- evidence 2:" in envoye and "--- end of evidence 2 ---" in envoye
    assert envoye.index("AAA") < envoye.index("BBB")


def test_des_octets_illisibles_ne_font_pas_tomber_la_decision(tmp_path):
    """Une preuve n'est pas forcément du texte. Planter ici perdrait
    l'enregistrement d'une décision à cause de son contenu."""
    rec, vus = enregistreur(tmp_path)
    with rec.decision("ask") as d:
        brut = d.evidence(source="https://example.org/bin", payload=b"\xff\xfe\x00binaire")
        d.ask("decris", evidence=[brut])

    assert "binaire" in vus[0]
    assert rec.verify() == []


def test_la_chaine_tient_avec_des_preuves_sur_les_questions(tmp_path):
    rec, _ = enregistreur(tmp_path)
    with rec.decision("ask") as d:
        page = d.evidence(source="https://example.org/p", payload=b"p")
        d.ask("question", evidence=[page])

    assert rec.verify() == []
