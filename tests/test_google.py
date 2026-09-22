import io
import json
from pathlib import Path
from typing import Any

import pytest

from statusboard import db, http
from statusboard.cli import poll_providers
from statusboard.model import Region
from statusboard.providers import PROVIDERS
from statusboard.providers.google import GoogleStatusProvider, _title

from conftest import utc

FIXTURES = Path(__file__).parent / "fixtures"
GCP_URL = "https://status.cloud.google.com/incidents.json"
WORKSPACE_URL = "https://www.google.com/appsstatus/dashboard/incidents.json"

GCP = GoogleStatusProvider("gcp", GCP_URL, "https://status.cloud.google.com/", "GCP")
WORKSPACE = GoogleStatusProvider(
    "google-workspace",
    WORKSPACE_URL,
    "https://www.google.com/appsstatus/dashboard/",
    "Google Workspace",
)


@pytest.fixture
def feeds(monkeypatch):
    state: dict[str, Any] = {
        "payloads": {
            GCP_URL: json.loads((FIXTURES / "gcp_incidents.json").read_text()),
            WORKSPACE_URL: json.loads(
                (FIXTURES / "workspace_incidents.json").read_text()
            ),
        },
        "requested": [],
    }

    def fake_fetch(url, timeout=20.0):
        state["requested"].append(url)
        return json.dumps(state["payloads"][url]).encode()

    monkeypatch.setattr(http, "fetch_bytes", fake_fetch)
    return state


def _by_id(incidents):
    return {i.external_id: i for i in incidents}


# GCP: the ADR-0003 tests, unchanged in intent.


def test_gcp_fixture_parses_to_one_incident_per_item(feeds):
    incidents = GCP.fetch()
    assert len(incidents) == 6
    assert all(i.provider == "gcp" for i in incidents)


def test_status_impact_mapping(feeds):
    by_id = _by_id(GCP.fetch())
    assert by_id["41E5S3mkTGDfkZuJZH5k"].severity == "minor"
    assert by_id["J5ia5t9p3g9Q5Wi7r8Ev"].severity == "major"
    assert by_id["utF3FMFdQfwBzJcGG6vf"].severity == "critical"


def test_unknown_status_impact_maps_to_major(feeds):
    feeds["payloads"][GCP_URL][1]["status_impact"] = "SOMETHING_NEW"
    assert _by_id(GCP.fetch())["utF3FMFdQfwBzJcGG6vf"].severity == "major"


def test_region_union_keeps_order_and_dedupes(feeds):
    inc = _by_id(GCP.fetch())["J5ia5t9p3g9Q5Wi7r8Ev"]
    assert inc.regions == [Region("gcp", "us-east1"), Region("gcp", "us-central1")]
    feeds["payloads"][GCP_URL][0]["previously_affected_locations"].append(
        {"title": "dup", "id": "us-east1"}
    )
    assert _by_id(GCP.fetch())["J5ia5t9p3g9Q5Wi7r8Ev"].regions == [
        Region("gcp", "us-east1"),
        Region("gcp", "us-central1"),
    ]


def test_global_location_passes_through(feeds):
    assert _by_id(GCP.fetch())["utF3FMFdQfwBzJcGG6vf"].regions == [
        Region("gcp", "global"),
        Region("gcp", "us-west1"),
    ]


def test_gcp_open_and_resolved(feeds):
    by_id = _by_id(GCP.fetch())
    assert by_id["J5ia5t9p3g9Q5Wi7r8Ev"].resolved_at is None
    assert by_id["utF3FMFdQfwBzJcGG6vf"].resolved_at == utc(2026, 8, 20, 19, 20, 0)


def test_gcp_field_mapping(feeds):
    inc = _by_id(GCP.fetch())["utF3FMFdQfwBzJcGG6vf"]
    assert inc.title.startswith("We are investigating an issue")
    assert inc.url == "https://status.cloud.google.com/incidents/utF3FMFdQfwBzJcGG6vf"
    assert inc.started_at == utc(2026, 8, 20, 15, 40, 0)
    assert inc.updated_at == utc(2026, 8, 27, 21, 45, 2)
    assert inc.last_message.startswith("# Incident Report")


def test_last_message_is_truncated(feeds):
    feeds["payloads"][GCP_URL][0]["most_recent_update"]["text"] = "x" * 5000
    assert len(GCP.fetch()[0].last_message) == 2000


# Workspace: same shape, no locations, markdown titles.


