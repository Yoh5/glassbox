"""Une réponse tronquée est rapportée comme telle, jamais comme une réponse.

Deux défauts, trouvés en sondant l'API réelle le 8 octobre 2026 — pas en
relisant le code, qui avait l'air juste.

**Le champ s'appelle `reasoning`.** Le repli lisait `reasoning_content`, une clé
que la réponse ne porte pas. Relevé de la sonde, sur la même requête tronquée :

    content            None
    reasoning          84 caracteres -> "Okay, so I need to figure out why 91..."
    reasoning_content  None

Le repli ne se déclenchait donc jamais : une réponse tronquée revenait sous
forme de chaîne vide, et rien ne disait pourquoi.

**Et le nom corrigé ne suffisait pas.** Substituer la réflexion à la réponse
était faux de toute façon : un raisonnement coupé en plein milieu n'est pas une
réponse, et l'enregistrer comme telle met une pensée à moitié formée dans le
registre sous la même forme qu'une vraie réponse — où le routeur la compare
ensuite pour juger de l'accord, et où le visualiseur l'affiche comme ce que le
modèle a dit.
"""

from __future__ import annotations

from glassbox.nebius import nebius_call


def reponse(message: dict, finish_reason: str = "length", jetons: int = 24) -> dict:
    return {
        "choices": [{"message": message, "finish_reason": finish_reason}],
        "usage": {"prompt_tokens": 40, "completion_tokens": jetons},
    }


def appeler_avec(corps: dict):
    """Un client qui rend `corps` sans toucher au réseau."""
    def poster(url, *, headers, json):  # noqa: A002, ARG001
        return corps
    return nebius_call(api_key="jamais-utilisee",
                       base_url="https://api.example/v1", post=poster)


def test_une_reponse_normale_passe_inchangee():
    appeler = appeler_avec(reponse({"content": "Paris", "reasoning": "pense..."}))
    texte, cout = appeler("nano", "capitale de la France ?")
    assert texte == "Paris"
    assert cout > 0


def test_une_troncature_ne_rend_pas_le_raisonnement():
    """Le cœur du test : la pensée coupée ne doit pas ressortir comme réponse."""
    pensee = "Okay, so I need to figure out why 91 isn't a prime number. Let me start"
    appeler = appeler_avec(reponse({"content": None, "reasoning": pensee}))
    texte, _ = appeler("nano", "pourquoi 91 n'est pas premier ?")

    assert pensee not in texte, "le raisonnement tronque est rendu comme une reponse"
    assert "no answer" in texte


def test_elle_dit_pourquoi_et_combien():
    """« Pas de réponse » sans raison envoie chercher au mauvais endroit.

    Même exigence que `verify`, qui nomme le premier enregistrement qui ne tient
    pas plutôt que d'annoncer qu'il y a un problème quelque part.
    """
    appeler = appeler_avec(reponse({"content": None, "reasoning": "x" * 84}))
    texte, _ = appeler("nano", "une question")

    assert "finish_reason=length" in texte
    assert "84 chars" in texte


def test_le_champ_lu_est_reasoning_et_pas_reasoning_content():
    """Épingle le nom. L'ancien code lisait une clé absente de la réponse.

    Avec `reasoning` renseigné et `reasoning_content` absent — ce que l'API rend
    réellement — le compte de caractères doit venir de `reasoning`.
    """
    appeler = appeler_avec(reponse({"content": None, "reasoning": "y" * 120}))
    texte, _ = appeler("nano", "une question")
    assert "120 chars" in texte


def test_reasoning_content_reste_un_repli_secondaire():
    """D'autres fournisseurs emploient ce nom ; le garder ne coûte rien."""
    appeler = appeler_avec(reponse({"content": None, "reasoning_content": "z" * 7}))
    texte, _ = appeler("nano", "une question")
    assert "7 chars" in texte


def test_sans_contenu_ni_raisonnement_elle_le_dit_quand_meme():
    """Le cas où les jetons facturés sont introuvables : zéro caractère, et la
    phrase le dit plutôt que de rendre une chaîne vide."""
    appeler = appeler_avec(reponse({"content": None}))
    texte, _ = appeler("nano", "une question")
    assert "0 chars" in texte
    assert texte != ""


def test_le_cout_est_compte_meme_quand_il_n_y_a_pas_de_reponse():
    """Les jetons sont facturés que la réponse arrive ou non. Les omettre
    ferait mentir le total du registre dans le sens flatteur."""
    appeler = appeler_avec(reponse({"content": None, "reasoning": "x" * 10}, jetons=24))
    _, cout = appeler("nano", "une question")
    assert cout > 0
