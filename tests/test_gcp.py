import io
import json
from pathlib import Path

import pytest

from statusboard import db, http
from statusboard.cli import poll_providers
from statusboard.model import Region
from statusboard.providers.gcp import GcpProvider

from conftest import utc

FIXTURE = Path(__file__).parent / "fixtures" / "gcp_incidents.json"


@pytest.fixture
def feed(monkeypatch):
    state = {"payload": json.loads(FIXTURE.read_text())}

    def fake_fetch(url, timeout=20.0):
        assert url == "https://status.cloud.google.com/incidents.json"
        return json.dumps(state["payload"]).encode()

    monkeypatch.setattr(http, "fetch_bytes", fake_fetch)
    return state


def _by_id(incidents):
    return {i.external_id: i for i in incidents}


def test_fixture_parses_to_one_incident_per_item(feed):
    incidents = GcpProvider().fetch()
    assert len(incidents) == 6
    assert all(i.provider == "gcp" for i in incidents)


def test_status_impact_mapping(feed):
    by_id = _by_id(GcpProvider().fetch())
    assert by_id["41E5S3mkTGDfkZuJZH5k"].severity == "minor"     # SERVICE_INFORMATION
    assert by_id["J5ia5t9p3g9Q5Wi7r8Ev"].severity == "major"     # SERVICE_DISRUPTION
    assert by_id["utF3FMFdQfwBzJcGG6vf"].severity == "critical"  # SERVICE_OUTAGE


def test_unknown_status_impact_maps_to_major(feed):
    feed["payload"][1]["status_impact"] = "SOMETHING_NEW"
    assert _by_id(GcpProvider().fetch())["utF3FMFdQfwBzJcGG6vf"].severity == "major"


def test_region_union_keeps_order_and_dedupes(feed):
    inc = _by_id(GcpProvider().fetch())["J5ia5t9p3g9Q5Wi7r8Ev"]
    assert inc.regions == [Region("gcp", "us-east1"), Region("gcp", "us-central1")]

    feed["payload"][0]["previously_affected_locations"].append({"title": "dup", "id": "us-east1"})
    inc = _by_id(GcpProvider().fetch())["J5ia5t9p3g9Q5Wi7r8Ev"]
    assert inc.regions == [Region("gcp", "us-east1"), Region("gcp", "us-central1")]


def test_global_location_passes_through(feed):
    inc = _by_id(GcpProvider().fetch())["utF3FMFdQfwBzJcGG6vf"]
    assert inc.regions == [Region("gcp", "global"), Region("gcp", "us-west1")]


def test_open_and_resolved(feed):
    by_id = _by_id(GcpProvider().fetch())
    assert by_id["J5ia5t9p3g9Q5Wi7r8Ev"].resolved_at is None
    assert by_id["utF3FMFdQfwBzJcGG6vf"].resolved_at == utc(2026, 8, 20, 19, 20, 0)


def test_field_mapping(feed):
    inc = _by_id(GcpProvider().fetch())["utF3FMFdQfwBzJcGG6vf"]
    assert inc.title.startswith("We are investigating an issue")
    assert inc.url == "https://status.cloud.google.com/incidents/utF3FMFdQfwBzJcGG6vf"
    assert inc.started_at == utc(2026, 8, 20, 15, 40, 0)
    assert inc.updated_at == utc(2026, 8, 27, 21, 45, 2)
    assert inc.last_message.startswith("# Incident Report")


def test_last_message_is_truncated(feed):
    feed["payload"][0]["most_recent_update"]["text"] = "x" * 5000
    assert len(GcpProvider().fetch()[0].last_message) == 2000


def test_end_to_end_poll_writes_regions(feed, conn):
    out = io.StringIO()
    assert poll_providers(conn, {"gcp": GcpProvider()}, out=out) == 0
    assert out.getvalue().strip() == "gcp: 6 incidents, 0 newly resolved"

    open_ids = [i.external_id for i in db.open_incidents(conn)]
    assert open_ids == ["J5ia5t9p3g9Q5Wi7r8Ev"]
    rows = conn.execute(
        "SELECT cloud, region_code FROM incident_region WHERE provider='gcp' ORDER BY region_code"
    ).fetchall()
    assert len(rows) > 0
    assert all(r["cloud"] == "gcp" for r in rows)
