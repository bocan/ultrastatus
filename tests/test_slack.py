import copy
import io
import json
from datetime import timezone
from pathlib import Path

import pytest

from statusboard import db, http
from statusboard.cli import poll_providers
from statusboard.providers import PROVIDERS
from statusboard.providers.slack import FEED_URL, SlackProvider

from conftest import utc

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "slack_history.json").read_text())


@pytest.fixture
def feed(monkeypatch):
    state = {"payload": copy.deepcopy(FIXTURE), "requested": []}

    def fake_fetch(url, timeout=20.0):
        state["requested"].append(url)
        return json.dumps(state["payload"]).encode()

    monkeypatch.setattr(http, "fetch_bytes", fake_fetch)
    return state


def _by_id(incidents):
    return {i.external_id: i for i in incidents}


def test_fixture_parses_with_string_ids(feed):
    incidents = SlackProvider().fetch()
    assert len(incidents) == 3
    assert [i.external_id for i in incidents] == ["1576", "1575", "1574"]
    assert all(i.provider == "slack" and i.regions == [] for i in incidents)
    assert feed["requested"] == [FEED_URL]
    assert FEED_URL.endswith("/history")


def test_active_is_open_and_resolved_uses_date_updated_in_utc(feed):
    by_id = _by_id(SlackProvider().fetch())
    assert by_id["1576"].resolved_at is None
    resolved = by_id["1575"]
    assert resolved.resolved_at == resolved.updated_at
    # 2026-08-06T18:08:09-07:00 is 01:08:09 UTC the next day.
    assert resolved.resolved_at.astimezone(timezone.utc) == utc(2026, 8, 7, 1, 8, 9)
    assert by_id["1576"].started_at.astimezone(timezone.utc) == utc(2026, 8, 13, 21, 21, 41)


@pytest.mark.parametrize(
    "status,open_expected",
    [("active", True), ("scheduled", True), ("resolved", False), ("completed", False), ("cancelled", False)],
)
def test_status_decides_open_or_resolved(feed, status, open_expected):
    feed["payload"][0]["status"] = status
    inc = SlackProvider().fetch()[0]
    assert (inc.resolved_at is None) is open_expected


@pytest.mark.parametrize("kind,expected", [("outage", "critical"), ("incident", "major"), ("notice", "minor"), ("weird", "major")])
def test_type_mapping(feed, kind, expected):
    feed["payload"][0]["type"] = kind
    assert SlackProvider().fetch()[0].severity == expected


def test_newest_note_wins_regardless_of_order(feed):
    inc = SlackProvider().fetch()[0]
    assert "We're continuing to investigate" in inc.last_message
    feed["payload"][0]["notes"].reverse()
    assert "We're continuing to investigate" in SlackProvider().fetch()[0].last_message


def test_message_is_plain_text_with_services_prefix(feed):
    by_id = _by_id(SlackProvider().fetch())
    assert by_id["1576"].last_message.startswith("Services: Messaging, Workspace/Org Administration. We're continuing to investigate")
    assert "<p>" not in by_id["1576"].last_message
    assert "&nbsp;" not in by_id["1575"].last_message
    assert by_id["1575"].last_message.endswith("problematic change.")


def test_no_notes_gives_only_the_services_prefix_or_empty(feed):
    feed["payload"][0]["notes"] = []
    assert SlackProvider().fetch()[0].last_message == "Services: Messaging, Workspace/Org Administration."
    feed["payload"][0]["services"] = []
    assert SlackProvider().fetch()[0].last_message == ""


def test_url_and_title_pass_through(feed):
    inc = SlackProvider().fetch()[0]
    assert inc.url == "https://slack-status.com/2026-08/e07b9271f0346c3b"
    assert inc.title.startswith("Trouble Accessing Historical Messages")


def test_registered_with_label():
    assert isinstance(PROVIDERS["slack"], SlackProvider)
    assert PROVIDERS["slack"].label == "Slack"
    assert PROVIDERS["slack"].lists_resolved is True


def test_end_to_end_poll(feed, conn):
    out = io.StringIO()
    assert poll_providers(conn, {"slack": SlackProvider()}, out=out) == 0
    assert out.getvalue().strip() == "slack: 3 incidents, 0 newly resolved"
    assert [i.external_id for i in db.open_incidents(conn)] == ["1576"]
    assert len(db.recent_resolved(conn, utc(2000, 1, 1))) == 2
