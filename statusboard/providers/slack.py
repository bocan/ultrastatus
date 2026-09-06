"""Slack provider. Reads Slack's own status API, history endpoint."""

import html
import json
import re
from datetime import datetime

from statusboard import http
from statusboard.model import Incident, Severity
from statusboard.providers import register

# History lists recent incidents with a status field, resolved ones included.
# /current lists only active incidents, so resolved_at would never be set.
FEED_URL = "https://slack-status.com/api/v2.0.0/history"
MESSAGE_LIMIT = 2000

TYPE_TO_SEVERITY: dict[str, Severity] = {
    "outage": "critical",
    "incident": "major",
    "notice": "minor",
}

# Slack's docs list status values ok, active, resolved, scheduled, completed,
# and cancelled. The last three belong to maintenance. Anything terminal is
# treated as resolved; active and scheduled stay open.
TERMINAL_STATUSES = {"resolved", "completed", "cancelled", "ok"}

_TAGS = re.compile(r"<[^>]+>")
_WHITESPACE = re.compile(r"\s+")


def _parse_ts(text: str) -> datetime:
    return datetime.fromisoformat(text)


def _strip_html(text: str) -> str:
    return _WHITESPACE.sub(" ", html.unescape(_TAGS.sub(" ", text or ""))).strip()


def _newest_note(notes: list[dict]) -> dict | None:
    """The live feed looked oldest first. Do not rely on it; pick by date_created."""
    dated = [n for n in notes if n.get("date_created")]
    if not dated:
        return notes[-1] if notes else None
    return max(dated, key=lambda n: n["date_created"])


def _to_incident(item: dict) -> Incident:
    updated_at = _parse_ts(item["date_updated"])
    newest = _newest_note(item.get("notes") or [])
    message = _strip_html(newest.get("body", "")) if newest else ""
    services = [s for s in item.get("services") or [] if s]
    if services:
        message = f"Services: {', '.join(services)}. {message}".strip()
    return Incident(
        provider="slack",
        external_id=str(item["id"]),
        title=item["title"],
        severity=TYPE_TO_SEVERITY.get(str(item.get("type", "")).lower(), "major"),
        started_at=_parse_ts(item["date_created"]),
        updated_at=updated_at,
        resolved_at=updated_at
        if str(item.get("status", "")).lower() in TERMINAL_STATUSES
        else None,
        url=item.get("url"),
        last_message=message[:MESSAGE_LIMIT],
        regions=[],
    )


class SlackProvider:
    name = "slack"
    lists_resolved = True
    label = "Slack"

    def fetch(self) -> list[Incident]:
        payload = json.loads(http.fetch_bytes(FEED_URL))
        return [_to_incident(item) for item in payload]


register(SlackProvider())
