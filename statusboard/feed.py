"""An RSS 2.0 feed of every open incident, written beside the page as feed.xml.

One item per open incident, in the same order as the open table: worst
severity first, then most recently updated. The guid is provider plus
external id, which the database keeps unique, so a reader shows each incident
once and drops it from the feed when it resolves. The incident URL is not
unique enough for that: every AWS incident links to the same health page. The
description carries the latest update as plain text.
"""

from datetime import datetime
from email.utils import format_datetime
from xml.etree import ElementTree as ET

from statusboard.model import Incident

FEED_NAME = "feed.xml"
FEED_TITLE = "Ultra Status open incidents"
FEED_DESCRIPTION = "Every open incident on the clouds and services your work runs on."
ATOM_NS = "http://www.w3.org/2005/Atom"
TTL_MINUTES = 2


def _rfc822(dt: datetime) -> str:
    return format_datetime(dt, usegmt=True)


def _text(parent: ET.Element, tag: str, text: str) -> ET.Element:
    child = ET.SubElement(parent, tag)
    child.text = text
    return child


def item_title(inc: Incident, label: str) -> str:
    return f"[{label}] {inc.severity}: {inc.title}"


def item_guid(inc: Incident) -> str:
    return f"{inc.provider}:{inc.external_id}"


def rss(
    open_incidents: list[Incident],
    labels: dict[str, str],
    site_url: str | None,
    now: datetime,
) -> str:
    """The feed as a UTF-8 XML document with an XML declaration."""
    ET.register_namespace("atom", ATOM_NS)
    root = ET.Element("rss", version="2.0")
    channel = ET.SubElement(root, "channel")
    _text(channel, "title", FEED_TITLE)
    _text(channel, "link", f"{site_url}/" if site_url else "")
    _text(channel, "description", FEED_DESCRIPTION)
    _text(channel, "language", "en")
    _text(channel, "lastBuildDate", _rfc822(now))
    _text(channel, "ttl", str(TTL_MINUTES))
    if site_url:
        ET.SubElement(
            channel,
            f"{{{ATOM_NS}}}link",
            href=f"{site_url}/{FEED_NAME}",
            rel="self",
            type="application/rss+xml",
        )
    for inc in open_incidents:
        label = labels.get(inc.provider, inc.provider)
        item = ET.SubElement(channel, "item")
        _text(item, "title", item_title(inc, label))
        if inc.url:
            _text(item, "link", inc.url)
        _text(item, "guid", item_guid(inc)).set("isPermaLink", "false")
        _text(item, "pubDate", _rfc822(inc.started_at))
        _text(item, "description", inc.last_message or inc.title)
        _text(item, "category", label)
        _text(item, "category", inc.severity)
        for region in inc.regions:
            _text(item, "category", f"{region.cloud} {region.code}")
    ET.indent(root)
    body = ET.tostring(root, encoding="unicode")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + body + "\n"
