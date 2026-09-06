import re
from datetime import timedelta

import pytest

from statusboard import db
from statusboard import render as render_module
from statusboard.config import Config
from statusboard.model import Region
from statusboard.render import PROVIDER_ORDER, build_context, render

from conftest import make_incident, utc


@pytest.fixture
def config(monkeypatch):
    """Call with a set of (cloud, code) pairs to activate the filter for one test."""

    def activate(my_regions):
        monkeypatch.setattr(
            render_module, "load_config", lambda: Config(frozenset(my_regions))
        )

    return activate


NOW = utc(2026, 9, 5, 20, 10, 0)
EXPECTED_NAMES = [
    "aws",
    "gcp",
    "azure",
    "databricks",
    "dbt",
    "snowflake",
    "airbyte",
    "claude",
    "openai",
    "github",
    "cloudflare",
    "npm",
    "docker",
    "pypi",
    "google-workspace",
    "slack",
    "atlassian",
]
TILE_COUNT = len(EXPECTED_NAMES)


def _fresh_polls(conn, names=EXPECTED_NAMES, at=None):
    for name in names:
        db.record_poll(conn, name, at or NOW - timedelta(minutes=1), None)


def test_empty_database_gives_all_stale_providers(conn):
    ctx = build_context(conn, NOW)
    assert [p["name"] for p in ctx["providers"]] == EXPECTED_NAMES
    assert [p["name"] for p in ctx["providers"]] == [n for n, _ in PROVIDER_ORDER]
    assert all(p["level"] == "stale" for p in ctx["providers"])
    assert all(p["polled_at"] is None for p in ctx["providers"])
    assert ctx["open"] == [] and ctx["resolved"] == []
    assert ctx["generated_at"] == "2026-09-05T20:10:00Z"


def test_levels_follow_worst_open_severity(conn):
    _fresh_polls(conn)
    db.upsert_incident(
        conn, make_incident(provider="aws", external_id="a", severity="minor")
    )
    db.upsert_incident(
        conn, make_incident(provider="aws", external_id="b", severity="critical")
    )
    db.upsert_incident(
        conn, make_incident(provider="gcp", external_id="c", severity="major")
    )

    levels = {p["name"]: p["level"] for p in build_context(conn, NOW)["providers"]}
    assert levels["aws"] == "critical"
    assert levels["gcp"] == "major"
    assert levels["azure"] == "ok"
    counts = {p["name"]: p["open_count"] for p in build_context(conn, NOW)["providers"]}
    assert counts["aws"] == 2 and counts["azure"] == 0


def test_old_poll_is_stale_even_with_no_incidents(conn):
    _fresh_polls(conn, names=[n for n in EXPECTED_NAMES if n != "npm"])
    db.record_poll(conn, "npm", NOW - timedelta(minutes=20), None)
    levels = {p["name"]: p["level"] for p in build_context(conn, NOW)["providers"]}
    assert levels["npm"] == "stale"
    assert levels["docker"] == "ok"


def test_poll_error_is_stale_and_carries_text(conn):
    _fresh_polls(conn)
    db.record_poll(conn, "azure", NOW, "RuntimeError: feed exploded")
    provider = {p["name"]: p for p in build_context(conn, NOW)["providers"]}["azure"]
    assert provider["level"] == "stale"
    assert provider["poll_error"] == "RuntimeError: feed exploded"
    assert provider["polled_at"] == "2026-09-05T20:10:00Z"


def test_stale_provider_still_lists_its_open_incidents(conn):
    db.upsert_incident(
        conn, make_incident(provider="aws", external_id="a", severity="critical")
    )
    ctx = build_context(conn, NOW)
    assert [i["provider"] for i in ctx["open"]] == ["aws"]
    assert ctx["providers"][0]["level"] == "stale"


