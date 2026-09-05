"""AWS provider. Reads the undocumented public JSON behind the AWS Health Dashboard."""

import codecs
import json
from datetime import datetime, timezone

from statusboard import http
from statusboard.model import Incident, Region, Severity
from statusboard.providers import register

FEED_URL = "https://health.aws.amazon.com/public/currentevents"
DASHBOARD_URL = "https://health.aws.amazon.com/health/status"
MESSAGE_LIMIT = 2000

# Top-level "status" is a string: "1" informational, "2" degradation, "3" disruption.
STATUS_TO_SEVERITY: dict[str, Severity] = {
    "1": "minor",
    "2": "major",
    "3": "critical",
}


def _decode(raw: bytes) -> str:
    """Sniff the byte order mark. The feed is UTF-16 with a BOM; the header lies."""
    if raw.startswith(codecs.BOM_UTF16_LE) or raw.startswith(codecs.BOM_UTF16_BE):
        return raw.decode("utf-16")
    return raw.decode("utf-8")


def _from_unix(seconds: int | str) -> datetime:
    return datetime.fromtimestamp(int(seconds), tz=timezone.utc)


def _region_from_arn(arn: str) -> list[Region]:
    parts = arn.split(":")
    region = parts[3] if len(parts) > 3 else ""
    return [Region("aws", region)] if region else []


def _to_incident(item: dict) -> Incident:
    started_at = _from_unix(item["date"])
    log = item.get("event_log") or []
    if log:
        last = log[-1]
        updated_at = _from_unix(last["timestamp"])
        last_message = (last.get("message") or "")[:MESSAGE_LIMIT]
    else:
        updated_at = started_at
        last_message = ""
    return Incident(
        provider="aws",
        external_id=item["arn"],
        title=f"{item.get('service_name', 'AWS')}: {item.get('summary', '')}",
        severity=STATUS_TO_SEVERITY.get(str(item.get("status", "")), "major"),
        started_at=started_at,
        updated_at=updated_at,
        resolved_at=None,
        url=DASHBOARD_URL,
        last_message=last_message,
        regions=_region_from_arn(item["arn"]),
    )


class AwsProvider:
    name = "aws"
    lists_resolved = False

    def fetch(self) -> list[Incident]:
        payload = json.loads(_decode(http.fetch_bytes(FEED_URL)))
        return [_to_incident(item) for item in payload]


register(AwsProvider())
