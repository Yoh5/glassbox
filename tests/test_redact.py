"""Redaction happens at the boundary, before anything is written or hashed.

A secret that reaches the ledger is there for good: the chain is append-only by
design, so "we will scrub it later" is not available. Runway learned this the
hard way — a hosted RPC provider embeds its key in the URL path, which survives
into a thrown error's message untouched.
"""

from glassbox.redact import Redactor


def test_replaces_a_known_secret_anywhere_in_the_text():
    redactor = Redactor(["sk-live-9f3a"])
    assert redactor("call failed for sk-live-9f3a at 09:31") == "call failed for [redacted] at 09:31"


def test_redacts_a_key_buried_in_a_url_path_which_is_how_providers_ship_them():
    redactor = Redactor(["sk-abc123"])
    text = "https://api.example.com/v2/sk-abc123/complete"
    assert "sk-abc123" not in redactor(text)


def test_leaves_text_alone_when_it_holds_no_secret():
    assert Redactor(["sk-abc123"])("nothing to see") == "nothing to see"


def test_ignores_empty_and_missing_secrets_rather_than_redacting_everything():
    # An unset environment variable reads as "", and replacing every empty
    # string would turn the whole ledger into [redacted].
    redactor = Redactor(["", None, "sk-abc123"])
    assert redactor("plain text") == "plain text"


def test_redacts_bytes_too_because_evidence_payloads_are_bytes():
    redactor = Redactor(["sk-abc123"])
    assert b"sk-abc123" not in redactor.bytes(b"header sk-abc123 body")


def test_reports_whether_it_changed_anything_so_a_record_can_say_so():
    redactor = Redactor(["sk-abc123"])
    assert redactor.applied("clean text") is False
    assert redactor.applied("holds sk-abc123") is True


def test_the_shortest_secret_still_wins_over_a_longer_overlapping_one():
    # Replacing the longer one first keeps the shorter from cutting it in half
    # and leaving a recognisable tail behind.
    redactor = Redactor(["abc", "abc123"])
    assert redactor("value abc123 here") == "value [redacted] here"
