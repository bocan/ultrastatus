"""World map as inline SVG: equirectangular projection, land path, region markers, hover cards."""

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

# Hover card placement, in canvas units on the cropped canvas.
CARD_WIDTH = 220
CARD_GAP = 8            # marker centre to card edge; overlaps the marker by 2 units
CARD_FLIP_X = 700       # past this, the card opens to the left
CARD_FLIP_Y = 260       # past this many units below the crop top, the card opens upward
CARD_MAX_INCIDENTS = 5


def project(lon: float, lat: float, width: int = WIDTH, height: int = HEIGHT) -> tuple[float, float]:
    return (lon + 180.0) / 360.0 * width, (90.0 - lat) / 180.0 * height


def crop_bounds(width: int = WIDTH, height: int = HEIGHT) -> tuple[float, float]:
    """(top, bottom) canvas y of the visible band."""
    return project(0, LAT_MAX, width, height)[1], project(0, LAT_MIN, width, height)[1]


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
    incidents: list[dict] = field(default_factory=list)   # {title, url, severity, provider_label}

    @property
    def key(self) -> str:
        return f"{self.cloud}:{self.code}"

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
    incidents: dict[tuple[str, str], list[dict]] | None = None,
) -> list[Marker]:
    """One marker per region row.

    Draw order: markers with an incident come last so they sit on top, and among
    those, mine after elsewhere. An empty my_regions means every marker is mine.
    """
    titles = titles or {}
    incidents = incidents or {}
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
            Marker(
                region.cloud, region.code, region.name, x + dx, y + dy, level,
                list(titles.get(key, [])), mine, list(incidents.get(key, [])),
            )
        )
    markers.sort(key=lambda m: (LEVEL_RANK.get(m.level, 0), m.mine))
    return markers


def card_style(m: Marker, width: int = WIDTH, height: int = HEIGHT) -> str:
    """Absolute position for the card, as percentages of the cropped canvas."""
    top, bottom = crop_bounds(width, height)
    band = bottom - top
    if m.x <= CARD_FLIP_X:
        horizontal = f"left: {(m.x + CARD_GAP) / width * 100:.1f}%"
    else:
        horizontal = f"right: {(width - m.x + CARD_GAP) / width * 100:.1f}%"
    if m.y - top <= CARD_FLIP_Y:
        vertical = f"top: {(m.y - 10 - top) / band * 100:.1f}%"
    else:
        vertical = f"bottom: {(bottom - m.y - 10) / band * 100:.1f}%"
    return f"{horizontal}; {vertical}"


def _chip(level: str) -> str:
    return f'<span class="chip level-{html.escape(level)}">{html.escape(level)}</span>'


def card_html(m: Marker, filter_active: bool) -> str:
    e = html.escape
    parts = [
        f'<div class="card" data-key="{e(m.key)}" style="{card_style(m)}">',
        f'<div class="card-head"><b>{e(CLOUD_LABELS.get(m.cloud, m.cloud))} {e(m.code)}</b> '
        f'<span class="muted">{e(m.name)}</span></div>',
        f'<div class="card-tags">{_chip(m.level)}',
    ]
    if filter_active and m.mine:
        parts.append('<span class="mine-tag">Your region</span>')
    parts.append("</div>")
    if m.incidents:
        parts.append("<ul>")
        for inc in m.incidents[:CARD_MAX_INCIDENTS]:
            title = e(inc.get("title", ""))
            url = inc.get("url")
            link = f'<a href="{e(url, quote=True)}">{title}</a>' if url else title
            parts.append(f"<li>{_chip(inc.get('severity', 'major'))} {link}</li>")
        parts.append("</ul>")
        extra = len(m.incidents) - CARD_MAX_INCIDENTS
        if extra > 0:
            parts.append(f'<div class="muted">and {extra} more</div>')
    else:
        parts.append('<div class="muted">No open incidents</div>')
    parts.append("</div>")
    return "".join(parts)


def hover_css(markers: list[Marker]) -> str:
    """One rule per marker: hover or focus on the circle reveals the matching card."""
    rules = []
    for m in markers:
        key = html.escape(m.key, quote=True)
        rules.append(
            f'svg.map:has([data-key="{key}"]:hover) .card[data-key="{key}"],'
            f'svg.map:has([data-key="{key}"]:focus-visible) .card[data-key="{key}"]'
            "{opacity:1;pointer-events:auto;transition-delay:0s}"
        )
    return "\n".join(rules)


def render_svg(
    markers: list[Marker],
    land: str,
    width: int = WIDTH,
    height: int = HEIGHT,
    filter_active: bool = False,
) -> str:
    top, bottom = crop_bounds(width, height)
    parts = [
        f'<svg class="map" viewBox="0 {top:.1f} {width} {bottom - top:.1f}" width="100%" '
        'preserveAspectRatio="xMidYMid meet" role="img" aria-label="World map of cloud region status">',
        f'<path class="land" d="{land}"/>',
    ]
    for m in markers:
        classes = f"marker marker-{m.level}" + ("" if m.mine else " marker-other")
        radius = RADIUS_MINE if m.mine else RADIUS_OTHER
        parts.append(
            f'<circle class="{classes}" data-key="{html.escape(m.key, quote=True)}" tabindex="0" '
            f'cx="{m.x:.1f}" cy="{m.y:.1f}" r="{radius}">'
            f"<title>{html.escape(m.tooltip)}</title></circle>"
        )
    # Cards live in one layer after every marker. SVG has no z-index, so this is
    # the only way a card can sit above markers drawn later than its own.
    parts.append(
        f'<foreignObject class="cards-layer" x="0" y="{top:.1f}" width="{width}" height="{bottom - top:.1f}">'
        '<div xmlns="http://www.w3.org/1999/xhtml" class="cards">'
    )
    for m in markers:
        parts.append(card_html(m, filter_active))
    parts.append("</div></foreignObject></svg>")
    return "".join(parts)
