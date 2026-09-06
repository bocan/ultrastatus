"""Airbyte provider. Instatus serves no incidents JSON, so parse the RSS history.

Each item's plain-text description holds a header (Type, Duration, Affected
Components) and a timeline of "Mon D, HH:MM:SS GMT+0 - State - message"
entries. Timeline entries are not always in time order: maintenance items put
the Completed entry first. So the newest entry is chosen by timestamp.
"""

import html
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

from statusboard import http
from statusboard.model import Incident, Severity
from statusboard.providers import register

FEED_URL = "https://status.airbyte.com/history.rss"
DEFAULT_URL = "https://status.airbyte.com/"
MESSAGE_LIMIT = 2000

TYPE_TO_SEVERITY: dict[str, Severity] = {"incident": "major", "maintenance": "minor"}
TERMINAL_STATES = {"resolved", "completed"}
# Timeline stamps carry no year. An entry more than this far before pubDate is
# taken to be in the next year (a December incident resolved in January). A
# smaller gap is real: maintenance entries can sit a few minutes before pubDate.
ROLLOVER_GAP = timedelta(days=7)

_HEADER = re.compile(r"^(Type|Duration|Affected Components):\s*(.*)$")
_STAMP_TEXT = r"[A-Z][a-z]{2} \d{1,2}, \d{2}:\d{2}:\d{2}"
# Three groups: timestamp, state, message. The lookahead that ends a message
# at the next timestamp must not capture, or findall returns four values.
_ENTRY = re.compile(
    r"(" + _STAMP_TEXT + r") GMT\+0 - ([A-Za-z][A-Za-z ]*?) - (.*?)"
    r"(?=\s+(?:" + _STAMP_TEXT + r") GMT\+0 - |\s*$)",
    re.DOTALL,
)
_WHITESPACE = re.compile(r"\s+")


def _parse_stamp(text: str, year: int, not_before: datetime) -> datetime:
    """'Sep 1, 16:02:31' with the year from pubDate. Roll into the next year if it lands before the start."""
    stamp = datetime.strptime(f"{text} {year}", "%b %d, %H:%M:%S %Y").replace(tzinfo=timezone.utc)
    if stamp < not_before - ROLLOVER_GAP:
        stamp = stamp.replace(year=year + 1)
    return stamp


def parse_description(text: str, started_at: datetime) -> tuple[dict[str, str], list[dict]]:
    """Returns (header, entries). Entries are sorted oldest first by timestamp."""
    header: dict[str, str] = {}
    body_lines = []
    for line in html.unescape(text or "").splitlines():
        stripped = line.strip()
        match = _HEADER.match(stripped)
        if match:
            header[match.group(1)] = match.group(2).strip()
        elif stripped:
            body_lines.append(stripped)
    timeline_text = " ".join(body_lines)
    entries = []
    for stamp, state, message in _ENTRY.findall(timeline_text):
        entries.append(
            {
                "at": _parse_stamp(stamp, started_at.year, started_at),
                "state": state.strip().lower(),
                "message": _WHITESPACE.sub(" ", message).strip(),
            }
        )
    # Oldest first. On equal timestamps a terminal entry sorts last, because
    # some maintenance items stamp every entry with the same minute.
    entries.sort(key=lambda e: (e["at"], e["state"] in TERMINAL_STATES))
    return header, entries


def _external_id(guid: str | None, link: str | None) -> str:
    source = (guid or "").strip() or (link or "").strip()
    return source.rstrip("/").rsplit("/", 1)[-1] or source


def _text(item: ET.Element, tag: str) -> str | None:
    node = item.find(tag)
    return node.text if node is not None else None


def _to_incident(item: ET.Element, now: datetime) -> Incident:
    pub = _text(item, "pubDate")
    try:
        started_at = parsedate_to_datetime(pub) if pub else now
    except (TypeError, ValueError):
        started_at = now
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=timezone.utc)
    header, entries = parse_description(_text(item, "description") or "", started_at)
    newest = entries[-1] if entries else None
    updated_at = newest["at"] if newest else started_at
    # Resolved when any entry is terminal. Seen live: a maintenance window
    # completed at 12:00 with a further note added at 20:00. Instatus shows it
    # as completed, so the newest terminal entry gives the resolve time.
    terminal = [e for e in entries if e["state"] in TERMINAL_STATES]
    resolved_at = terminal[-1]["at"] if terminal else None
    message = newest["message"] if newest else ""
    components = header.get("Affected Components", "").strip()
    if components:
        message = f"Components: {components}. {message}".strip()
    return Incident(
        provider="airbyte",
        external_id=_external_id(_text(item, "guid"), _text(item, "link")),
        title=(_text(item, "title") or "").strip(),
        severity=TYPE_TO_SEVERITY.get(header.get("Type", "").strip().lower(), "major"),
        started_at=started_at,
        updated_at=updated_at,
        resolved_at=resolved_at,
        url=(_text(item, "link") or "").strip() or DEFAULT_URL,
        last_message=message[:MESSAGE_LIMIT],
        regions=[],
    )


class AirbyteProvider:
    name = "airbyte"
    lists_resolved = True
    label = "Airbyte"

    def fetch(self) -> list[Incident]:
        root = ET.fromstring(http.fetch_bytes(FEED_URL))
        now = datetime.now(timezone.utc)
        return [_to_incident(item, now) for item in root.iter("item")]


register(AirbyteProvider())
