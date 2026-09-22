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

# Workspace descriptions open with a bold markdown heading, then the real
# sentence. The live feed writes the heading many ways: "**Summary**",
# "**Summary:**", "**Title:**", "**Title :**", "**Title** : text",
# "**Title:** text", or "**Description**". Match a short bold run that is the
# whole line or is followed by a colon, so bold emphasis inside a real sentence
# ("**Gmail** is down") is left alone.
_BOLD_HEADING = re.compile(r"^\s*\*\*\s*[^*\n]{1,40}?\s*(:\s*)?\*\*\s*(:\s*)?")


def _parse_ts(text: str) -> datetime:
    return datetime.fromisoformat(text)


def _strip_heading(line: str) -> str:
    match = _BOLD_HEADING.match(line)
    if not match:
        return line.strip()
    rest = line[match.end() :].strip()
    if not rest or match.group(1) or match.group(2):
        return rest
    return line.strip()


def _title(external_desc: str) -> str:
    for line in (external_desc or "").splitlines():
        line = _strip_heading(line)
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
