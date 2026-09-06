import copy
import io
import json
from pathlib import Path
from typing import Any

import pytest

from statusboard import db, http
from statusboard.cli import poll_providers
from statusboard.model import Region
from statusboard.providers.databricks import PAGES, DatabricksProvider, api_url

from conftest import utc

FIXTURES = Path(__file__).parent / "fixtures"
QUIET = json.loads((FIXTURES / "databricks_aws_quiet.json").read_text())
INCIDENT = json.loads((FIXTURES / "databricks_aws_incident.json").read_text())

AWS_ID, AZURE_ID, GCP_ID = (page_id for _, page_id, _ in PAGES)


@pytest.fixture
def feeds(monkeypatch):
    """One payload per page id. Tests swap payloads in, or set one to raise."""
    state: dict[str, Any] = {
        "payloads": {
            AWS_ID: copy.deepcopy(QUIET),
            AZURE_ID: copy.deepcopy(QUIET),
            GCP_ID: copy.deepcopy(QUIET),
        },
        "raise_for": set(),
        "requested": [],
    }

    def fake_fetch(url, timeout=20.0):
        state["requested"].append(url)
        page_id = url.rsplit("/", 1)[1]
        if page_id in state["raise_for"]:
            raise RuntimeError(f"simulated failure for {page_id}")
        return json.dumps(state["payloads"][page_id]).encode()

    monkeypatch.setattr(http, "fetch_bytes", fake_fetch)
    return state


def _with_container_names(names):
    payload = copy.deepcopy(INCIDENT)
    payload["result"]["incidents"][0]["containers_affected"] = [
        {"_id": f"id{i}", "name": n} for i, n in enumerate(names)
    ]
    return payload


def test_quiet_pages_yield_no_incidents(feeds):
    assert DatabricksProvider().fetch() == []
    assert feeds["requested"] == [api_url(AWS_ID), api_url(AZURE_ID), api_url(GCP_ID)]


def test_aws_page_incident_maps_fields_and_regions(feeds):
    feeds["payloads"][AWS_ID] = copy.deepcopy(INCIDENT)
    incidents = DatabricksProvider().fetch()
    assert len(incidents) == 1
    inc = incidents[0]
    assert inc.provider == "databricks"
    assert inc.external_id == "aws:6afd0c1e2b3c4d5e6f708192"
    assert inc.title == "Elevated error rates on job launches"
    assert inc.severity == "critical"
    assert inc.started_at == utc(2026, 9, 5, 10, 0, 0)
    assert inc.updated_at == utc(2026, 9, 5, 10, 5, 0)
    assert inc.resolved_at is None
    assert (
        inc.url
        == f"https://status.databricks.com/pages/incident/{AWS_ID}/6afd0c1e2b3c4d5e6f708192"
    )
    assert inc.last_message.startswith("Starting at 09:52 UTC")
    assert inc.regions == [Region("aws", "us-east-1"), Region("aws", "eu-west-1")]


def test_newest_message_wins_regardless_of_array_order(feeds):
    payload = copy.deepcopy(INCIDENT)
    payload["result"]["incidents"][0]["messages"].reverse()
    feeds["payloads"][AWS_ID] = payload
    inc = DatabricksProvider().fetch()[0]
    assert inc.last_message.startswith("Starting at 09:52 UTC")
    assert inc.updated_at == utc(2026, 9, 5, 10, 5, 0)


def test_azure_page_normalises_display_names(feeds):
    feeds["payloads"][AZURE_ID] = _with_container_names(["Australia East", "East US 2"])
    inc = DatabricksProvider().fetch()[0]
    assert inc.external_id.startswith("azure:")
    assert inc.regions == [Region("azure", "australiaeast"), Region("azure", "eastus2")]
    assert inc.url and inc.url.startswith(
        f"https://status.azuredatabricks.net/pages/incident/{AZURE_ID}/"
    )


def test_gcp_page_normalises_hyphenated_names(feeds):
    feeds["payloads"][GCP_ID] = _with_container_names(["US-Central1", "EU-West1"])
    inc = DatabricksProvider().fetch()[0]
    assert inc.regions == [Region("gcp", "us-central1"), Region("gcp", "europe-west1")]
    assert inc.url and inc.url.startswith(
        f"https://status.gcp.databricks.com/pages/incident/{GCP_ID}/"
    )


def test_unknown_container_is_dropped_without_error(feeds):
    feeds["payloads"][AWS_ID] = _with_container_names(["Global", "US East 1"])
    inc = DatabricksProvider().fetch()[0]
    assert inc.regions == [Region("aws", "us-east-1")]


@pytest.mark.parametrize(
    "code,expected",
    [
        (300, "minor"),
        (400, "major"),
        (500, "critical"),
        (600, "critical"),
        (999, "major"),
    ],
)
def test_status_code_mapping(feeds, code, expected):
    payload = copy.deepcopy(INCIDENT)
    payload["result"]["incidents"][0]["current_status"] = code
    feeds["payloads"][AWS_ID] = payload
    assert DatabricksProvider().fetch()[0].severity == expected


def test_missing_current_status_falls_back_to_newest_message(feeds):
    payload = copy.deepcopy(INCIDENT)
    item = payload["result"]["incidents"][0]
    del item["current_status"]
    item["messages"][1]["status"] = 300
    feeds["payloads"][AWS_ID] = payload
    assert DatabricksProvider().fetch()[0].severity == "minor"


def test_no_messages_falls_back_to_datetime_open(feeds):
    payload = copy.deepcopy(INCIDENT)
    payload["result"]["incidents"][0]["messages"] = []
    feeds["payloads"][AWS_ID] = payload
    inc = DatabricksProvider().fetch()[0]
    assert inc.updated_at == inc.started_at
    assert inc.last_message == ""


def test_one_page_failure_raises_without_partial_result(feeds):
    feeds["payloads"][AWS_ID] = copy.deepcopy(INCIDENT)
    feeds["raise_for"].add(GCP_ID)
    with pytest.raises(RuntimeError):
        DatabricksProvider().fetch()


def test_end_to_end_incident_then_quiet_resolves(feeds, conn):
    out = io.StringIO()
    feeds["payloads"][AWS_ID] = copy.deepcopy(INCIDENT)
    assert (
        poll_providers(
            conn,
            {"databricks": DatabricksProvider()},
            out=out,
            now=utc(2026, 9, 5, 10, 10),
        )
        == 0
    )
    assert [i.external_id for i in db.open_incidents(conn)] == [
        "aws:6afd0c1e2b3c4d5e6f708192"
    ]

    feeds["payloads"][AWS_ID] = copy.deepcopy(QUIET)
    assert (
        poll_providers(
            conn,
            {"databricks": DatabricksProvider()},
            out=out,
            now=utc(2026, 9, 5, 10, 12),
        )
        == 0
    )
    assert db.open_incidents(conn) == []
    resolved = db.recent_resolved(conn, utc(2000, 1, 1))
    assert resolved[0].resolved_at == utc(2026, 9, 5, 10, 12)


def test_failed_poll_does_not_resolve_open_incident(feeds, conn):
    feeds["payloads"][AWS_ID] = copy.deepcopy(INCIDENT)
    poll_providers(conn, {"databricks": DatabricksProvider()}, out=io.StringIO())
    feeds["raise_for"].add(AZURE_ID)
    assert (
        poll_providers(conn, {"databricks": DatabricksProvider()}, out=io.StringIO())
        == 1
    )
    assert len(db.open_incidents(conn)) == 1
