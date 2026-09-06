"""One provider class for every page that serves the Statuspage v2 incidents feed.

Atlassian Statuspage (GitHub, Cloudflare, Claude, npm) and incident.io (Docker)
both answer at /api/v2/incidents.json with the same shape. incident.io omits
started_at and shortlink, so both fall back.
"""

import json
from datetime import datetime

from statusboard import http
from statusboard.model import Incident, Severity
from statusboard.providers import register

# Statuspage "impact" values mapped to our three severities.
IMPACT_TO_SEVERITY: dict[str, Severity] = {
    "none": "minor",
    "minor": "minor",
    "major": "major",
    "critical": "critical",
}


def _parse_ts(text: str) -> datetime:
    return datetime.fromisoformat(text)


class StatuspageProvider:
    lists_resolved = True

    def __init__(self, name: str, host: str, label: str):
        self.name = name
        self.host = host
        self.label = label

    @property
    def feed_url(self) -> str:
        return f"https://{self.host}/api/v2/incidents.json"

    def _to_incident(self, item: dict) -> Incident:
        updates = item.get("incident_updates") or []
        # incident_updates is newest first on both Statuspage and incident.io.
        last_message = updates[0].get("body", "") if updates else ""
        resolved = item.get("resolved_at")
        started = item.get("started_at") or item["created_at"]
        url = item.get("shortlink") or f"https://{self.host}/incidents/{item['id']}"
        return Incident(
            provider=self.name,
            external_id=item["id"],
            title=item["name"],
            severity=IMPACT_TO_SEVERITY.get(item.get("impact", ""), "major"),
            started_at=_parse_ts(started),
            updated_at=_parse_ts(item["updated_at"]),
            resolved_at=_parse_ts(resolved) if resolved else None,
            url=url,
            last_message=last_message or "",
            regions=[],
        )

    def fetch(self) -> list[Incident]:
        payload = json.loads(http.fetch_bytes(self.feed_url))
        return [self._to_incident(item) for item in payload.get("incidents", [])]


STATUSPAGE_PROVIDERS = [
    StatuspageProvider("github", "www.githubstatus.com", "GitHub"),
    StatuspageProvider("cloudflare", "www.cloudflarestatus.com", "Cloudflare"),
    StatuspageProvider("claude", "status.claude.com", "Claude"),
    StatuspageProvider("npm", "status.npmjs.org", "npm"),
    StatuspageProvider("docker", "www.dockerstatus.com", "Docker"),
    # ADR-0017. dbt and OpenAI run on incident.io and use the two fallbacks.
    StatuspageProvider("dbt", "status.getdbt.com", "dbt Cloud"),
    StatuspageProvider("openai", "status.openai.com", "OpenAI"),
    StatuspageProvider("atlassian", "status.atlassian.com", "Atlassian"),
    StatuspageProvider("pypi", "status.python.org", "PyPI"),
]

for _provider in STATUSPAGE_PROVIDERS:
    register(_provider)
