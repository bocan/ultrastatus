import copy
import io
import json
from pathlib import Path
from typing import Any

import pytest

from statusboard import db, http, regions
from statusboard.cli import poll_providers
from statusboard.model import Region
from statusboard.providers import PROVIDERS
from statusboard.providers.snowflake import (
    REGION_GROUPS,
    UNMAPPED_GROUPS,
    SnowflakeProvider,
)

FIXTURES = Path(__file__).parent / "fixtures"
COMPONENTS_URL = "https://status.snowflake.com/api/v2/components.json"
INCIDENTS_URL = "https://status.snowflake.com/api/v2/incidents.json"
COMPONENTS = json.loads((FIXTURES / "snowflake_components.json").read_text())
INCIDENTS = json.loads((FIXTURES / "snowflake_incidents.json").read_text())


@pytest.fixture
def feeds(monkeypatch):
    state: dict[str, Any] = {
        "payloads": {
            COMPONENTS_URL: copy.deepcopy(COMPONENTS),
            INCIDENTS_URL: copy.deepcopy(INCIDENTS),
        },
        "raise_for": set(),
        "requested": [],
    }

    def fake_fetch(url, timeout=20.0):
        state["requested"].append(url)
        if url in state["raise_for"]:
            raise RuntimeError(f"simulated failure for {url}")
        return json.dumps(state["payloads"][url]).encode()

    monkeypatch.setattr(http, "fetch_bytes", fake_fetch)
    return state


def _by_id(incidents):
    return {i.external_id: i for i in incidents}


def _group_name_to_id():
    return {c["name"]: c["id"] for c in COMPONENTS["components"] if c["group"]}


def test_every_live_group_is_mapped_or_knowingly_dropped():
    names = {c["name"] for c in COMPONENTS["components"] if c["group"]}
    unknown = names - set(REGION_GROUPS) - UNMAPPED_GROUPS
    assert unknown == set(), f"new Snowflake region groups: {sorted(unknown)}"
    assert len(names) == 53


def test_every_mapped_code_exists_in_the_region_table():
    for name, (cloud, code) in REGION_GROUPS.items():
        assert regions.lookup(cloud, code) is not None, f"{name} -> {cloud} {code}"


def test_regions_come_from_component_groups(feeds):
    by_id = _by_id(SnowflakeProvider().fetch())
    assert by_id["9p16kxkml7v2"].regions == [Region("gcp", "us-central1")]
    assert by_id["fl9tkpj8d7hk"].regions == [
        Region("aws", "eu-central-1")
    ]  # three components, one group
    assert by_id["847dlygl25yb"].regions == [
        Region("aws", "us-west-2"),
        Region("aws", "us-gov-west-1"),
        Region("aws", "ca-central-1"),
    ]  # the DoD group is dropped


def test_two_clouds_in_one_incident(feeds):
    ids = _group_name_to_id()
    item = feeds["payloads"][INCIDENTS_URL]["incidents"][0]
    item["components"] = [
        {
            "id": "a",
            "name": "Applications",
            "group_id": ids["AWS - Europe (London)"],
            "group": False,
        },
        {
            "id": "b",
            "name": "Applications",
            "group_id": ids["Azure - UK South (London)"],
            "group": False,
        },
        {
            "id": "c",
            "name": "Developer Tools",
            "group_id": ids["AWS - Europe (London)"],
            "group": False,
        },
        {
            "id": "d",
            "name": "Applications",
            "group_id": "no-such-group",
            "group": False,
        },
    ]
    inc = _by_id(SnowflakeProvider().fetch())["9p16kxkml7v2"]
    assert inc.regions == [Region("aws", "eu-west-2"), Region("azure", "uksouth")]


def test_incident_with_no_components_is_global(feeds):
    feeds["payloads"][INCIDENTS_URL]["incidents"][0]["components"] = []
    assert _by_id(SnowflakeProvider().fetch())["9p16kxkml7v2"].regions == []


def test_fetch_order_and_statuspage_fields(feeds):
    incidents = SnowflakeProvider().fetch()
    assert feeds["requested"] == [COMPONENTS_URL, INCIDENTS_URL]
    open_inc = _by_id(incidents)["9p16kxkml7v2"]
    assert open_inc.provider == "snowflake"
    assert open_inc.resolved_at is None
    assert open_inc.severity == "minor"
    assert open_inc.url.startswith("https://stspg.io/")


def test_components_failure_raises_without_partial_result(feeds):
    feeds["raise_for"].add(COMPONENTS_URL)
    with pytest.raises(RuntimeError):
        SnowflakeProvider().fetch()
    assert feeds["requested"] == [COMPONENTS_URL]


def test_registered_with_label_and_group():
    provider = PROVIDERS["snowflake"]
    assert isinstance(provider, SnowflakeProvider)
    assert provider.label == "Snowflake"
    assert provider.lists_resolved is True


def test_end_to_end_poll_writes_region_rows(feeds, conn):
    out = io.StringIO()
    assert poll_providers(conn, {"snowflake": SnowflakeProvider()}, out=out) == 0
    assert out.getvalue().strip() == "snowflake: 3 incidents, 0 newly resolved"
    rows = conn.execute(
        "SELECT cloud, region_code FROM incident_region WHERE provider='snowflake' ORDER BY region_code"
    ).fetchall()
    assert [(r["cloud"], r["region_code"]) for r in rows] == [
        ("aws", "ca-central-1"),
        ("aws", "eu-central-1"),
        ("gcp", "us-central1"),
        ("aws", "us-gov-west-1"),
        ("aws", "us-west-2"),
    ]
    assert [i.external_id for i in db.open_incidents(conn)] == ["9p16kxkml7v2"]
