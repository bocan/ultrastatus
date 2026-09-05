"""GitHub provider. Reads the Atlassian Statuspage incidents feed."""

import json
from datetime import datetime

from statusboard import http
from statusboard.model import Incident, Severity
from statusboard.providers import register

FEED_URL = "https://www.githubstatus.com/api/v2/incidents.json"

# Statuspage "impact" values mapped to our three severities.
IMPACT_TO_SEVERITY: dict[str, Severity] = {
    "none": "minor",
    "minor": "minor",
    "major": "major",
    "critical": "critical",
}


def _parse_ts(text: str) -> datetime:
    return datetime.fromisoformat(text)


def _to_incident(item: dict) -> Incident:
    updates = item.get("incident_updates") or []
    # Statuspage lists incident_updates newest first.
    last_message = updates[0].get("body", "") if updates else ""
    resolved = item.get("resolved_at")
    return Incident(
        provider="github",
        external_id=item["id"],
        title=item["name"],
        severity=IMPACT_TO_SEVERITY.get(item.get("impact", ""), "major"),
        started_at=_parse_ts(item["started_at"]),
        updated_at=_parse_ts(item["updated_at"]),
        resolved_at=_parse_ts(resolved) if resolved else None,
        url=item.get("shortlink"),
        last_message=last_message or "",
        regions=[],
    )


class GitHubProvider:
    name = "github"
    lists_resolved = True

    def fetch(self) -> list[Incident]:
        payload = json.loads(http.fetch_bytes(FEED_URL))
        return [_to_incident(item) for item in payload.get("incidents", [])]


register(GitHubProvider())
