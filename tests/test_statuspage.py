import io
import json
from pathlib import Path

import pytest

from statusboard import db, http
from statusboard.cli import poll_providers
from statusboard.providers import PROVIDERS
from statusboard.providers.statuspage import StatuspageProvider

from conftest import utc

FIXTURES = Path(__file__).parent / "fixtures"

GITHUB = StatuspageProvider("github", "www.githubstatus.com", "GitHub")
DOCKER = StatuspageProvider("docker", "www.dockerstatus.com", "Docker")


@pytest.fixture
def feeds(monkeypatch):
    """Serve a fixture per host, and record every URL requested."""
    state = {
        "payloads": {
            "www.githubstatus.com": json.loads(
                (FIXTURES / "github_incidents.json").read_text()
            ),
            "www.dockerstatus.com": json.loads(
                (FIXTURES / "docker_incidents.json").read_text()
            ),
        },
        "requested": [],
    }

    def fake_fetch(url, timeout=20.0):
        state["requested"].append(url)
        host = url.split("/")[2]
        payload = state["payloads"].get(host, {"incidents": []})
        return json.dumps(payload).encode()

    monkeypatch.setattr(http, "fetch_bytes", fake_fetch)
    return state


def _by_id(incidents):
    return {i.external_id: i for i in incidents}


# GitHub: the ADR-0002 tests, unchanged in intent.


def test_github_fetch_returns_one_incident_per_item(feeds):
    incidents = GITHUB.fetch()
    assert len(incidents) == len(feeds["payloads"]["www.githubstatus.com"]["incidents"])
    assert all(i.provider == "github" for i in incidents)


def test_severity_mapping_covers_all_impacts(feeds):
    by_id = _by_id(GITHUB.fetch())
    assert by_id["tx9qn4khd664"].severity == "critical"
    assert by_id["zw1hbx2yyhvr"].severity == "major"
    assert by_id["r05vk75c594j"].severity == "minor"
    assert by_id["wms44hv62t3p"].severity == "minor"  # impact "none"


def test_github_field_mapping_keeps_shortlink_and_started_at(feeds):
    inc = _by_id(GITHUB.fetch())["zw1hbx2yyhvr"]
    assert inc.title == "Disruption with Copilot Code Review"
    assert inc.url == "https://stspg.io/dddfhld6fj0z"
    assert inc.started_at.isoformat().startswith("2026-09-04T20:39:03")
    assert inc.updated_at.isoformat().startswith("2026-09-04T22:26:46")
    assert inc.resolved_at.isoformat().startswith("2026-09-04T22:26:46")
    assert inc.last_message.startswith("This incident has been resolved.")
    assert inc.regions == []


def test_open_incident_has_no_resolved_at(feeds):
    item = feeds["payloads"]["www.githubstatus.com"]["incidents"][0]
    item["resolved_at"] = None
    item["status"] = "monitoring"
    assert GITHUB.fetch()[0].resolved_at is None


def test_empty_updates_gives_empty_message(feeds):
    feeds["payloads"]["www.githubstatus.com"]["incidents"][0]["incident_updates"] = []
    assert GITHUB.fetch()[0].last_message == ""


def test_unknown_impact_maps_to_major(feeds):
    feeds["payloads"]["www.githubstatus.com"]["incidents"][0]["impact"] = "weird"
    assert GITHUB.fetch()[0].severity == "major"


# Docker: incident.io shape without started_at or shortlink.


def test_docker_falls_back_to_created_at_and_incident_url(feeds):
    incidents = DOCKER.fetch()
    assert len(incidents) == 3
    inc = incidents[0]
    assert "started_at" not in feeds["payloads"]["www.dockerstatus.com"]["incidents"][0]
    assert inc.started_at == utc(2026, 8, 24, 19, 13, 56)
    assert (
        inc.url == "https://www.dockerstatus.com/incidents/01M0TK349Z8VCJ3ERNSAAW7YKA"
    )
    assert inc.resolved_at == utc(2026, 7, 31, 20, 48, 37)
    assert inc.last_message == "Resolved"
    assert inc.severity == "major"


# Registry and per-host routing.


EXPECTED_STATUSPAGE = {
    "github": ("www.githubstatus.com", "GitHub"),
    "cloudflare": ("www.cloudflarestatus.com", "Cloudflare"),
    "claude": ("status.claude.com", "Claude"),
    "npm": ("status.npmjs.org", "npm"),
    "docker": ("www.dockerstatus.com", "Docker"),
    "dbt": ("status.getdbt.com", "dbt Cloud"),
    "openai": ("status.openai.com", "OpenAI"),
    "atlassian": ("status.atlassian.com", "Atlassian"),
    "pypi": ("status.python.org", "PyPI"),
}


def test_statuspage_providers_are_registered_with_hosts_and_labels():
    for name, (host, label) in EXPECTED_STATUSPAGE.items():
        provider = PROVIDERS[name]
        assert isinstance(provider, StatuspageProvider), name
        assert provider.host == host
        assert provider.label == label
        assert provider.lists_resolved is True


def test_each_instance_requests_its_own_host(feeds):
    for name in EXPECTED_STATUSPAGE:
        PROVIDERS[name].fetch()
    assert feeds["requested"] == [
        f"https://{host}/api/v2/incidents.json"
        for host, _ in EXPECTED_STATUSPAGE.values()
    ]


def test_incident_io_shaped_feed_on_dbt_uses_the_fallbacks(feeds):
    # Reuse the Docker fixture, which has no started_at or shortlink, served for dbt's host.
    feeds["payloads"]["status.getdbt.com"] = feeds["payloads"]["www.dockerstatus.com"]
    incidents = PROVIDERS["dbt"].fetch()
    assert len(incidents) == 3
    inc = incidents[0]
    assert inc.provider == "dbt"
    assert inc.started_at == utc(2026, 8, 24, 19, 13, 56)
    assert inc.url == "https://status.getdbt.com/incidents/01M0TK349Z8VCJ3ERNSAAW7YKA"


def test_end_to_end_poll(feeds, conn):
    out = io.StringIO()
    assert poll_providers(conn, {"github": GITHUB, "docker": DOCKER}, out=out) == 0
    stored = db.open_incidents(conn) + db.recent_resolved(conn, utc(2000, 1, 1))
    assert len(stored) == 5 + 3
    assert out.getvalue().splitlines() == [
        "github: 5 incidents, 0 newly resolved",
        "docker: 3 incidents, 0 newly resolved",
    ]
