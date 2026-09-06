from datetime import timedelta

from statusboard import db
from statusboard.model import Region

from conftest import make_incident, utc


def test_upsert_then_select_round_trips(conn):
    inc = make_incident(
        regions=[Region("aws", "us-east-1"), Region("gcp", "us-central1")]
    )
    db.upsert_incident(conn, inc)

    rows = db.open_incidents(conn)
    assert len(rows) == 1
    got = rows[0]
    assert got.provider == "fake"
    assert got.external_id == "a"
    assert got.title == "Something broke"
    assert got.severity == "major"
    assert got.started_at == inc.started_at
    assert got.updated_at == inc.updated_at
    assert got.resolved_at is None
    assert got.url == "https://example.test/a"
    assert got.last_message == "Investigating."
    assert got.regions == [Region("aws", "us-east-1"), Region("gcp", "us-central1")]


def test_upsert_twice_updates_in_place(conn):
    db.upsert_incident(conn, make_incident(title="first"))
    db.upsert_incident(conn, make_incident(title="second"))

    count = conn.execute("SELECT count(*) FROM incident").fetchone()[0]
    assert count == 1
    assert db.open_incidents(conn)[0].title == "second"


def test_upsert_replaces_regions(conn):
    db.upsert_incident(
        conn,
        make_incident(regions=[Region("aws", "us-east-1"), Region("aws", "eu-west-1")]),
    )
    db.upsert_incident(conn, make_incident(regions=[Region("azure", "eastus")]))

    assert db.open_incidents(conn)[0].regions == [Region("azure", "eastus")]
    count = conn.execute("SELECT count(*) FROM incident_region").fetchone()[0]
    assert count == 1


def test_timestamps_truncate_to_seconds(conn):
    started = utc(2026, 9, 5, 10, 0, 0).replace(microsecond=999999)
    db.upsert_incident(conn, make_incident(started_at=started))
    raw = conn.execute("SELECT started_at FROM incident").fetchone()[0]
    assert raw == "2026-09-05T10:00:00Z"


def test_mark_missing_resolved_only_touches_unseen_open_rows(conn):
    now = utc(2026, 9, 5, 12, 0, 0)
    db.upsert_incident(conn, make_incident(external_id="a"))
    db.upsert_incident(conn, make_incident(external_id="b"))
    db.upsert_incident(
        conn, make_incident(external_id="c", resolved_at=utc(2026, 9, 1))
    )
    db.upsert_incident(conn, make_incident(provider="other", external_id="d"))

    count = db.mark_missing_resolved(conn, "fake", {"a"}, now)

    assert count == 1
    by_id = {i.external_id: i for i in db.recent_resolved(conn, utc(2000, 1, 1))}
    assert by_id["b"].resolved_at == now
    assert by_id["c"].resolved_at == utc(2026, 9, 1)
    open_ids = {i.external_id for i in db.open_incidents(conn)}
    assert open_ids == {"a", "d"}


def test_mark_missing_resolved_with_empty_seen_set(conn):
    now = utc(2026, 9, 5, 12, 0, 0)
    db.upsert_incident(conn, make_incident(external_id="a"))
    db.upsert_incident(conn, make_incident(external_id="b"))

    assert db.mark_missing_resolved(conn, "fake", set(), now) == 2
    assert db.open_incidents(conn) == []


def test_recent_resolved_respects_since(conn):
    db.upsert_incident(
        conn, make_incident(external_id="old", resolved_at=utc(2026, 8, 1))
    )
    db.upsert_incident(
        conn, make_incident(external_id="new", resolved_at=utc(2026, 9, 4))
    )

    since = utc(2026, 9, 5) - timedelta(days=7)
    ids = [i.external_id for i in db.recent_resolved(conn, since)]
    assert ids == ["new"]


def test_last_polls_returns_newest_per_provider(conn):
    db.record_poll(conn, "fake", utc(2026, 9, 5, 10, 0, 0), "boom")
    db.record_poll(conn, "fake", utc(2026, 9, 5, 10, 2, 0), None)
    db.record_poll(conn, "other", utc(2026, 9, 5, 9, 0, 0), "down")

    polls = db.last_polls(conn)
    assert polls["fake"] == (utc(2026, 9, 5, 10, 2, 0), None)
    assert polls["other"] == (utc(2026, 9, 5, 9, 0, 0), "down")


def test_schema_has_exactly_three_tables(conn):
    names = {
        r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert names == {"incident", "incident_region", "poll_run"}