def test_workspace_fixture_parses_with_no_regions(feeds):
    incidents = WORKSPACE.fetch()
    assert len(incidents) == 6
    assert all(i.provider == "google-workspace" for i in incidents)
    assert all(i.regions == [] for i in incidents)
    assert all(
        (i.url or "").startswith(
            "https://www.google.com/appsstatus/dashboard/incidents/"
        )
        for i in incidents
    )
    by_id = _by_id(incidents)
    assert by_id["B5V4MfnVp97nxoTYbxdX"].resolved_at is None
    assert all(
        i.resolved_at is not None
        for i in incidents
        if i.external_id != "B5V4MfnVp97nxoTYbxdX"
    )


def test_workspace_title_is_first_line_without_summary_prefix(feeds):
    by_id = _by_id(WORKSPACE.fetch())
    assert by_id["y2ufhCB886p7rveYNnko"].title.startswith(
        "Google Chat users are experiencing an issue"
    )
    assert "**" not in by_id["y2ufhCB886p7rveYNnko"].title
    assert "\n" not in by_id["y2ufhCB886p7rveYNnko"].title
    assert (
        by_id["sjDiph2NXGAfkYYLfK7T"].title
        == "Some customers may experience slowness while using Google Drive."
    )


def test_workspace_title_heading_on_its_own_line(feeds):
    # The live feed sometimes writes "**Title:**" instead of "**Summary:**".
    by_id = _by_id(WORKSPACE.fetch())
    assert by_id["B5V4MfnVp97nxoTYbxdX"].title == (
        "Gmail Android App users on the latest Gmail Android release "
        "may experience issues accessing their inbox."
    )


def test_workspace_title_heading_with_text_on_the_same_line(feeds):
    # "**Title** : text" puts the colon outside the bold and the text inline.
    by_id = _by_id(WORKSPACE.fetch())
    assert by_id["nK23ZsSxV33wfkqXVeh3"].title == (
        "Some customers may have experienced an issue with Gemini "
        "where conversation history may not have been visible."
    )


@pytest.mark.parametrize(
    "desc",
    [
        "**Summary**\nFirst line\nSecond",
        "**Summary:**\nFirst line\nSecond",
        "**Title**\nFirst line\nSecond",
        "**Title:**\nFirst line\nSecond",
        "**Title :**\nFirst line\nSecond",
        "**Description**\nFirst line\nSecond",
        "**Title** : First line\nSecond",
        "**Title:** First line\nSecond",
        "**Title :** First line\nSecond",
        "**title**:First line\nSecond",
        "**Title**\n**Description**\nFirst line\nSecond",
    ],
)
def test_title_strips_every_bold_heading_variant(desc):
    assert _title(desc) == "First line"


def test_title_keeps_bold_emphasis_inside_a_sentence():
    assert (
        _title("**Gmail** is down for some users") == "**Gmail** is down for some users"
    )


def test_title_helper_edge_cases():
    assert _title("**Summary:**\nFirst line\nSecond") == "First line"
    assert _title("**summary**\n\n  Padded line  ") == "Padded line"
    assert _title("Plain single line") == "Plain single line"
    assert _title("") == ""
    assert _title("**Title:**") == ""
    assert len(_title("**Summary**\n" + "x" * 500)) == 200


def test_both_instances_are_registered_and_request_their_own_url(feeds):
    gcp, workspace = PROVIDERS["gcp"], PROVIDERS["google-workspace"]
    assert isinstance(gcp, GoogleStatusProvider)
    assert isinstance(workspace, GoogleStatusProvider)
    assert gcp.feed_url == GCP_URL
    assert workspace.feed_url == WORKSPACE_URL
    assert workspace.label == "Google Workspace"
    PROVIDERS["gcp"].fetch()
    PROVIDERS["google-workspace"].fetch()
    assert feeds["requested"] == [GCP_URL, WORKSPACE_URL]


def test_end_to_end_poll_writes_gcp_regions_and_workspace_rows(feeds, conn):
    out = io.StringIO()
    assert (
        poll_providers(conn, {"gcp": GCP, "google-workspace": WORKSPACE}, out=out) == 0
    )
    assert out.getvalue().splitlines() == [
        "gcp: 6 incidents, 0 newly resolved",
        "google-workspace: 6 incidents, 0 newly resolved",
    ]
    assert sorted(i.external_id for i in db.open_incidents(conn)) == [
        "B5V4MfnVp97nxoTYbxdX",
        "J5ia5t9p3g9Q5Wi7r8Ev",
    ]
    rows = conn.execute(
        "SELECT count(*) FROM incident_region WHERE provider='gcp'"
    ).fetchone()[0]
    assert rows > 0
    ws_rows = conn.execute(
        "SELECT count(*) FROM incident WHERE provider='google-workspace'"
    ).fetchone()[0]
    assert ws_rows == 6
