"""Azure provider. Reads the public RSS feed, which is empty when all is well."""

import hashlib
import html
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

from statusboard import http, regions
from statusboard.model import Incident, Region
from statusboard.providers import register

FEED_URL = "https://azure.status.microsoft/en-us/status/feed/"
DEFAULT_URL = "https://azure.status.microsoft/en-us/status/"
MESSAGE_LIMIT = 2000

_TAGS = re.compile(r"<[^>]+>")
_WHITESPACE = re.compile(r"\s+")
_RESOLVED_WORDS = re.compile(r"\b(resolved|mitigated)\b", re.IGNORECASE)


def _strip_html(text: str) -> str:
    return _WHITESPACE.sub(" ", html.unescape(_TAGS.sub(" ", text))).strip()


def _parse_pubdate(text: str | None, fallback: datetime) -> datetime:
    if not text:
        return fallback
    for candidate in (text, re.sub(r"\s+Z$", " +0000", text.strip())):
        try:
            parsed = parsedate_to_datetime(candidate)
        except (TypeError, ValueError):
            continue
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    return fallback


def _external_id(guid: str | None, title: str, pubdate: str | None) -> str:
    if guid and guid.strip():
        return guid.strip()
    digest = hashlib.sha1(f"{title}|{pubdate or ''}".encode()).hexdigest()
    return digest[:16]


def _regions_from_categories(categories: list[str]) -> list[Region]:
    by_name = dict(regions.azure_names_longest_first())
    out: list[Region] = []
    for category in categories:
        code = by_name.get(category.strip())
        if code and Region("azure", code) not in out:
            out.append(Region("azure", code))
    return out


def _regions_from_text(text: str) -> list[Region]:
    """Match display names longest first, deleting each match so prefixes cannot re-match."""
    out: list[Region] = []
    remaining = text
    for name, code in regions.azure_names_longest_first():
        pattern = re.compile(r"\b" + re.escape(name) + r"\b", re.IGNORECASE)
        if pattern.search(remaining):
            remaining = pattern.sub(" ", remaining)
            region = Region("azure", code)
            if region not in out:
                out.append(region)
    return out


def _text(item: ET.Element, tag: str) -> str | None:
    node = item.find(tag)
    return node.text if node is not None else None


def _to_incident(item: ET.Element, now: datetime) -> Incident:
    title = (_text(item, "title") or "").strip()
    pubdate_text = _text(item, "pubDate")
    started_at = _parse_pubdate(pubdate_text, now)
    description = _strip_html(_text(item, "description") or "")
    categories = [c.text or "" for c in item.findall("category")]
    found = _regions_from_categories(categories) or _regions_from_text(f"{title} {description}")
    resolved = _RESOLVED_WORDS.search(f"{title} {description}") is not None
    return Incident(
        provider="azure",
        external_id=_external_id(_text(item, "guid"), title, pubdate_text),
        title=title,
        severity="major",
        started_at=started_at,
        updated_at=started_at,
        resolved_at=started_at if resolved else None,
        url=(_text(item, "link") or "").strip() or DEFAULT_URL,
        last_message=description[:MESSAGE_LIMIT],
        regions=found,
    )


class AzureProvider:
    name = "azure"
    lists_resolved = False

    def fetch(self) -> list[Incident]:
        root = ET.fromstring(http.fetch_bytes(FEED_URL))
        now = datetime.now(timezone.utc)
        return [_to_incident(item, now) for item in root.iter("item")]


register(AzureProvider())