def test_resolved_window_is_seven_days(conn):
    db.upsert_incident(
        conn,
        make_incident(
            provider="gcp", external_id="old", resolved_at=NOW - timedelta(days=8)
        ),
    )
    db.upsert_incident(
        conn,
        make_incident(
            provider="gcp", external_id="new", resolved_at=NOW - timedelta(days=6)
        ),
    )
    ctx = build_context(conn, NOW)
    assert [i["title"] for i in ctx["resolved"]] == ["Something broke"]
    assert ctx["resolved"][0]["resolved_at"] == db.to_iso(NOW - timedelta(days=6))


def test_incident_dict_shape(conn):
    db.upsert_incident(
        conn,
        make_incident(
            provider="databricks",
            external_id="x",
            last_message="m" * 300,
            regions=[Region("aws", "us-east-1"), Region("azure", "eastus")],
        ),
    )
    inc = build_context(conn, NOW)["open"][0]
    assert inc["provider_label"] == "Databricks"
    assert inc["region_labels"] == ["aws us-east-1", "azure eastus"]
    assert len(inc["last_message"]) == 240
    assert inc["last_message"].endswith("…")
    assert inc["last_message_full"] == "m" * 300


def test_render_writes_page_for_empty_database(conn, tmp_path):
    target = render(conn, tmp_path / "site", now=NOW)
    html = target.read_text()
    assert target.name == "index.html"
    assert "No open incidents." in html
    assert "Nothing resolved in the last 7 days." in html
    # ADR-0012: exactly one inline script, nothing fetched from the network.
    assert html.count("<script") == 1
    assert "<script src" not in html and "<script " not in html
    assert '<link rel="stylesheet"' not in html
    assert not re.search(r'<(script|link|img|iframe)[^>]+(src|href)="https?://', html)
    assert html.count('class="tile level-') == TILE_COUNT
    # Accessibility: the meta refresh serves only no-script browsers, the
    # script handles the reload otherwise; one main landmark; 24 px checkboxes.
    assert '<noscript><meta http-equiv="refresh" content="120"></noscript>' in html
    assert html.count("<main>") == 1 and html.count("</main>") == 1
    assert html.find("<main>") < html.find('class="tile level-') < html.find("</main>")
    assert 'input[type="checkbox"] { width: 24px; height: 24px;' in html
    # Cooperative gestures: the hint overlay exists and the map starts scrollable.
    assert '<div class="map-hint" role="status"' in html
    assert "svg.map { touch-action: pan-y;" in html


def test_render_includes_incident_title_and_link(conn, tmp_path):
    _fresh_polls(conn)
    db.upsert_incident(
        conn,
        make_incident(
            provider="cloudflare",
            external_id="z",
            title="Edge <b>trouble</b>",
            url="https://example.test/z",
        ),
    )
    html = render(conn, tmp_path / "site", now=NOW).read_text()
    assert 'href="https://example.test/z"' in html
    assert "Edge &lt;b&gt;trouble&lt;/b&gt;" in html  # autoescaped
    assert "Edge <b>trouble</b>" not in html
    assert "2026-09-05 10:00 UTC" in html


# ADR-0011: region filter.


def test_inactive_config_matches_unfiltered_shape(conn):
    ctx = build_context(conn, NOW)
    assert ctx["filter_active"] is False
    assert ctx["my_region_labels"] == []
    assert ctx["open_elsewhere"] == [] and ctx["resolved_elsewhere"] == []
    assert all(p["elsewhere_count"] == 0 for p in ctx["providers"])


def test_elsewhere_incident_does_not_raise_tile_level(conn, config):
    config({("aws", "eu-west-2")})
    _fresh_polls(conn)
    db.upsert_incident(
        conn,
        make_incident(
            provider="aws",
            external_id="a",
            severity="critical",
            regions=[Region("aws", "us-east-1")],
        ),
    )
    ctx = build_context(conn, NOW)
    aws = {p["name"]: p for p in ctx["providers"]}["aws"]
    assert aws["level"] == "ok"
    assert aws["open_count"] == 0
    assert aws["elsewhere_count"] == 1
    assert [i["title"] for i in ctx["open_elsewhere"]] == ["Something broke"]
    assert ctx["open"] == []
    assert ctx["all_clear"] is True


