"""Build the dashboard context from SQLite and write one self-contained HTML page."""

import sqlite3
from datetime import datetime, timedelta, timezone
from importlib import resources
from pathlib import Path

from jinja2 import Environment, PackageLoader, select_autoescape

from statusboard import db, icon, regions
from statusboard.config import Config, load_config
from statusboard.mapgen import hover_css, land_path, marker_layout, render_svg
from statusboard.model import Incident
from statusboard.providers import PROVIDERS

# Tile groups, in display order, with default labels. Statuspage providers also
# carry a label on the object; that wins when present. Every registered provider
# must appear in exactly one group; tests/test_groups.py enforces it.
GROUPS: list[tuple[str, list[tuple[str, str]]]] = [
    ("Clouds", [("aws", "AWS"), ("gcp", "GCP"), ("azure", "Azure")]),
    ("Data platforms", [("databricks", "Databricks"), ("dbt", "dbt Cloud")]),
    ("AI", [("claude", "Claude"), ("openai", "OpenAI")]),
    ("Developer tooling", [("github", "GitHub"), ("cloudflare", "Cloudflare"), ("npm", "npm"), ("docker", "Docker"), ("pypi", "PyPI")]),
    ("Workplace", [("google-workspace", "Google Workspace"), ("slack", "Slack"), ("atlassian", "Atlassian")]),
]
PROVIDER_ORDER: list[tuple[str, str]] = [pair for _, pairs in GROUPS for pair in pairs]

CLOUD_PROVIDERS = ("aws", "gcp", "azure")
# Providers whose incidents carry regions, so the filter can split them.
REGIONAL_PROVIDERS = ("aws", "gcp", "azure", "databricks")

SOURCE_URLS: dict[str, str] = {
    "aws": "https://health.aws.amazon.com/health/status",
    "gcp": "https://status.cloud.google.com/",
    "azure": "https://azure.status.microsoft/en-us/status/",
    "github": "https://www.githubstatus.com/",
    "databricks": "https://status.databricks.com/",
    "cloudflare": "https://www.cloudflarestatus.com/",
    "claude": "https://status.claude.com/",
    "npm": "https://status.npmjs.org/",
    "docker": "https://www.dockerstatus.com/",
    "google-workspace": "https://www.google.com/appsstatus/dashboard/",
    "slack": "https://slack-status.com/",
    "dbt": "https://status.getdbt.com/",
    "openai": "https://status.openai.com/",
    "atlassian": "https://status.atlassian.com/",
    "pypi": "https://status.python.org/",
}

STALE_AFTER = timedelta(minutes=15)
RESOLVED_WINDOW = timedelta(days=7)
MESSAGE_PREVIEW = 240
SEVERITY_RANK = {"minor": 1, "major": 2, "critical": 3}


def _label(name: str, default: str) -> str:
    return getattr(PROVIDERS.get(name), "label", None) or default


def _worst(severities: list[str]) -> str:
    if not severities:
        return "ok"
    return max(severities, key=lambda s: SEVERITY_RANK[s])


def _ago(then: datetime, now: datetime) -> str:
    seconds = int((now - then).total_seconds())
    if seconds < 60:
        return "just now"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} min ago"
    hours = minutes // 60
    if hours < 48:
        return f"{hours} h ago"
    return f"{hours // 24} d ago"


def _incident_dict(inc: Incident, labels: dict[str, str]) -> dict:
    message = inc.last_message or ""
    preview = message if len(message) <= MESSAGE_PREVIEW else message[: MESSAGE_PREVIEW - 1].rstrip() + "…"
    return {
        "provider": inc.provider,
        "provider_label": labels.get(inc.provider, inc.provider),
        "severity": inc.severity,
        "title": inc.title,
        "url": inc.url,
        "started_at": db.to_iso(inc.started_at),
        "updated_at": db.to_iso(inc.updated_at),
        "resolved_at": db.to_iso(inc.resolved_at) if inc.resolved_at else None,
        "last_message": preview,
        "last_message_full": message,
        "region_labels": [f"{r.cloud} {r.code}" for r in inc.regions],
    }


def _on_map(inc: Incident) -> bool:
    return any(regions.lookup(r.cloud, r.code) is not None for r in inc.regions)


def is_mine(inc: Incident, config: Config) -> bool:
    """Global incidents and incidents with no mappable region are always mine."""
    if not config.active or not _on_map(inc):
        return True
    return any((r.cloud, r.code) in config.my_regions for r in inc.regions)


def _open_sort_key(inc: Incident):
    return (-SEVERITY_RANK[inc.severity], -inc.updated_at.timestamp())


def group_level(levels: list[str]) -> str:
    """Worst incident level wins. Stale only when every member is stale. Else ok."""
    incident_levels = [lv for lv in levels if lv in SEVERITY_RANK]
    if incident_levels:
        return max(incident_levels, key=lambda lv: SEVERITY_RANK[lv])
    if levels and all(lv == "stale" for lv in levels):
        return "stale"
    return "ok"


def build_groups(providers: list[dict]) -> list[dict]:
    by_name = {p["name"]: p for p in providers}
    groups = []
    for label, pairs in GROUPS:
        members = [by_name[name] for name, _ in pairs if name in by_name]
        if not members:
            continue
        groups.append(
            {
                "label": label,
                "level": group_level([m["level"] for m in members]),
                "open_count": sum(m["open_count"] for m in members),
                "has_regions": any(m["has_regions"] for m in members),
                "providers": members,
            }
        )
    return groups


