"""Le routeur refuse plutôt que de dépenser sans fin.

Un appel isolé était déjà borné — `max_tokens`, deux délais d'attente — mais une
série ne l'était pas : le routeur parcourt les paliers, échantillonne chacun, et
rien ne comptait le total. L'OWASP Top 10 for LLM Applications 2026 classe la
consommation non bornée au sixième rang des risques mesurés contre des incidents
réels, et la part gênante est que ce projet **mesure** le coût à chaque appel.
Il avait le chiffre et ne s'en servait pas.

Trouvé en passant le classement 2026 sur ce dépôt, le 8 octobre 2026 — pas en
marchant le produit. Les deux méthodes trouvent des choses différentes.
"""

from __future__ import annotations

import pytest

from glassbox.router import BudgetExhausted, Router


def compteur(cout: float = 0.01):
    """Un modèle factice qui facture `cout` et compte ses appels."""
    etat = {"appels": 0}

    def appeler(tier: str, prompt: str) -> tuple[str, float]:
        etat["appels"] += 1
        return f"reponse-{etat['appels']}", cout

    return appeler, etat


def test_sans_plafond_rien_ne_change(tmp_path):
    """Le défaut reste l'absence de plafond : un garde qu'on ne demande pas ne
    doit pas s'activer tout seul et casser les appelants existants."""
    appeler, etat = compteur()
    r = Router(appeler, tiers=("nano",), samples=2)
    for _ in range(10):
        r.ask("question")
    assert etat["appels"] == 20


def test_le_plafond_finit_par_refuser():
    appeler, etat = compteur()
    r = Router(appeler, tiers=("nano",), samples=2, max_cost_usd=0.05)

    with pytest.raises(BudgetExhausted):
        for _ in range(10):
            r.ask("question")

    assert etat["appels"] < 20, "le plafond n'a rien arrêté"


def test_il_s_arrete_une_fois_franchi_et_ne_promet_pas_de_ne_pas_franchir():
    """La propriété exacte, épinglée pour qu'on ne la surpromette pas ailleurs.

    Le coût d'un appel n'est connu qu'au retour. Le contrôle demande « ai-je
    déjà dépensé le plafond ? » avant chaque appel, donc l'appel qui le franchit
    est payé. Un plafond de 0,05 $ s'arrête à 0,06 $, pas à 0,05 $.
    """
    appeler, _ = compteur(cout=0.01)
    r = Router(appeler, tiers=("nano",), samples=2, max_cost_usd=0.05)

    with pytest.raises(BudgetExhausted):
        for _ in range(10):
            r.ask("question")

    assert r.spent_usd > 0.05, "le dépassement décrit dans la docstring n'a pas lieu"
    assert r.spent_usd < 0.05 + 0.03, "le dépassement doit rester d'un appel, pas d'une série"


def test_le_message_dit_combien_et_quel_appel_n_a_pas_eu_lieu():
    """« Budget dépassé » n'est pas un constat : il faut le montant et la cible.

    Même exigence que `verify`, qui nomme le premier enregistrement qui ne tient
    pas plutôt que de dire que quelque chose ne va pas quelque part.
    """
    appeler, _ = compteur()
    r = Router(appeler, tiers=("nano",), samples=2, max_cost_usd=0.02)

    with pytest.raises(BudgetExhausted) as leve:
        for _ in range(10):
            r.ask("question")

    message = str(leve.value)
    assert "0.02" in message, "le plafond n'est pas dit"
    assert "nano" in message, "l'appel refusé n'est pas nommé"
    assert "was not made" in message


def test_un_plafond_nul_ou_negatif_est_refuse_a_la_construction():
    """Un plafond de zéro interdit le premier appel : c'est une erreur de
    configuration, pas une politique. La dire tôt vaut mieux qu'une série
    d'exceptions au premier `ask`."""
    appeler, _ = compteur()
    for mauvais in (0, -1.0):
        with pytest.raises(ValueError, match="must be positive"):
            Router(appeler, max_cost_usd=mauvais)


def test_la_depense_est_lisible_sans_attendre_le_refus():
    """Un plafond qu'on ne peut pas voir approcher force à attendre l'accident."""
    appeler, _ = compteur(cout=0.01)
    r = Router(appeler, tiers=("nano",), samples=2, max_cost_usd=1.0)

    assert r.spent_usd == 0.0
    r.ask("question")
    assert r.spent_usd == pytest.approx(0.02)