def test_my_region_incident_sets_level_and_clears_all_clear(conn, config):
    config({("aws", "eu-west-2")})
    _fresh_polls(conn)
    db.upsert_incident(
        conn,
        make_incident(
            provider="aws",
            external_id="a",
            severity="minor",
            regions=[Region("aws", "eu-west-2")],
        ),
    )
    ctx = build_context(conn, NOW)
    assert {p["name"]: p["level"] for p in ctx["providers"]}["aws"] == "minor"
    assert ctx["all_clear"] is False
    assert len(ctx["open"]) == 1
    assert ctx["my_region_labels"] == ["aws eu-west-2"]


def test_global_and_unmapped_incidents_are_always_mine(conn, config):
    config({("azure", "uksouth")})
    db.upsert_incident(
        conn,
        make_incident(
            provider="github", external_id="g", title="GitHub thing", regions=[]
        ),
    )
    db.upsert_incident(
        conn,
        make_incident(
            provider="gcp",
            external_id="x",
            title="GCP global",
            regions=[Region("gcp", "global")],
        ),
    )
    ctx = build_context(conn, NOW)
    assert {i["title"] for i in ctx["open"]} == {"GitHub thing", "GCP global"}
    assert ctx["open_elsewhere"] == []


def test_databricks_on_my_host_region_is_mine(conn, config):
    config({("aws", "eu-west-2")})
    _fresh_polls(conn)
    db.upsert_incident(
        conn,
        make_incident(
            provider="databricks",
            external_id="d",
            severity="major",
            regions=[Region("aws", "eu-west-2")],
        ),
    )
    ctx = build_context(conn, NOW)
    assert [i["provider"] for i in ctx["open"]] == ["databricks"]
    assert {p["name"]: p["level"] for p in ctx["providers"]}["databricks"] == "major"
    assert "London): major. Something broke" in ctx["map_svg"]


def test_snowflake_on_my_host_region_is_mine_and_colours_the_marker(conn, config):
    config({("aws", "eu-west-2")})
    _fresh_polls(conn)
    db.upsert_incident(
        conn,
        make_incident(
            provider="snowflake",
            external_id="s",
            severity="major",
            regions=[Region("aws", "eu-west-2")],
        ),
    )
    ctx = build_context(conn, NOW)
    assert [i["provider"] for i in ctx["open"]] == ["snowflake"]
    assert {p["name"]: p["level"] for p in ctx["providers"]}["snowflake"] == "major"
    assert "London): major. Something broke" in ctx["map_svg"]


def test_open_sorts_by_severity_then_updated(conn):
    db.upsert_incident(
        conn,
        make_incident(
            provider="aws",
            external_id="old-minor",
            title="old minor",
            severity="minor",
            updated_at=NOW - timedelta(hours=5),
        ),
    )
    db.upsert_incident(
        conn,
        make_incident(
            provider="aws",
            external_id="new-minor",
            title="new minor",
            severity="minor",
            updated_at=NOW - timedelta(hours=1),
        ),
    )
    db.upsert_incident(
        conn,
        make_incident(
            provider="aws",
            external_id="crit",
            title="crit",
            severity="critical",
            updated_at=NOW - timedelta(hours=9),
        ),
    )
    ctx = build_context(conn, NOW)
    assert [i["title"] for i in ctx["open"]] == ["crit", "new minor", "old minor"]


def test_rendered_html_banner_and_details(conn, config, tmp_path):
    config({("aws", "eu-west-2")})
    _fresh_polls(conn)
    html = render(conn, tmp_path / "a", now=NOW).read_text()
    assert "All clear in your regions: aws eu-west-2" in html
    assert "<details" not in html
    assert "Open in your regions" in html

    db.upsert_incident(
        conn,
        make_incident(
            provider="aws", external_id="e", regions=[Region("aws", "us-east-1")]
        ),
    )
    html = render(conn, tmp_path / "b", now=NOW).read_text()
    assert "Open elsewhere (1)" in html
    assert "<details" in html
    assert "0 open in your regions" in html
    assert "1 elsewhere" in html


