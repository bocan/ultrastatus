from datetime import timedelta

import json
import re

from statusboard import db, regions
from statusboard.mapgen import (
    Marker,
    geojson_to_path,
    land_path,
    marker_layout,
    preset_boxes,
    project,
    render_svg,
)
from statusboard.model import Region
from statusboard.render import build_context

from conftest import make_incident, utc

NOW = utc(2026, 9, 5, 20, 10, 0)


def test_project_corners_and_origin():
    assert project(0, 0, 1000, 500) == (500.0, 250.0)
    assert project(-180, 90, 1000, 500) == (0.0, 0.0)
    assert project(180, -90, 1000, 500) == (1000.0, 500.0)


def test_geojson_to_path_counts_rings():
    geojson = {
        "features": [
            {
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[0, 0], [10, 0], [10, 10], [0, 0]]],
                }
            },
            {
                "geometry": {
                    "type": "MultiPolygon",
                    "coordinates": [
                        [[[20, 20], [30, 20], [30, 30], [20, 20]]],
                        [
                            [[40, 40], [50, 40], [50, 50], [40, 40]],
                            [[42, 42], [44, 42], [44, 44], [42, 42]],
                        ],
                    ],
                }
            },
            {"geometry": {"type": "Point", "coordinates": [1, 1]}},
        ]
    }
    path = geojson_to_path(geojson, 1000, 500)
    assert path.count("M") == 4
    assert path.count("Z") == 4
    assert path.startswith("M500.0 250.0L")


def test_land_path_is_generated_and_within_budget():
    land = land_path()
    assert land.startswith("M")
    assert land.endswith("Z")
    assert (
        len(land.encode()) < 1_300_000
    )  # ADR-0012: 1:50m coastline, page budget 1.5 MB


# ADR-0012: viewport group, labels, presets.

CONTINENT_SAMPLES = {
    "north-america": [
        "us-east-1",
        "us-west-2",
        "ca-central-1",
        "mx-central-1",
        "us-central1",
        "westus3",
        "canadaeast",
    ],
    "south-america": ["sa-east-1", "southamerica-west1", "brazilsouth", "chilecentral"],
    "europe": [
        "eu-west-1",
        "eu-north-1",
        "eu-south-2",
        "europe-north1",
        "europe-west12",
        "uksouth",
        "norwaywest",
        "polandcentral",
    ],
    "middle-east-africa": [
        "af-south-1",
        "me-central-1",
        "il-central-1",
        "africa-south1",
        "qatarcentral",
        "southafricawest",
    ],
    "asia": [
        "ap-south-1",
        "ap-northeast-1",
        "ap-southeast-3",
        "asia-east1",
        "asia-south2",
        "japanwest",
        "indonesiacentral",
        "jioindiawest",
    ],
    "oceania": [
        "ap-southeast-2",
        "ap-southeast-4",
        "ap-southeast-6",
        "australia-southeast1",
        "newzealandnorth",
        "australiacentral",
    ],
}


def _markers_by_code():
    return {m.code: m for m in marker_layout(regions.all_regions(), {})}


def _inside(m, box):
    x, y, w, h = box
    return x <= m.x <= x + w and y <= m.y <= y + h


def test_viewport_group_wraps_land_and_markers():
    svg = render_svg(marker_layout(regions.all_regions(), {}), "M0 0Z")
    assert svg.count('<g class="viewport">') == 1
    assert (
        svg.find('<g class="viewport">')
        < svg.find("<path")
        < svg.find("<circle")
        < svg.find("</g>")
        < svg.find("<foreignObject")
    )
    assert 'tabindex="0" data-presets="' in svg


def test_label_follows_each_circle_with_the_region_code():
    markers = marker_layout(regions.all_regions(), {})
    svg = render_svg(markers, "M0 0Z")
    labels = re.findall(
        r'<text class="label"[^>]* x="[\d.]+" y="[\d.]+">([^<]+)</text>', svg
    )
    assert labels == [m.code for m in markers]
    assert svg.count("<text") == svg.count("<circle")


def test_preset_boxes_have_all_keys_and_contain_their_markers():
    boxes = preset_boxes(marker_layout(regions.all_regions(), {}))
    assert set(boxes) == {
        "world",
        "north-america",
        "south-america",
        "europe",
        "middle-east-africa",
        "asia",
        "oceania",
        "mine",
    }
    by_code = _markers_by_code()
    for name, codes in CONTINENT_SAMPLES.items():
        for code in codes:
            assert _inside(by_code[code], boxes[name]), f"{code} outside {name}"
    x, y, w, h = boxes["world"]
    assert (x, w) == (0.0, 1000.0) and round(y, 1) == 13.9 and round(h, 1) == 402.8
    for box in boxes.values():
        assert (
            box[0] >= 0
            and box[0] + box[2] <= 1000
            and box[1] >= 13.9
            and box[1] + box[3] <= 416.7 + 0.05
        )


def test_mine_preset_frames_mine_markers_with_margin():
    markers = marker_layout(
        regions.all_regions(),
        {},
        my_regions={("aws", "eu-west-2"), ("aws", "ap-southeast-2")},
    )
    boxes = preset_boxes(markers, filter_active=True)
    mine = [m for m in markers if m.mine]
    assert all(_inside(m, boxes["mine"]) for m in mine)
    assert boxes["mine"][2] > 0 and boxes["mine"][3] > 0

    single = marker_layout(regions.all_regions(), {}, my_regions={("aws", "eu-west-2")})
    box = preset_boxes(single, filter_active=True)["mine"]
    assert box[2] == 80 and box[3] == 80

    assert preset_boxes(markers, filter_active=False)["mine"] == boxes["world"]


