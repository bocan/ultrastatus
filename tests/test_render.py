from datetime import timedelta

from statusboard import db
from statusboard.model import Region
from statusboard.render import PROVIDER_ORDER, build_context, render

from conftest import make_incident, utc

NOW = utc(2026, 9, 5, 20, 10, 0)
EXPECTED_NAMES = ["aws", "gcp", "azure", "github", "databricks", "cloudflare", "claude", "npm", "docker"]


def _fresh_polls(conn, names=EXPECTED_NAMES, at=None):
    for name in names:
        db.record_poll(conn, name, at or NOW - timedelta(minutes=1), None)


def test_empty_database_gives_nine_stale_providers(conn):
    ctx = build_context(conn, NOW)
    assert [p["name"] for p in ctx["providers"]] == EXPECTED_NAMES
    assert [p["name"] for p in ctx["providers"]] == [n for n, _ in PROVIDER_ORDER]
    assert all(p["level"] == "stale" for p in ctx["providers"])
    assert all(p["polled_at"] is None for p in ctx["providers"])
    assert ctx["open"] == [] and ctx["resolved"] == []
    assert ctx["generated_at"] == "2026-09-05T20:10:00Z"


def test_levels_follow_worst_open_severity(conn):
    _fresh_polls(conn)
    db.upsert_incident(conn, make_incident(provider="aws", external_id="a", severity="minor"))
    db.upsert_incident(conn, make_incident(provider="aws", external_id="b", severity="critical"))
    db.upsert_incident(conn, make_incident(provider="gcp", external_id="c", severity="major"))

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
    db.upsert_incident(conn, make_incident(provider="aws", external_id="a", severity="critical"))
    ctx = build_context(conn, NOW)
    assert [i["provider"] for i in ctx["open"]] == ["aws"]
    assert ctx["providers"][0]["level"] == "stale"


def test_resolved_window_is_seven_days(conn):
    db.upsert_incident(conn, make_incident(provider="gcp", external_id="old", resolved_at=NOW - timedelta(days=8)))
    db.upsert_incident(conn, make_incident(provider="gcp", external_id="new", resolved_at=NOW - timedelta(days=6)))
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
    assert "<script" not in html
    assert html.count('class="tile level-') == 9
    assert 'http-equiv="refresh"' in html


def test_render_includes_incident_title_and_link(conn, tmp_path):
    _fresh_polls(conn)
    db.upsert_incident(
        conn,
        make_incident(provider="cloudflare", external_id="z", title="Edge <b>trouble</b>", url="https://example.test/z"),
    )
    html = render(conn, tmp_path / "site", now=NOW).read_text()
    assert 'href="https://example.test/z"' in html
    assert "Edge &lt;b&gt;trouble&lt;/b&gt;" in html  # autoescaped
    assert "Edge <b>trouble</b>" not in html
    assert "2026-09-05 10:00 UTC" in html
