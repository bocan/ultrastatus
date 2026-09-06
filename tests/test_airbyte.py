import io
from pathlib import Path

import pytest

from statusboard import db, http
from statusboard.cli import poll_providers
from statusboard.providers import PROVIDERS
from statusboard.providers.airbyte import FEED_URL, AirbyteProvider, parse_description

from conftest import utc

FIXTURE = (Path(__file__).parent / "fixtures" / "airbyte_history.xml").read_bytes()

ITEM = """<?xml version="1.0"?><rss version="2.0"><channel><item>
<title>{title}</title><description>{description}</description>
<pubDate>{pubdate}</pubDate><link>{link}</link><guid>{link}</guid>
</item></channel></rss>"""


@pytest.fixture
def feed(monkeypatch):
    state = {"body": FIXTURE, "requested": []}

    def fake_fetch(url, timeout=20.0):
        state["requested"].append(url)
        return state["body"]

    monkeypatch.setattr(http, "fetch_bytes", fake_fetch)
    return state


def _by_id(incidents):
    return {i.external_id: i for i in incidents}


def _item(description, title="T", pubdate="Tue, 1 Sep 2026 15:30:00 +0000", link="https://status.airbyte.com/incident/abc"):
    return ITEM.format(title=title, description=description, pubdate=pubdate, link=link).encode()


def test_fixture_parses_with_ids_from_the_guid_path(feed):
    incidents = AirbyteProvider().fetch()
    assert feed["requested"] == [FEED_URL]
    assert [i.external_id for i in incidents] == ["cmtiukc5l0m7k1ao1dcpz87yt", "cma1j631b003h13zj4jvzzpdk", "handedited000000000000001"]
    assert all(i.provider == "airbyte" and i.regions == [] for i in incidents)


def test_resolved_incident_uses_newest_timeline_entry(feed):
    inc = _by_id(AirbyteProvider().fetch())["cmtiukc5l0m7k1ao1dcpz87yt"]
    assert inc.started_at == utc(2026, 9, 1, 15, 30, 0)
    assert inc.updated_at == utc(2026, 9, 1, 16, 2, 31)
    assert inc.resolved_at == utc(2026, 9, 1, 16, 2, 31)
    assert inc.severity == "major"
    assert inc.last_message == "Components: Data Sync. This incident has been resolved."
    assert inc.url == "https://status.airbyte.com/incident/cmtiukc5l0m7k1ao1dcpz87yt"


def test_maintenance_with_completed_entry_listed_first_is_resolved(feed):
    inc = _by_id(AirbyteProvider().fetch())["cma1j631b003h13zj4jvzzpdk"]
    assert inc.severity == "minor"
    assert inc.started_at == utc(2025, 5, 1, 13, 0, 0)
    assert inc.resolved_at == utc(2025, 5, 1, 15, 0, 0)  # Completed is first in the text, newest by time
    assert inc.last_message.startswith("Components: WebApp, Connector Builder, Airbyte API, Data Sync. Maintenance has completed")


def test_open_incident_ends_in_monitoring(feed):
    inc = _by_id(AirbyteProvider().fetch())["handedited000000000000001"]
    assert inc.resolved_at is None
    assert inc.updated_at == utc(2026, 9, 5, 9, 20, 0)
    assert "&amp;" not in inc.last_message and "&" in inc.last_message


def test_year_rollover(feed):
    feed["body"] = _item(
        "Type: Incident\nAffected Components: Data Sync\nDec 31, 23:50:00 GMT+0 - Investigating - Looking. Jan 2, 01:00:00 GMT+0 - Resolved - Done.",
        pubdate="Thu, 31 Dec 2026 23:50:00 +0000",
    )
    inc = AirbyteProvider().fetch()[0]
    assert inc.started_at == utc(2026, 12, 31, 23, 50, 0)
    assert inc.resolved_at == utc(2027, 1, 2, 1, 0, 0)


