"""Databricks provider. Merges three status.io pages, one per host cloud."""

import json
from datetime import datetime

from statusboard import http, regions
from statusboard.model import Incident, Region, Severity
from statusboard.providers import register

MESSAGE_LIMIT = 2000

# (page key, status.io page id, public host). Ids verified 2026-09-05.
PAGES: list[tuple[str, str, str]] = [
    ("aws", "5cf02dde58a00904bda41926", "status.databricks.com"),
    ("azure", "5d49ec10226b9e13cb6a422e", "status.azuredatabricks.net"),
    ("gcp", "60087ab5608daf0535dc8e23", "status.gcp.databricks.com"),
]

# status.io status codes: 100 Operational, 300 Degraded Performance,
# 400 Partial Service Disruption, 500 Service Disruption, 600 Security Event.
STATUS_CODE_TO_SEVERITY: dict[int, Severity] = {
    300: "minor",
    400: "major",
    500: "critical",
    600: "critical",
}


def api_url(page_id: str) -> str:
    return f"https://api.status.io/1.0/status/{page_id}"


def _parse_ts(text: str) -> datetime:
    return datetime.fromisoformat(text)


def _newest_message(messages: list[dict]) -> dict | None:
    """The status.io docs do not state message order, so sort by datetime."""
    dated = [m for m in messages if m.get("datetime")]
    if not dated:
        return messages[-1] if messages else None
    return max(dated, key=lambda m: m["datetime"])


def _severity(item: dict, newest: dict | None) -> Severity:
    code = item.get("current_status")
    if code is None and newest is not None:
        code = newest.get("status")
    try:
        return STATUS_CODE_TO_SEVERITY.get(int(code), "major")
    except (TypeError, ValueError):
        return "major"


def _regions(page_key: str, item: dict) -> list[Region]:
    out: list[Region] = []
    for container in item.get("containers_affected") or []:
        code = regions.normalise(page_key, container.get("name", ""))
        region = Region(page_key, code)
        if regions.lookup(page_key, code) is not None and region not in out:
            out.append(region)
    return out


def _to_incident(page_key: str, page_id: str, host: str, item: dict) -> Incident:
    started_at = _parse_ts(item["datetime_open"])
    newest = _newest_message(item.get("messages") or [])
    if newest is not None and newest.get("datetime"):
        updated_at = _parse_ts(newest["datetime"])
    else:
        updated_at = started_at
    return Incident(
        provider="databricks",
        external_id=f"{page_key}:{item['_id']}",
        title=item["name"],
        severity=_severity(item, newest),
        started_at=started_at,
        updated_at=updated_at,
        resolved_at=None,
        url=f"https://{host}/pages/incident/{page_id}/{item['_id']}",
        last_message=((newest or {}).get("details") or "")[:MESSAGE_LIMIT],
        regions=_regions(page_key, item),
    )


class DatabricksProvider:
    name = "databricks"
    lists_resolved = False

    def fetch(self) -> list[Incident]:
        incidents: list[Incident] = []
        for page_key, page_id, host in PAGES:
            payload = json.loads(http.fetch_bytes(api_url(page_id)))
            result = payload.get("result") or {}
            for item in result.get("incidents") or []:
                incidents.append(_to_incident(page_key, page_id, host, item))
        return incidents


register(DatabricksProvider())
