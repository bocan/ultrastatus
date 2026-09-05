"""Google Cloud provider. Reads the public incidents.json feed."""

import json
from datetime import datetime

from statusboard import http
from statusboard.model import Incident, Region, Severity
from statusboard.providers import register

FEED_URL = "https://status.cloud.google.com/incidents.json"
INCIDENT_URL_BASE = "https://status.cloud.google.com/"
MESSAGE_LIMIT = 2000

STATUS_IMPACT_TO_SEVERITY: dict[str, Severity] = {
    "SERVICE_INFORMATION": "minor",
    "SERVICE_DISRUPTION": "major",
    "SERVICE_OUTAGE": "critical",
}


def _parse_ts(text: str) -> datetime:
    return datetime.fromisoformat(text)


def _regions(item: dict) -> list[Region]:
    seen: list[str] = []
    for key in ("currently_affected_locations", "previously_affected_locations"):
        for loc in item.get(key) or []:
            code = loc.get("id")
            if code and code not in seen:
                seen.append(code)
    return [Region("gcp", code) for code in seen]


def _to_incident(item: dict) -> Incident:
    end = item.get("end")
    recent = item.get("most_recent_update") or {}
    return Incident(
        provider="gcp",
        external_id=item["id"],
        title=item["external_desc"],
        severity=STATUS_IMPACT_TO_SEVERITY.get(item.get("status_impact", ""), "major"),
        started_at=_parse_ts(item["begin"]),
        updated_at=_parse_ts(item["modified"]),
        resolved_at=_parse_ts(end) if end else None,
        url=INCIDENT_URL_BASE + item["uri"],
        last_message=(recent.get("text") or "")[:MESSAGE_LIMIT],
        regions=_regions(item),
    )


class GcpProvider:
    name = "gcp"
    lists_resolved = True

    def fetch(self) -> list[Incident]:
        payload = json.loads(http.fetch_bytes(FEED_URL))
        return [_to_incident(item) for item in payload]


register(GcpProvider())
