import io
import json
from pathlib import Path

import pytest

from statusboard import db, http
from statusboard.cli import poll_providers
from statusboard.providers.github import GitHubProvider

from conftest import utc

FIXTURE = Path(__file__).parent / "fixtures" / "github_incidents.json"


@pytest.fixture
def feed(monkeypatch):
    """Serve the fixture, or a modified copy, in place of the network."""
    state = {"payload": json.loads(FIXTURE.read_text())}

    def fake_fetch(url, timeout=20.0):
        assert url == "https://www.githubstatus.com/api/v2/incidents.json"
        return json.dumps(state["payload"]).encode()

    monkeypatch.setattr(http, "fetch_bytes", fake_fetch)
    return state


def test_fetch_returns_one_incident_per_item(feed):
    incidents = GitHubProvider().fetch()
    assert len(incidents) == len(feed["payload"]["incidents"])
    assert all(i.provider == "github" for i in incidents)


def test_severity_mapping_covers_all_impacts(feed):
    by_id = {i.external_id: i for i in GitHubProvider().fetch()}
    assert by_id["tx9qn4khd664"].severity == "critical"
    assert by_id["zw1hbx2yyhvr"].severity == "major"
    assert by_id["r05vk75c594j"].severity == "minor"
    assert by_id["wms44hv62t3p"].severity == "minor"  # impact "none"


def test_field_mapping(feed):
    inc = {i.external_id: i for i in GitHubProvider().fetch()}["zw1hbx2yyhvr"]
    assert inc.title == "Disruption with Copilot Code Review"
    assert inc.url == "https://stspg.io/dddfhld6fj0z"
    assert inc.started_at == utc(2026, 9, 4, 20, 39, 3).replace(microsecond=195000)
    assert inc.updated_at.isoformat().startswith("2026-09-04T22:26:46")
    assert inc.resolved_at.isoformat().startswith("2026-09-04T22:26:46")
    assert inc.last_message.startswith("This incident has been resolved.")
    assert inc.regions == []


def test_open_incident_has_no_resolved_at(feed):
    feed["payload"]["incidents"][0]["resolved_at"] = None
    feed["payload"]["incidents"][0]["status"] = "monitoring"
    inc = GitHubProvider().fetch()[0]
    assert inc.resolved_at is None


def test_empty_updates_gives_empty_message(feed):
    feed["payload"]["incidents"][0]["incident_updates"] = []
    assert GitHubProvider().fetch()[0].last_message == ""


def test_end_to_end_poll(feed, conn):
    out = io.StringIO()
    code = poll_providers(conn, {"github": GitHubProvider()}, out=out)
    assert code == 0
    stored = db.open_incidents(conn) + db.recent_resolved(conn, utc(2000, 1, 1))
    assert len(stored) == len(feed["payload"]["incidents"])
    assert out.getvalue().strip() == "github: 5 incidents, 0 newly resolved"
