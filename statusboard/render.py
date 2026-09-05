"""Build the dashboard context from SQLite and write one self-contained HTML page."""

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from jinja2 import Environment, PackageLoader, select_autoescape

from statusboard import db, regions
from statusboard.mapgen import land_path, marker_layout, render_svg
from statusboard.model import Incident
from statusboard.providers import PROVIDERS

# Fixed tile order and default labels. Statuspage providers also carry a label
# on the object; that wins when present.
PROVIDER_ORDER: list[tuple[str, str]] = [
    ("aws", "AWS"),
    ("gcp", "GCP"),
    ("azure", "Azure"),
    ("github", "GitHub"),
    ("databricks", "Databricks"),
    ("cloudflare", "Cloudflare"),
    ("claude", "Claude"),
    ("npm", "npm"),
    ("docker", "Docker"),
]

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


def build_context(conn: sqlite3.Connection, now: datetime) -> dict:
    labels = {name: _label(name, default) for name, default in PROVIDER_ORDER}
    open_incidents = db.open_incidents(conn)
    resolved = db.recent_resolved(conn, now - RESOLVED_WINDOW)
    polls = db.last_polls(conn)

    providers = []
    for name, _default in PROVIDER_ORDER:
        mine = [i for i in open_incidents if i.provider == name]
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
                "polled_at": polled_at,
                "polled_ago": polled_ago,
                "poll_error": poll_error,
                "source_url": SOURCE_URLS[name],
            }
        )

    open_dicts = [_incident_dict(i, labels) for i in open_incidents]
    stale_clouds = {p["name"] for p in providers if p["level"] == "stale" and p["name"] in ("aws", "gcp", "azure")}
    return {
        "generated_at": db.to_iso(now),
        "providers": providers,
        "open": open_dicts,
        "resolved": [_incident_dict(i, labels) for i in resolved],
        "map_svg": build_map_svg(open_incidents, stale_clouds),
        "global_incidents": [d for d, i in zip(open_dicts, open_incidents) if not _on_map(i)],
    }


def _on_map(inc: Incident) -> bool:
    return any(regions.lookup(r.cloud, r.code) is not None for r in inc.regions)


def build_map_svg(open_incidents: list[Incident], stale_clouds: set[str]) -> str:
    levels: dict[tuple[str, str], str] = {}
    titles: dict[tuple[str, str], list[str]] = {}
    for inc in open_incidents:
        for r in inc.regions:
            key = (r.cloud, r.code)
            current = levels.get(key, "ok")
            if SEVERITY_RANK[inc.severity] > SEVERITY_RANK.get(current, 0):
                levels[key] = inc.severity
            titles.setdefault(key, []).append(inc.title)
    markers = marker_layout(regions.all_regions(), levels, titles, stale_clouds)
    return render_svg(markers, land_path())


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
    return target