def test_svg_data_presets_round_trips():
    markers = marker_layout(regions.all_regions(), {})
    svg = render_svg(markers, "M0 0Z")
    raw = re.search(r'data-presets="([^"]+)"', svg).group(1)
    parsed = json.loads(raw.replace("&quot;", '"'))
    assert {k: tuple(v) for k, v in parsed.items()} == preset_boxes(markers)


def test_marker_layout_defaults_to_ok_per_region():
    rows = regions.all_regions()
    markers = marker_layout(rows, {})
    assert len(markers) == len(rows)
    assert all(m.level == "ok" for m in markers)
    assert {(m.cloud, m.code) for m in markers} == {(r.cloud, r.code) for r in rows}


def test_marker_layout_applies_level_and_offsets():
    rows = [
        r
        for r in regions.all_regions()
        if (r.cloud, r.code) in {("aws", "us-east-1"), ("gcp", "us-east4")}
    ]
    markers = {
        (m.cloud, m.code): m
        for m in marker_layout(rows, {("aws", "us-east-1"): "critical"})
    }
    aws, gcp = markers[("aws", "us-east-1")], markers[("gcp", "us-east4")]
    assert aws.level == "critical"
    assert gcp.level == "ok"
    # Same city, so gcp sits at the fixed offset from aws.
    assert (round(gcp.x - aws.x), round(gcp.y - aws.y)) == (7, 5)


def test_incident_markers_draw_last():
    rows = regions.all_regions()
    markers = marker_layout(rows, {("azure", "uksouth"): "minor"})
    assert markers[-1].code == "uksouth"
    assert all(m.level in ("ok", "stale") for m in markers[:-1])


def test_stale_cloud_greys_only_ok_markers():
    rows = [r for r in regions.all_regions() if r.cloud == "gcp"][:5]
    key = (rows[0].cloud, rows[0].code)
    markers = marker_layout(rows, {key: "major"}, stale_clouds={"gcp"})
    by_key = {(m.cloud, m.code): m.level for m in markers}
    assert by_key[key] == "major"
    assert all(level == "stale" for k, level in by_key.items() if k != key)


def test_all_markers_mine_when_filter_empty():
    markers = marker_layout(regions.all_regions(), {}, my_regions=frozenset())
    assert all(m.mine for m in markers)
    svg = render_svg(markers, "M0 0Z")
    assert "marker-other" not in svg
    assert 'r="6"' in svg and 'r="4"' not in svg


def test_only_my_marker_is_large_and_bright():
    rows = regions.all_regions()
    markers = marker_layout(rows, {}, my_regions={("aws", "eu-west-2")})
    mine = [m for m in markers if m.mine]
    assert [(m.cloud, m.code) for m in mine] == [("aws", "eu-west-2")]
    svg = render_svg(markers, "M0 0Z")
    assert svg.count("marker-other") == len(rows) - 1
    assert svg.count('r="6"') == 1
    assert svg.count('r="4"') == len(rows) - 1


def test_elsewhere_incident_draws_before_my_incident():
    rows = regions.all_regions()
    levels = {("aws", "us-east-1"): "major", ("aws", "eu-west-2"): "major"}
    markers = marker_layout(rows, levels, my_regions={("aws", "eu-west-2")})
    assert markers[-1].code == "eu-west-2"
    assert markers[-2].code == "us-east-1"


def test_render_svg_shape_and_tooltip():
    markers = [
        Marker(
            "aws",
            "us-east-1",
            "N. Virginia (Ashburn)",
            284.7,
            141.7,
            "critical",
            ["A <b>bad</b> day", "Two", "Three", "Four"],
        ),
        Marker("gcp", "us-central1", "Iowa", 233.6, 135.3, "ok"),
    ]
    svg = render_svg(markers, "M0 0L1 1Z")
    assert svg.startswith("<svg")
    assert svg.count("<path") == 1
    assert svg.count("<circle") == 2
    assert (
        "<title>AWS us-east-1 (N. Virginia (Ashburn)): critical. A &lt;b&gt;bad&lt;/b&gt; day; Two; Three</title>"
        in svg
    )
    assert "Four" not in svg
    assert 'viewBox="0 13.9 1000 402.8"' in svg


def test_build_context_includes_map_and_global_incidents(conn):
    for name in (
        "aws",
        "gcp",
        "azure",
        "github",
        "databricks",
        "cloudflare",
        "claude",
        "npm",
        "docker",
    ):
        db.record_poll(conn, name, NOW - timedelta(minutes=1), None)
    db.upsert_incident(
        conn,
        make_incident(
            provider="aws", external_id="r", regions=[Region("aws", "eu-west-2")]
        ),
    )
    db.upsert_incident(
        conn,
        make_incident(
            provider="github", external_id="g", title="Global thing", regions=[]
        ),
    )
    db.upsert_incident(
        conn,
        make_incident(
            provider="gcp",
            external_id="x",
            title="Only global loc",
            regions=[Region("gcp", "global")],
        ),
    )

    ctx = build_context(conn, NOW)
    assert ctx["map_svg"].startswith("<svg")
    assert "London): major. Something broke" in ctx["map_svg"]
    assert {g["title"] for g in ctx["global_incidents"]} == {
        "Global thing",
        "Only global loc",
    }