@pytest.mark.parametrize("kind,expected", [("Incident", "major"), ("Maintenance", "minor"), ("Weird", "major"), (None, "major")])
def test_type_mapping(feed, kind, expected):
    header = f"Type: {kind}\n" if kind else ""
    feed["body"] = _item(header + "Sep 1, 15:30:00 GMT+0 - Resolved - Done.")
    assert AirbyteProvider().fetch()[0].severity == expected


def test_no_timeline_falls_back_to_pubdate(feed):
    feed["body"] = _item("Type: Incident\nAffected Components: WebApp")
    inc = AirbyteProvider().fetch()[0]
    assert inc.updated_at == inc.started_at
    assert inc.resolved_at is None
    assert inc.last_message == "Components: WebApp."
    feed["body"] = _item("Type: Incident")
    assert AirbyteProvider().fetch()[0].last_message == ""


def test_entry_minutes_before_pubdate_does_not_roll_into_next_year(feed):
    # Seen live: a maintenance item published 10:30 with an entry stamped 10:19.
    feed["body"] = _item(
        "Type: Maintenance\nJun 7, 12:31:58 GMT+0 - Completed - Done. Jun 7, 10:19:21 GMT+0 - Identified - In progress. Jun 7, 10:30:00 GMT+0 - Identified - Not yet.",
        pubdate="Tue, 7 Jun 2022 10:30:00 +0000",
    )
    inc = AirbyteProvider().fetch()[0]
    assert inc.resolved_at == utc(2022, 6, 7, 12, 31, 58)
    assert inc.updated_at.year == 2022


def test_equal_timestamps_let_the_terminal_entry_win(feed):
    # Seen live: three entries all stamped 10:00:00, Completed listed first.
    feed["body"] = _item(
        "Type: Maintenance\nDec 28, 10:00:00 GMT+0 - Completed - Done. Dec 28, 10:00:00 GMT+0 - Identified - Planned. Dec 28, 10:00:00 GMT+0 - Identified - In progress.",
        pubdate="Tue, 28 Dec 2021 10:00:00 +0000",
    )
    inc = AirbyteProvider().fetch()[0]
    assert inc.resolved_at == utc(2021, 12, 28, 10, 0, 0)
    assert inc.last_message.endswith("Done.")


def test_note_added_after_completion_keeps_the_item_resolved(feed):
    # Seen live: completed at 12:00, then an Identified note at 20:00.
    feed["body"] = _item(
        "Type: Maintenance\nAffected Components: WebApp\nJan 14, 11:00:01 GMT+0 - Identified - In progress Jan 14, 12:00:00 GMT+0 - Completed - Done Jan 14, 20:00:00 GMT+0 - Identified - Restarting databases.",
        pubdate="Tue, 14 Jan 2025 20:00:00 +0000",
    )
    inc = AirbyteProvider().fetch()[0]
    assert inc.resolved_at == utc(2025, 1, 14, 12, 0, 0)
    assert inc.updated_at == utc(2025, 1, 14, 20, 0, 0)
    assert inc.last_message == "Components: WebApp. Restarting databases."


def test_parse_description_sorts_entries_by_time():
    header, entries = parse_description(
        "Type: Maintenance\nMay 1, 15:00:00 GMT+0 - Completed - Done May 1, 13:00:00 GMT+0 - Identified - Planned",
        utc(2025, 5, 1, 13, 0),
    )
    assert header == {"Type": "Maintenance"}
    assert [e["state"] for e in entries] == ["identified", "completed"]
    assert entries[-1]["message"] == "Done"


def test_registered_with_label():
    assert isinstance(PROVIDERS["airbyte"], AirbyteProvider)
    assert PROVIDERS["airbyte"].label == "Airbyte"
    assert PROVIDERS["airbyte"].lists_resolved is True


def test_end_to_end_poll(feed, conn):
    out = io.StringIO()
    assert poll_providers(conn, {"airbyte": AirbyteProvider()}, out=out) == 0
    assert out.getvalue().strip() == "airbyte: 3 incidents, 0 newly resolved"
    assert [i.external_id for i in db.open_incidents(conn)] == ["handedited000000000000001"]
    assert len(db.recent_resolved(conn, utc(2000, 1, 1))) == 2
