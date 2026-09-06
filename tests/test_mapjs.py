"""ADR-0012: the pure math in map.js, run under node when it is available."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

MAP_JS = Path(__file__).parent.parent / "statusboard" / "static" / "map.js"
VIEW = {"x": 0, "y": 13.9, "w": 1000, "h": 402.8}

HARNESS = """
const M = require(process.argv[2]);
const view = %s;
const out = {};
out.clampLow = M.clampScale(0.5);
out.clampHigh = M.clampScale(20);
const centre = { x: view.x + view.w / 2, y: view.y + view.h / 2 };
out.zoomCentre = M.zoomAt({ scale: 1, tx: 0, ty: 0 }, 2, centre.x, centre.y, view);
out.panClamped = M.panBy({ scale: 2, tx: 0, ty: 0 }, 99999, 99999, view);
out.panClampedNeg = M.panBy({ scale: 2, tx: 0, ty: 0 }, -99999, -99999, view);
out.fitEurope = M.fitBox({ x: 446, y: 55, w: 167, h: 118 }, view);
out.fitWorld = M.fitBox({ x: 0, y: 13.9, w: 1000, h: 402.8 }, view);
out.wheelNotch = M.wheelFactor(100, 0);
out.wheelNotchOut = M.wheelFactor(-100, 0);
out.wheelTrackpad = M.wheelFactor(3, 0);
out.wheelLines = M.wheelFactor(3, 1);
out.wheelHuge = M.wheelFactor(50000, 0);
out.wheelHugeOut = M.wheelFactor(-50000, 0);
out.cardLeft = M.cardStyle(100, 100, view);
out.cardRight = M.cardStyle(900, 380, view);
process.stdout.write(JSON.stringify(out));
""" % json.dumps(VIEW)


@pytest.fixture(scope="module")
def results(tmp_path_factory):
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    harness = tmp_path_factory.mktemp("mapjs") / "harness.js"
    harness.write_text(HARNESS)
    proc = subprocess.run(
        [node, str(harness), str(MAP_JS)], capture_output=True, text=True, timeout=30
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def _covers(state, view):
    """The transformed map must still cover the whole view box."""
    s, tx, ty = state["scale"], state["tx"], state["ty"]
    left, right = view["x"] * s + tx, (view["x"] + view["w"]) * s + tx
    top, bottom = view["y"] * s + ty, (view["y"] + view["h"]) * s + ty
    return (
        left <= view["x"] + 1e-6
        and right >= view["x"] + view["w"] - 1e-6
        and top <= view["y"] + 1e-6
        and bottom >= view["y"] + view["h"] - 1e-6
    )


def test_clamp_scale(results):
    assert results["clampLow"] == 1
    assert results["clampHigh"] == 8


def test_zoom_at_centre_doubles_scale_and_keeps_centre(results):
    st = results["zoomCentre"]
    assert st["scale"] == 2
    cx, cy = VIEW["x"] + VIEW["w"] / 2, VIEW["y"] + VIEW["h"] / 2
    assert abs(cx * st["scale"] + st["tx"] - cx) < 1e-6
    assert abs(cy * st["scale"] + st["ty"] - cy) < 1e-6
    assert _covers(st, VIEW)


def test_pan_is_clamped_to_the_map_edge(results):
    assert _covers(results["panClamped"], VIEW)
    assert _covers(results["panClampedNeg"], VIEW)
    assert results["panClamped"]["tx"] == 0  # cannot pan past the left edge at all
    assert results["panClampedNeg"]["tx"] == -1000  # right edge at scale 2


def test_fit_box_frames_europe(results):
    st = results["fitEurope"]
    assert st["scale"] > 1
    assert _covers(st, VIEW)
    # Both box corners land inside the view.
    for x, y in ((446, 55), (446 + 167, 55 + 118)):
        sx, sy = x * st["scale"] + st["tx"], y * st["scale"] + st["ty"]
        assert VIEW["x"] <= sx <= VIEW["x"] + VIEW["w"]
        assert VIEW["y"] <= sy <= VIEW["y"] + VIEW["h"]
    assert results["fitWorld"] == {"scale": 1, "tx": 0, "ty": 0}


def test_wheel_factor_is_proportional_and_clamped(results):
    # Positive deltaY scrolls down, which zooms out, so the factor is below 1.
    assert 0.85 < results["wheelNotch"] < 0.88
    assert 1.14 < results["wheelNotchOut"] < 1.16
    assert abs(results["wheelNotch"] * results["wheelNotchOut"] - 1) < 1e-9
    # A 3 px trackpad tick barely moves; 30 of them add up to about one notch.
    assert 0.99 < results["wheelTrackpad"] < 1.0
    assert abs(results["wheelTrackpad"] ** 33 - results["wheelNotch"]) < 0.01
    # Line mode is 16 px per line.
    assert abs(results["wheelLines"] - results["wheelTrackpad"] ** 16) < 1e-9
    # A wild delta is capped to one step of 1.5x either way.
    assert abs(results["wheelHuge"] - 1 / 1.5) < 1e-9
    assert results["wheelHugeOut"] == 1.5


def test_card_style_matches_python_rules(results):
    assert results["cardLeft"] == {"left": "10.4%", "top": "18.9%"}
    assert results["cardRight"] == {"right": "10.4%", "bottom": "6.6%"}
