"""ADR-0013: pure-CSS hover cards."""

import re
from datetime import timedelta

from statusboard import db, regions
from statusboard.mapgen import Marker, card_html, card_style, hover_css, marker_layout, render_svg
from statusboard.model import Region
from statusboard.render import build_context, render

from conftest import make_incident, utc

NOW = utc(2026, 9, 5, 20, 10, 0)


def _marker(x=100.0, y=100.0, level="ok", incidents=None, mine=True, code="us-east-1", cloud="aws"):
    return Marker(cloud, code, "N. Virginia (Ashburn)", x, y, level, [], mine, incidents or [])


def test_every_circle_has_key_and_tabindex():
    markers = marker_layout(regions.all_regions(), {})
    svg = render_svg(markers, "M0 0Z")
    circles = re.findall(r"<circle [^>]*>", svg)
    assert len(circles) == len(markers)
    keys = set()
    for c in circles:
        assert 'tabindex="0"' in c
        key = re.search(r'data-key="([^"]+)"', c).group(1)
        keys.add(key)
    assert keys == {f"{m.cloud}:{m.code}" for m in markers}


def test_every_marker_label_and_card_carries_its_cloud():
    markers = marker_layout(regions.all_regions(), {})
    svg = render_svg(markers, "M0 0Z")
    for tag in ("<circle ", '<text class="label" ', '<div class="card" '):
        found = re.findall(re.escape(tag) + r'[^>]*data-cloud="(aws|gcp|azure)"', svg)
        assert len(found) == len(markers), tag
    assert sorted(re.findall(r'<circle [^>]*data-cloud="(\w+)"', svg)) == sorted(m.cloud for m in markers)


def test_cloud_toggle_rules_are_in_the_page(conn, tmp_path):
    html = render(conn, tmp_path / "site", now=NOW).read_text()
    for cloud in ("aws", "gcp", "azure"):
        assert f'id="toggle-{cloud}" checked' in html
        assert f'.map-wrap:has(#toggle-{cloud}:not(:checked))' in html
        assert f'svg.map [data-cloud="{cloud}"]' in html


def test_cards_layer_comes_after_last_circle_with_one_card_per_marker():
    markers = marker_layout(regions.all_regions(), {})
    svg = render_svg(markers, "M0 0Z")
    assert svg.count("<foreignObject") == 1
    assert svg.rfind("<circle") < svg.find("<foreignObject")
    assert 'xmlns="http://www.w3.org/1999/xhtml"' in svg
    card_keys = re.findall(r'<div class="card" data-key="([^"]+)"', svg)
    assert sorted(card_keys) == sorted(f"{m.cloud}:{m.code}" for m in markers)


def test_hover_css_one_rule_per_marker_with_hover_and_focus():
    markers = marker_layout(regions.all_regions(), {})
    css = hover_css(markers)
    rules = css.splitlines()
    assert len(rules) == len(markers)
    for m in markers:
        rule = next(r for r in rules if f'[data-key="{m.cloud}:{m.code}"]:hover' in r)
        assert f'[data-key="{m.cloud}:{m.code}"]:focus-visible' in rule
        assert f'.card[data-key="{m.cloud}:{m.code}"]' in rule
        assert "opacity:1" in rule and "visibility:visible" in rule


def test_card_opens_left_past_the_flip_line():
    assert card_style(_marker(x=900.0)).startswith("right: ")
    assert "left:" not in card_style(_marker(x=900.0))
    assert card_style(_marker(x=100.0)).startswith("left: 10.4%")


def test_card_opens_upward_in_the_bottom_third():
    assert "bottom: " in card_style(_marker(y=380.0))
    assert "top:" not in card_style(_marker(y=380.0))
    assert "top: " in card_style(_marker(y=100.0))


def test_card_lists_five_and_counts_the_rest():
    incidents = [{"title": f"Incident {i}", "url": f"https://x.test/{i}", "severity": "minor"} for i in range(6)]
    html = card_html(_marker(level="minor", incidents=incidents), filter_active=False)
    assert html.count("<li>") == 5
    assert "and 1 more" in html
    assert 'href="https://x.test/0"' in html
    assert "No open incidents" not in html


def test_single_incident_has_no_repeated_severity_chip():
    one = card_html(_marker(level="critical", incidents=[{"title": "Only one", "url": None, "severity": "critical"}]), False)
    assert one.count("chip level-critical") == 1  # the region level in the head only
    two = card_html(
        _marker(level="critical", incidents=[
            {"title": "First", "url": None, "severity": "critical"},
            {"title": "Second", "url": None, "severity": "minor"},
        ]),
        False,
    )
    assert two.count("chip level-critical") == 2
    assert two.count("chip level-minor") == 1


def test_card_with_no_incidents_says_so():
    html = card_html(_marker(), filter_active=False)
    assert "No open incidents" in html
    assert "<li>" not in html
    assert "<b>AWS us-east-1</b>" in html
    assert "N. Virginia (Ashburn)" in html
    assert 'chip level-ok">ok</span>' in html


def test_card_escapes_titles():
    m = _marker(level="major", incidents=[{"title": "A <b>bad</b> day", "url": None, "severity": "major"}])
    m.titles = ["A <b>bad</b> day"]
    html = card_html(m, filter_active=False)
    assert "A &lt;b&gt;bad&lt;/b&gt; day" in html
    assert "<b>bad</b>" not in html
    assert "<a " not in html  # no url, no link
    svg = render_svg([m], "M0 0Z")
    assert "<title>AWS us-east-1 (N. Virginia (Ashburn)): major. A &lt;b&gt;bad&lt;/b&gt; day</title>" in svg


def test_your_region_tag_only_when_filter_active_and_mine():
    assert "Your region" in card_html(_marker(mine=True), filter_active=True)
    assert "Your region" not in card_html(_marker(mine=False), filter_active=True)
    assert "Your region" not in card_html(_marker(mine=True), filter_active=False)


def test_page_contains_rules_and_still_no_script(conn, tmp_path):
    for name in ("aws", "gcp", "azure", "github", "databricks", "cloudflare", "claude", "npm", "docker"):
        db.record_poll(conn, name, NOW - timedelta(minutes=1), None)
    db.upsert_incident(
        conn,
        make_incident(provider="aws", external_id="a", title="Edge trouble", url="https://x.test/a", regions=[Region("aws", "eu-west-2")]),
    )
    ctx = build_context(conn, NOW)
    assert ctx["map_css"].count(":focus-visible)") == len(regions.all_regions())
    html = render(conn, tmp_path / "site", now=NOW).read_text()
    assert html.count(":focus-visible)") == len(regions.all_regions())
    assert html.count("<script") == 1  # ADR-0012's inline script, nothing external
    assert '<div class="card" data-key="aws:eu-west-2"' in html
    assert '<a href="https://x.test/a">Edge trouble</a>' in html