def build_context(conn: sqlite3.Connection, now: datetime) -> dict:
    config = load_config()
    labels = {name: _label(name, default) for name, default in PROVIDER_ORDER}
    open_incidents = sorted(db.open_incidents(conn), key=_open_sort_key)
    resolved = db.recent_resolved(conn, now - RESOLVED_WINDOW)
    polls = db.last_polls(conn)

    open_mine = [i for i in open_incidents if is_mine(i, config)]
    open_elsewhere = [i for i in open_incidents if not is_mine(i, config)]
    resolved_mine = [i for i in resolved if is_mine(i, config)]
    resolved_elsewhere = [i for i in resolved if not is_mine(i, config)]

    providers = []
    for name, _default in PROVIDER_ORDER:
        mine = [i for i in open_mine if i.provider == name]
        elsewhere = [i for i in open_elsewhere if i.provider == name]
        level = _worst([i.severity for i in mine])
        poll = polls.get(name)
        polled_at, poll_error, polled_ago = None, None, None
        if poll is None:
            level = "stale"
        else:
            polled_at_dt, poll_error = poll
            polled_at = db.to_iso(polled_at_dt)
            polled_ago = _ago(polled_at_dt, now)
            if poll_error is not None or now - polled_at_dt > STALE_AFTER:
                level = "stale"
        providers.append(
            {
                "name": name,
                "label": labels[name],
                "level": level,
                "open_count": len(mine),
                "elsewhere_count": len(elsewhere),
                "has_regions": name in REGIONAL_PROVIDERS,
                "polled_at": polled_at,
                "polled_ago": polled_ago,
                "poll_error": poll_error,
                "source_url": SOURCE_URLS[name],
            }
        )

    stale_clouds = {p["name"] for p in providers if p["level"] == "stale" and p["name"] in CLOUD_PROVIDERS}
    open_dicts = [_incident_dict(i, labels) for i in open_incidents]
    map_svg, map_css = build_map(open_incidents, stale_clouds, config, labels)
    return {
        "generated_at": db.to_iso(now),
        "providers": providers,
        "groups": build_groups(providers),
        "filter_active": config.active,
        "my_region_labels": sorted(f"{cloud} {code}" for cloud, code in config.my_regions),
        "all_clear": not open_mine,
        "open": [_incident_dict(i, labels) for i in open_mine],
        "open_elsewhere": [_incident_dict(i, labels) for i in open_elsewhere],
        "resolved": [_incident_dict(i, labels) for i in resolved_mine],
        "resolved_elsewhere": [_incident_dict(i, labels) for i in resolved_elsewhere],
        "map_svg": map_svg,
        "map_css": map_css,
        "map_js": map_js(),
        "favicon_svg": icon.svg_data_uri(),
        "favicon_png": icon.png_data_uri(),
        "global_incidents": [d for d, i in zip(open_dicts, open_incidents) if not _on_map(i)],
    }


def build_map(
    open_incidents: list[Incident],
    stale_clouds: set[str],
    config: Config = Config(frozenset()),
    labels: dict[str, str] | None = None,
) -> tuple[str, str]:
    """Returns (svg, css). Open incidents are expected newest first, so cards list them that way."""
    labels = labels or {}
    levels: dict[tuple[str, str], str] = {}
    titles: dict[tuple[str, str], list[str]] = {}
    incidents: dict[tuple[str, str], list[dict]] = {}
    for inc in open_incidents:
        for r in inc.regions:
            key = (r.cloud, r.code)
            current = levels.get(key, "ok")
            if SEVERITY_RANK[inc.severity] > SEVERITY_RANK.get(current, 0):
                levels[key] = inc.severity
            titles.setdefault(key, []).append(inc.title)
            incidents.setdefault(key, []).append(
                {
                    "title": inc.title,
                    "url": inc.url,
                    "severity": inc.severity,
                    "provider_label": labels.get(inc.provider, inc.provider),
                }
            )
    markers = marker_layout(regions.all_regions(), levels, titles, stale_clouds, config.my_regions, incidents)
    return render_svg(markers, land_path(), filter_active=config.active), hover_css(markers)


def build_map_svg(open_incidents: list[Incident], stale_clouds: set[str], config: Config = Config(frozenset())) -> str:
    return build_map(open_incidents, stale_clouds, config)[0]


def map_js() -> str:
    """The pan and zoom script, inlined into the page so it makes no request."""
    return resources.files("statusboard").joinpath("static/map.js").read_text(encoding="utf-8")


def _format_ts(value: str | None) -> str:
    if not value:
        return ""
    return db.from_iso(value).strftime("%Y-%m-%d %H:%M UTC")


def environment() -> Environment:
    env = Environment(
        loader=PackageLoader("statusboard", "templates"),
        autoescape=select_autoescape(default=True),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["ts"] = _format_ts
    return env


def render(conn: sqlite3.Connection, out_dir: str | Path, now: datetime | None = None) -> Path:
    now = now or datetime.now(timezone.utc)
    context = build_context(conn, now)
    html = environment().get_template("index.html.j2").render(**context)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    target = out / "index.html"
    target.write_text(html, encoding="utf-8")
    # Browsers ask for /favicon.ico on their own. The page links inline data
    # URIs, but writing the file too keeps a plain directory serve free of 404s.
    (out / "favicon.ico").write_bytes(icon.ico_icon())
    return target
