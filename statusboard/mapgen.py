"""World map as inline SVG: equirectangular projection, land path, region markers."""

import html
import json
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path

from statusboard.regions import RegionInfo

WIDTH = 1000
HEIGHT = 500
LAT_MAX = 85.0   # crop the empty Arctic
LAT_MIN = -60.0  # crop Antarctica
RADIUS_MINE = 6
RADIUS_OTHER = 4

# Three clouds share many cities. Offset each cloud so markers stay distinct.
OFFSETS: dict[str, tuple[int, int]] = {"aws": (0, 0), "gcp": (7, 5), "azure": (-7, 5)}
CLOUD_LABELS: dict[str, str] = {"aws": "AWS", "gcp": "GCP", "azure": "Azure"}

LEVEL_RANK: dict[str, int] = {"ok": 0, "stale": 0, "minor": 1, "major": 2, "critical": 3}

GEOJSON_NAME = "world-110m.geojson"
LAND_PATH_NAME = "world-land.svgpath"


def project(lon: float, lat: float, width: int = WIDTH, height: int = HEIGHT) -> tuple[float, float]:
    return (lon + 180.0) / 360.0 * width, (90.0 - lat) / 180.0 * height


def _ring_to_path(ring: list, width: int, height: int) -> str:
    parts = []
    for index, (lon, lat) in enumerate(ring):
        x, y = project(lon, lat, width, height)
        parts.append(f"{'M' if index == 0 else 'L'}{x:.1f} {y:.1f}")
    parts.append("Z")
    return "".join(parts)


def geojson_to_path(geojson: dict, width: int = WIDTH, height: int = HEIGHT) -> str:
    """One SVG path string covering every Polygon and MultiPolygon in the file."""
    pieces = []
    for feature in geojson.get("features", []):
        geometry = feature.get("geometry") or {}
        kind = geometry.get("type")
        coords = geometry.get("coordinates") or []
        polygons = [coords] if kind == "Polygon" else coords if kind == "MultiPolygon" else []
        for polygon in polygons:
            for ring in polygon:
                pieces.append(_ring_to_path(ring, width, height))
    return "".join(pieces)


def _data(name: str):
    return resources.files("statusboard").joinpath(f"data/{name}")


def write_land_path(out: str | Path | None = None) -> Path:
    """Generate world-land.svgpath from the vendored GeoJSON. Run once via make world-svg."""
    with _data(GEOJSON_NAME).open(encoding="utf-8") as handle:
        geojson = json.load(handle)
    target = Path(out) if out else Path(str(_data(LAND_PATH_NAME)))
    target.write_text(geojson_to_path(geojson), encoding="utf-8")
    return target


def land_path() -> str:
    return _data(LAND_PATH_NAME).read_text(encoding="utf-8")


@dataclass
class Marker:
    cloud: str
    code: str
    name: str
    x: float
    y: float
    level: str
    titles: list[str] = field(default_factory=list)
    mine: bool = True

    @property
    def tooltip(self) -> str:
        text = f"{CLOUD_LABELS.get(self.cloud, self.cloud)} {self.code} ({self.name}): {self.level}"
        if self.titles:
            text += ". " + "; ".join(self.titles[:3])
        return text


def marker_layout(
    regions: list[RegionInfo],
    levels: dict[tuple[str, str], str],
    titles: dict[tuple[str, str], list[str]] | None = None,
    stale_clouds: set[str] | frozenset[str] = frozenset(),
    my_regions: set[tuple[str, str]] | frozenset[tuple[str, str]] = frozenset(),
) -> list[Marker]:
    """One marker per region row.

    Draw order: markers with an incident come last so they sit on top, and among
    those, mine after elsewhere. An empty my_regions means every marker is mine.
    """
    titles = titles or {}
    markers = []
    for region in regions:
        key = (region.cloud, region.code)
        level = levels.get(key, "ok")
        if level == "ok" and region.cloud in stale_clouds:
            level = "stale"
        x, y = project(region.lon, region.lat)
        dx, dy = OFFSETS.get(region.cloud, (0, 0))
        mine = not my_regions or key in my_regions
        markers.append(
            Marker(region.cloud, region.code, region.name, x + dx, y + dy, level, list(titles.get(key, [])), mine)
        )
    markers.sort(key=lambda m: (LEVEL_RANK.get(m.level, 0), m.mine))
    return markers


def render_svg(markers: list[Marker], land: str, width: int = WIDTH, height: int = HEIGHT) -> str:
    top = project(0, LAT_MAX, width, height)[1]
    bottom = project(0, LAT_MIN, width, height)[1]
    parts = [
        f'<svg class="map" viewBox="0 {top:.1f} {width} {bottom - top:.1f}" width="100%" '
        'preserveAspectRatio="xMidYMid meet" role="img" aria-label="World map of cloud region status">',
        f'<path class="land" d="{land}"/>',
    ]
    for m in markers:
        classes = f"marker marker-{m.level}" + ("" if m.mine else " marker-other")
        radius = RADIUS_MINE if m.mine else RADIUS_OTHER
        parts.append(
            f'<circle class="{classes}" cx="{m.x:.1f}" cy="{m.y:.1f}" r="{radius}">'
            f"<title>{html.escape(m.tooltip)}</title></circle>"
        )
    parts.append("</svg>")
    return "".join(parts)
