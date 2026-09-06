import io

from statusboard import db
from statusboard.cli import poll_providers
from statusboard.providers.fake import FakeProvider, RaisingProvider

from conftest import make_incident, utc


def test_open_only_feed_resolves_vanished_incidents(conn):
    a = make_incident(external_id="a")
    b = make_incident(external_id="b")
    provider = FakeProvider("fake", lists_resolved=False, batches=[[a, b], [a]])
    out = io.StringIO()

    assert (
        poll_providers(conn, {"fake": provider}, out=out, now=utc(2026, 9, 5, 10, 0))
        == 0
    )
    assert {i.external_id for i in db.open_incidents(conn)} == {"a", "b"}

    assert (
        poll_providers(conn, {"fake": provider}, out=out, now=utc(2026, 9, 5, 10, 2))
        == 0
    )
    assert {i.external_id for i in db.open_incidents(conn)} == {"a"}
    resolved = db.recent_resolved(conn, utc(2000, 1, 1))
    assert [i.external_id for i in resolved] == ["b"]
    assert resolved[0].resolved_at == utc(2026, 9, 5, 10, 2)

    lines = out.getvalue().splitlines()
    assert lines == [
        "fake: 2 incidents, 0 newly resolved",
        "fake: 1 incidents, 1 newly resolved",
    ]


def test_feed_that_lists_resolved_is_not_auto_resolved(conn):
    a = make_incident(external_id="a")
    provider = FakeProvider("fake", lists_resolved=True, batches=[[a], []])

    poll_providers(conn, {"fake": provider}, out=io.StringIO())
    poll_providers(conn, {"fake": provider}, out=io.StringIO())

    assert [i.external_id for i in db.open_incidents(conn)] == ["a"]


def test_raising_provider_is_recorded_and_others_still_run(conn):
    bad = RaisingProvider("bad", "feed exploded")
    good = FakeProvider(
        "good",
        lists_resolved=False,
        batches=[[make_incident(provider="good", external_id="g")]],
    )
    out = io.StringIO()
    now = utc(2026, 9, 5, 10, 0)

    code = poll_providers(conn, {"bad": bad, "good": good}, out=out, now=now)

    assert code == 1
    polls = db.last_polls(conn)
    assert polls["bad"] == (now, "RuntimeError: feed exploded")
    assert polls["good"] == (now, None)
    assert [i.external_id for i in db.open_incidents(conn)] == ["g"]
    assert out.getvalue().splitlines() == [
        "bad: ERROR feed exploded",
        "good: 1 incidents, 0 newly resolved",
    ]


def test_failed_fetch_does_not_resolve_existing_incidents(conn):
    db.upsert_incident(conn, make_incident(provider="bad", external_id="x"))
    bad = RaisingProvider("bad")

    poll_providers(conn, {"bad": bad}, out=io.StringIO())

    assert [i.external_id for i in db.open_incidents(conn)] == ["x"]
