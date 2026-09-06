"""Google status feeds. One class, two instances: Google Cloud and Google Workspace.

Both publish an incidents.json with the same shape. Workspace lacks the two
affected-location keys, so its incidents carry no regions.
"""

import json
import re
from datetime import datetime

from statusboard import http
from statusboard.model import Incident, Region, Severity
from statusboard.providers import register

MESSAGE_LIMIT = 2000
TITLE_LIMIT = 200

STATUS_IMPACT_TO_SEVERITY: dict[str, Severity] = {
    "SERVICE_INFORMATION": "minor",
    "SERVICE_DISRUPTION": "major",
    "SERVICE_OUTAGE": "critical",
}

# Workspace descriptions open with a markdown heading such as "**Summary:**" or
# "**Summary**" on its own line, then the real sentence.
_SUMMARY_PREFIX = re.compile(r"^\s*\*\*Summary:?\*\*\s*", re.IGNORECASE)


def _parse_ts(text: str) -> datetime:
    return datetime.fromisoformat(text)


def _title(external_desc: str) -> str:
    text = _SUMMARY_PREFIX.sub("", external_desc or "")
    for line in text.splitlines():
        line = line.strip()
        if line:
            return line[:TITLE_LIMIT]
    return ""


def _regions(item: dict) -> list[Region]:
    seen: list[str] = []
    for key in ("currently_affected_locations", "previously_affected_locations"):
        for loc in item.get(key) or []:
            code = loc.get("id")
            if code and code not in seen:
                seen.append(code)
    return [Region("gcp", code) for code in seen]


class GoogleStatusProvider:
    lists_resolved = True

    def __init__(self, name: str, feed_url: str, incident_url_base: str, label: str):
        self.name = name
        self.feed_url = feed_url
        self.incident_url_base = incident_url_base
        self.label = label

    def _to_incident(self, item: dict) -> Incident:
        end = item.get("end")
        recent = item.get("most_recent_update") or {}
        return Incident(
            provider=self.name,
            external_id=item["id"],
            title=_title(item.get("external_desc", "")),
            severity=STATUS_IMPACT_TO_SEVERITY.get(
                item.get("status_impact", ""), "major"
            ),
            started_at=_parse_ts(item["begin"]),
            updated_at=_parse_ts(item["modified"]),
            resolved_at=_parse_ts(end) if end else None,
            url=self.incident_url_base + item["uri"],
            last_message=(recent.get("text") or "")[:MESSAGE_LIMIT],
            regions=_regions(item),
        )

    def fetch(self) -> list[Incident]:
        payload = json.loads(http.fetch_bytes(self.feed_url))
        return [self._to_incident(item) for item in payload]


GOOGLE_PROVIDERS = [
    GoogleStatusProvider(
        "gcp",
        "https://status.cloud.google.com/incidents.json",
        "https://status.cloud.google.com/",
        "GCP",
    ),
    GoogleStatusProvider(
        "google-workspace",
        "https://www.google.com/appsstatus/dashboard/incidents.json",
        "https://www.google.com/appsstatus/dashboard/",
        "Google Workspace",
    ),
]

for _provider in GOOGLE_PROVIDERS:
    register(_provider)
