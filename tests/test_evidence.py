"""The evidence store: what the agent saw, when it saw it, and where it came from.

Addressing an *observation* rather than a payload is deliberate. The same bytes
fetched from two places, or from one place at two times, are two different
facts about the world, and a decision that cites one is not citing the other.
"""

import pytest

from glassbox.evidence import EvidenceStore, UnknownEvidence
from glassbox.redact import Redactor

PAGE = b"<html>quarterly results are up</html>"


def store(tmp_path, secrets=()):
    return EvidenceStore(tmp_path, redactor=Redactor(secrets))


def test_stores_and_returns_the_payload_untouched(tmp_path):
    s = store(tmp_path)
    item = s.put(source="https://example.org/q3", payload=PAGE, fetched_at="2026-10-14T09:31:00Z")

    assert s.get(item.id).payload == PAGE


def test_keeps_the_provenance_a_decision_will_cite(tmp_path):
    s = store(tmp_path)
    item = s.put(source="https://example.org/q3", payload=PAGE, fetched_at="2026-10-14T09:31:00Z")

    back = s.get(item.id)
    assert back.source == "https://example.org/q3"
    assert back.fetched_at == "2026-10-14T09:31:00Z"


def test_the_same_observation_always_gets_the_same_id(tmp_path):
    a = store(tmp_path / "a")
    b = store(tmp_path / "b")
    args = dict(source="https://example.org/q3", payload=PAGE, fetched_at="2026-10-14T09:31:00Z")

    assert a.put(**args).id == b.put(**args).id


def test_the_same_bytes_fetched_twice_are_two_observations(tmp_path):
    s = store(tmp_path)
    first = s.put(source="https://example.org/q3", payload=PAGE, fetched_at="2026-10-14T09:31:00Z")
    later = s.put(source="https://example.org/q3", payload=PAGE, fetched_at="2026-10-14T11:02:00Z")

    assert first.id != later.id
    # ...but the bytes are stored once, and that is visible.
    assert first.payload_sha256 == later.payload_sha256


def test_an_unknown_id_raises_rather_than_returning_nothing(tmp_path):
    with pytest.raises(UnknownEvidence):
        store(tmp_path).get("sha256:" + "0" * 64)


def test_a_secret_in_the_payload_is_redacted_before_it_is_stored(tmp_path):
    s = store(tmp_path, secrets=["sk-live-9f3a"])
    item = s.put(
        source="https://example.org/q3",
        payload=b"Authorization: Bearer sk-live-9f3a",
        fetched_at="2026-10-14T09:31:00Z",
    )

    assert b"sk-live-9f3a" not in s.get(item.id).payload
    assert item.redacted is True


def test_a_secret_in_the_source_url_is_redacted_too(tmp_path):
    s = store(tmp_path, secrets=["sk-live-9f3a"])
    item = s.put(
        source="https://api.example.org/v2/sk-live-9f3a/page",
        payload=PAGE,
        fetched_at="2026-10-14T09:31:00Z",
    )

    assert "sk-live-9f3a" not in item.source
    assert item.redacted is True


def test_an_ordinary_item_is_not_marked_redacted(tmp_path):
    s = store(tmp_path, secrets=["sk-live-9f3a"])
    item = s.put(source="https://example.org/q3", payload=PAGE, fetched_at="2026-10-14T09:31:00Z")

    assert item.redacted is False


def test_a_payload_edited_on_disk_is_caught(tmp_path):
    s = store(tmp_path)
    item = s.put(source="https://example.org/q3", payload=PAGE, fetched_at="2026-10-14T09:31:00Z")

    (tmp_path / "objects" / item.payload_sha256).write_bytes(b"<html>results are down</html>")

    problems = s.verify()
    assert len(problems) == 1
    assert item.payload_sha256[:12] in problems[0]


def test_an_untouched_store_verifies_clean(tmp_path):
    s = store(tmp_path)
    s.put(source="https://example.org/q3", payload=PAGE, fetched_at="2026-10-14T09:31:00Z")
    s.put(source="https://example.org/q4", payload=b"other", fetched_at="2026-10-14T09:32:00Z")

    assert s.verify() == []
