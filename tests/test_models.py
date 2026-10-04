"""The question that comes before the others: are these tiers really there?

`list_models` existed and nothing called it -- not the package, not the CLI,
not an example, not a test. A helper nobody can run is a helper that does not
exist, and this one answers the first question anyone reproducing the
measurement has to ask.

It matters more here than most places. Model ids get renamed and withdrawn. If
one of the three tiers is gone, the router does not stop: it fails on that tier
and the escalation numbers quietly become a measurement of something else, with
the same title on the same page. A number that is wrong without saying so is
worse than a missing number, which is why this command exits non-zero.
"""

import glassbox.cli as cli
from glassbox.cli import main
from glassbox.nebius import TIERS


def _repond(monkeypatch, ids, *, cle="k"):
    monkeypatch.setenv("NEBIUS_API_KEY", cle)
    monkeypatch.setattr(cli, "list_models", lambda _key, _base: list(ids))


def test_every_tier_present_exits_zero(monkeypatch, capsys):
    _repond(monkeypatch, [t.model_id for t in TIERS.values()] + ["something/else"])

    assert main(["models"]) == 0
    dit = capsys.readouterr().out
    assert "MISSING" not in dit
    for name in TIERS:
        assert name in dit


def test_a_missing_tier_fails_and_is_named(monkeypatch, capsys):
    """Naming it is the point. A fallback nobody notices turns a measurement
    into a different measurement."""
    present = [t.model_id for name, t in TIERS.items() if name != "ultra"]
    _repond(monkeypatch, present)

    code = main(["models"])
    dit = capsys.readouterr().out

    assert code != 0
    assert "MISSING" in dit
    assert "ultra" in dit


def test_it_says_what_a_missing_tier_costs(monkeypatch, capsys):
    """Not just that it is absent: what happens to the numbers if you carry on
    anyway."""
    _repond(monkeypatch, [TIERS["nano"].model_id])

    main(["models"])

    assert "measuring something" in capsys.readouterr().out


def test_no_key_is_not_a_pass(monkeypatch, capsys):
    """Silence here would read as success, and the run would go ahead."""
    monkeypatch.delenv("NEBIUS_API_KEY", raising=False)

    code = main(["models"])

    assert code != 0
    assert "NEBIUS_API_KEY" in capsys.readouterr().out


def test_an_unreachable_endpoint_is_not_a_pass(monkeypatch, capsys):
    monkeypatch.setenv("NEBIUS_API_KEY", "k")
    def tombe(_key, _base):
        raise OSError("no route to host")
    monkeypatch.setattr(cli, "list_models", tombe)

    code = main(["models"])

    assert code != 0
    assert "no route to host" in capsys.readouterr().out


def test_the_key_can_be_read_from_another_variable(monkeypatch, capsys):
    """Nobody keeps every provider's key under the same name."""
    monkeypatch.delenv("NEBIUS_API_KEY", raising=False)
    monkeypatch.setenv("AUTRE_CLE", "k")
    monkeypatch.setattr(cli, "list_models", lambda _k, _b: [t.model_id for t in TIERS.values()])

    assert main(["models", "--api-key-env", "AUTRE_CLE"]) == 0
