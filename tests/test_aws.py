import codecs
import io
import json
from pathlib import Path

import pytest

from statusboard import db, http
from statusboard.cli import poll_providers
from statusboard.model import Region
from statusboard.providers.aws import AwsProvider, _decode, _region_from_arn

from conftest import utc

FIXTURE = Path(__file__).parent / "fixtures" / "aws_currentevents.json"
FEED_URL = "https://health.aws.amazon.com/public/currentevents"


@pytest.fixture
def feed(monkeypatch):
    """Serve the fixture as UTF-16 BE with a BOM, exactly as the live feed does."""
    state = {"payload": json.loads(FIXTURE.read_text())}

    def fake_fetch(url, timeout=20.0):
        assert url == FEED_URL
        return codecs.BOM_UTF16_BE + json.dumps(state["payload"]).encode("utf-16-be")

    monkeypatch.setattr(http, "fetch_bytes", fake_fetch)
    return state


def test_decode_handles_all_three_encodings():
    text = '[{"a": "é"}]'
    assert _decode(codecs.BOM_UTF16_LE + text.encode("utf-16-le")) == text
    assert _decode(codecs.BOM_UTF16_BE + text.encode("utf-16-be")) == text
    assert _decode(text.encode("utf-8")) == text


def test_fixture_parses_with_arn_as_id(feed):
    incidents = AwsProvider().fetch()
    assert len(incidents) == 2
    assert all(i.external_id.startswith("arn:aws:health:") for i in incidents)
    assert all(i.provider == "aws" for i in incidents)


def test_region_from_arn():
    assert _region_from_arn("arn:aws:health:me-central-1::event/X/Y/Z") == [Region("aws", "me-central-1")]
    assert _region_from_arn("arn:aws:health:::event/X/Y/Z") == []


def test_severity_mapping(feed):
    payload = feed["payload"]
    payload[0]["status"] = "1"
    payload[1]["status"] = "2"
    by_id = {i.external_id: i for i in AwsProvider().fetch()}
    assert by_id[payload[0]["arn"]].severity == "minor"
    assert by_id[payload[1]["arn"]].severity == "major"

    payload[0]["status"] = "3"
    payload[1]["status"] = "9"
    by_id = {i.external_id: i for i in AwsProvider().fetch()}
    assert by_id[payload[0]["arn"]].severity == "critical"
    assert by_id[payload[1]["arn"]].severity == "major"


def test_field_mapping(feed):
    inc = AwsProvider().fetch()[0]
    assert inc.title == "Multiple services: Increased Error Rates"
    assert inc.started_at == utc(2026, 3, 1, 12, 51, 25)
    assert inc.updated_at == utc(2026, 4, 30, 7, 25, 54)
    assert inc.resolved_at is None
    assert inc.url == "https://health.aws.amazon.com/health/status"
    assert inc.last_message.startswith("We are providing an update on the ongoing service disruption.")
    assert inc.regions == [Region("aws", "me-central-1")]


def test_empty_event_log_falls_back(feed):
    feed["payload"][0]["event_log"] = []
    inc = AwsProvider().fetch()[0]
    assert inc.updated_at == inc.started_at
    assert inc.last_message == ""


def test_end_to_end_resolves_vanished_event(feed, conn):
    out = io.StringIO()
    assert poll_providers(conn, {"aws": AwsProvider()}, out=out, now=utc(2026, 9, 5, 10, 0)) == 0
    assert len(db.open_incidents(conn)) == 2

    dropped = feed["payload"].pop(1)
    assert poll_providers(conn, {"aws": AwsProvider()}, out=out, now=utc(2026, 9, 5, 10, 2)) == 0

    open_ids = [i.external_id for i in db.open_incidents(conn)]
    assert open_ids == [feed["payload"][0]["arn"]]
    resolved = db.recent_resolved(conn, utc(2000, 1, 1))
    assert [i.external_id for i in resolved] == [dropped["arn"]]
    assert resolved[0].resolved_at == utc(2026, 9, 5, 10, 2)
    assert out.getvalue().splitlines() == [
        "aws: 2 incidents, 0 newly resolved",
        "aws: 1 incidents, 1 newly resolved",
    ]