# ADR-0014: tile groups.


def _group(ctx, label):
    return next(g for g in ctx["groups"] if g["label"] == label)


def test_groups_follow_the_declared_order_and_skip_empty_ones(conn):
    ctx = build_context(conn, NOW)
    assert [g["label"] for g in ctx["groups"]] == [
        "Clouds",
        "Data platforms",
        "AI",
        "Developer tooling",
        "Workplace",
    ]
    assert [p["name"] for p in _group(ctx, "Workplace")["providers"]] == [
        "google-workspace",
        "slack",
        "atlassian",
    ]
    assert [p["name"] for p in _group(ctx, "Clouds")["providers"]] == [
        "aws",
        "gcp",
        "azure",
    ]
    assert [p["name"] for p in _group(ctx, "Developer tooling")["providers"]] == [
        "github",
        "cloudflare",
        "npm",
        "docker",
        "pypi",
    ]
    assert [p["name"] for g in ctx["groups"] for p in g["providers"]] == EXPECTED_NAMES


def test_group_level_is_worst_incident_level(conn):
    _fresh_polls(conn)
    db.upsert_incident(
        conn, make_incident(provider="aws", external_id="a", severity="critical")
    )
    db.upsert_incident(
        conn, make_incident(provider="gcp", external_id="b", severity="minor")
    )
    clouds = _group(build_context(conn, NOW), "Clouds")
    assert clouds["level"] == "critical"
    assert clouds["open_count"] == 2
    assert clouds["has_regions"] is True


def test_group_is_stale_only_when_every_member_is_stale(conn):
    _fresh_polls(conn, names=["gcp", "azure"])  # aws never polled, so stale
    ctx = build_context(conn, NOW)
    assert _group(ctx, "Clouds")["level"] == "ok"
    assert (
        _group(ctx, "Developer tooling")["level"] == "stale"
    )  # none of its members polled
    assert _group(ctx, "AI")["level"] == "stale"
    assert _group(ctx, "Workplace")["level"] == "stale"


def test_rendered_groups_have_headings_in_order_and_all_tiles(conn, tmp_path):
    _fresh_polls(conn)
    html = render(conn, tmp_path / "site", now=NOW).read_text()
    assert html.count('<section class="group">') == 5
    positions = [
        html.find(f"\n    {label}\n")
        for label in (
            "Clouds",
            "Data platforms",
            "AI",
            "Developer tooling",
            "Workplace",
        )
    ]
    assert all(p >= 0 for p in positions) and positions == sorted(positions)
    assert html.count('class="tile level-') == TILE_COUNT


def test_empty_group_is_not_rendered(conn, monkeypatch):
    monkeypatch.setattr(render_module, "GROUPS", render_module.GROUPS + [("Ghost", [])])
    ctx = build_context(conn, NOW)
    assert "Ghost" not in [g["label"] for g in ctx["groups"]]


def test_group_heading_counts_open_in_your_regions(conn, config, tmp_path):
    config({("aws", "eu-west-2")})
    _fresh_polls(conn)
    db.upsert_incident(
        conn,
        make_incident(
            provider="aws", external_id="a", regions=[Region("aws", "eu-west-2")]
        ),
    )
    html = render(conn, tmp_path / "site", now=NOW).read_text()
    assert "1 open in your regions" in html
    assert _group(build_context(conn, NOW), "Clouds")["open_count"] == 1


def test_rendered_html_without_config_is_unchanged(conn, tmp_path):
    html = render(conn, tmp_path / "site", now=NOW).read_text()
    assert "banner" not in html.split("</style>")[1]
    assert "<details" not in html
    assert "Open incidents" in html
    assert "your regions" not in html.split("</style>")[1]
