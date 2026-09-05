import io
from pathlib import Path

import pytest

from statusboard import db, http
from statusboard.cli import poll_providers
from statusboard.model import Region
from statusboard.providers.azure import AzureProvider, _parse_pubdate, _regions_from_text

from conftest import utc

FIXTURES = Path(__file__).parent / "fixtures"
EMPTY = (FIXTURES / "azure_empty.xml").read_bytes()
ITEMS = (FIXTURES / "azure_items.xml").read_bytes()


@pytest.fixture
def feed(monkeypatch):
    state = {"body": ITEMS}

    def fake_fetch(url, timeout=20.0):
        assert url == "https://azure.status.microsoft/en-us/status/feed/"
        return state["body"]

    monkeypatch.setattr(http, "fetch_bytes", fake_fetch)
    return state


def _by_title(incidents):
    return {i.title: i for i in incidents}


def test_empty_feed_yields_nothing(feed):
    feed["body"] = EMPTY
    assert AzureProvider().fetch() == []


def test_item_with_guid_and_categories(feed):
    inc = _by_title(AzureProvider().fetch())["Awareness - Virtual Machines"]
    assert inc.provider == "azure"
    assert inc.external_id == "awareness-virtual-machines"
    assert inc.severity == "major"
    assert inc.resolved_at is None  # "mitigation" is not "mitigated"
    assert inc.regions == [Region("azure", "westeurope"), Region("azure", "northeurope"), Region("azure", "eastus2")]
    assert inc.started_at == utc(2024, 7, 18, 4, 9, 0)
    assert inc.updated_at == inc.started_at
    assert inc.url == "https://status.azure.com/en-us/status/"


def test_item_without_guid_falls_back_to_text_and_hash(feed):
    inc = _by_title(AzureProvider().fetch())["Storage - East US 2 - Mitigated"]
    assert inc.regions == [Region("azure", "eastus2")]
    assert inc.resolved_at == utc(2024, 7, 30, 10, 30, 0)
    assert len(inc.external_id) == 16
    assert all(c in "0123456789abcdef" for c in inc.external_id)
    again = _by_title(AzureProvider().fetch())["Storage - East US 2 - Mitigated"]
    assert again.external_id == inc.external_id


def test_non_region_categories_are_ignored(feed):
    inc = _by_title(AzureProvider().fetch())["Network Infrastructure - Issues accessing a subset of Microsoft services"]
    assert inc.regions == [Region("azure", "uksouth")]
    assert inc.resolved_at is None


def test_html_is_stripped_and_unescaped(feed):
    inc = _by_title(AzureProvider().fetch())["Awareness - Virtual Machines"]
    assert "<" not in inc.last_message
    assert "&nbsp;" not in inc.last_message
    assert "&lt;" not in inc.last_message
    assert inc.last_message.startswith("We have been made aware of an issue")


def test_text_matching_prefers_longest_name():
    assert _regions_from_text("Issue in East US 2 only") == [Region("azure", "eastus2")]
    # "West Europe" is longer than "East US", so it matches first.
    assert _regions_from_text("Issue in East US and West Europe") == [
        Region("azure", "westeurope"),
        Region("azure", "eastus"),
    ]
    assert _regions_from_text("no region here") == []


def test_pubdate_with_trailing_z_parses_to_utc():
    fallback = utc(2000, 1, 1)
    parsed = _parse_pubdate("Thu, 18 Jul 2024 04:09:00 Z", fallback)
    assert parsed == utc(2024, 7, 18, 4, 9, 0)
    assert parsed.tzinfo is not None
    assert _parse_pubdate("not a date", fallback) == fallback
    assert _parse_pubdate(None, fallback) == fallback


def test_end_to_end_items_then_empty_resolves(feed, conn):
    out = io.StringIO()
    assert poll_providers(conn, {"azure": AzureProvider()}, out=out, now=utc(2026, 9, 5, 10, 0)) == 0
    open_ids = {i.external_id for i in db.open_incidents(conn)}
    assert "awareness-virtual-machines" in open_ids
    assert len(open_ids) == 2

    feed["body"] = EMPTY
    assert poll_providers(conn, {"azure": AzureProvider()}, out=out, now=utc(2026, 9, 5, 10, 2)) == 0
    assert db.open_incidents(conn) == []
    by_id = {i.external_id: i for i in db.recent_resolved(conn, utc(2000, 1, 1))}
    assert by_id["awareness-virtual-machines"].resolved_at == utc(2026, 9, 5, 10, 2)
    assert out.getvalue().splitlines() == [
        "azure: 3 incidents, 0 newly resolved",
        "azure: 0 incidents, 2 newly resolved",
    ]
