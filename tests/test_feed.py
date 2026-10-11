"""The RSS feed of open incidents, written as feed.xml beside the page."""

from xml.etree import ElementTree as ET

from statusboard import db
from statusboard.config import Config
from statusboard.feed import ATOM_NS, FEED_NAME, FEED_TITLE, rss
from statusboard.model import Region
from statusboard.render import build_context, render

from conftest import make_incident, utc

NOW = utc(2026, 9, 5, 12, 0, 0)
LABELS = {"cloudflare": "Cloudflare", "aws": "AWS"}


def _items(xml: str) -> list[ET.Element]:
    return ET.fromstring(xml).findall("./channel/item")


def _texts(item: ET.Element, tag: str) -> list[str]:
    return [e.text or "" for e in item.findall(tag)]


# Unit: the document itself.


def test_empty_feed_is_valid_rss_with_no_items():
    xml = rss([], {}, None, NOW)
    assert xml.startswith('<?xml version="1.0" encoding="UTF-8"?>\n<rss version="2.0">')
    root = ET.fromstring(xml)
    channel = root.find("channel")
    assert channel is not None
    assert channel.findtext("title") == FEED_TITLE
    assert channel.findtext("link") == ""
    assert channel.findtext("lastBuildDate") == "Sat, 05 Sep 2026 12:00:00 GMT"
    assert channel.findtext("ttl") == "2"
    assert _items(xml) == []
    assert channel.find(f"{{{ATOM_NS}}}link") is None


def test_site_url_sets_channel_link_and_self_link():
    channel = ET.fromstring(rss([], {}, "https://status.example", NOW)).find("channel")
    assert channel is not None
    assert channel.findtext("link") == "https://status.example/"
    self_link = channel.find(f"{{{ATOM_NS}}}link")
    assert self_link is not None
    assert self_link.get("href") == f"https://status.example/{FEED_NAME}"
    assert self_link.get("rel") == "self"
    assert self_link.get("type") == "application/rss+xml"


def test_item_carries_title_link_guid_date_description_and_categories():
    inc = make_incident(
        provider="cloudflare",
        external_id="z",
        title="Edge trouble",
        severity="critical",
        url="https://example.test/z",
        last_message="We are looking into it.",
        regions=[Region("aws", "us-east-1"), Region("gcp", "europe-west2")],
    )
    (item,) = _items(rss([inc], LABELS, None, NOW))
    assert item.findtext("title") == "[Cloudflare] critical: Edge trouble"
    assert item.findtext("link") == "https://example.test/z"
    guid = item.find("guid")
    assert guid is not None
    assert guid.text == "cloudflare:z"
    assert guid.get("isPermaLink") == "false"
    assert item.findtext("pubDate") == "Sat, 05 Sep 2026 10:00:00 GMT"
    assert item.findtext("description") == "We are looking into it."
    assert _texts(item, "category") == [
        "Cloudflare",
        "critical",
        "aws us-east-1",
        "gcp europe-west2",
    ]


def test_item_without_url_has_no_link_but_still_a_guid():
    inc = make_incident(provider="aws", external_id="e1", url=None, regions=[])
    (item,) = _items(rss([inc], LABELS, None, NOW))
    assert item.find("link") is None
    assert item.findtext("guid") == "aws:e1"


def test_incidents_sharing_one_url_keep_distinct_guids():
    """Every AWS incident links to the same health page; the guid must not."""
    shared = "https://health.aws.amazon.com/health/status"
    first = make_incident(provider="aws", external_id="one", url=shared)
    second = make_incident(provider="aws", external_id="two", url=shared)
    items = _items(rss([first, second], LABELS, None, NOW))
    assert [i.findtext("link") for i in items] == [shared, shared]
    assert [i.findtext("guid") for i in items] == ["aws:one", "aws:two"]


def test_item_without_message_falls_back_to_the_title():
    inc = make_incident(title="Quiet one", last_message="")
    (item,) = _items(rss([inc], LABELS, None, NOW))
    assert item.findtext("description") == "Quiet one"


def test_markup_in_titles_and_messages_is_escaped_not_injected():
    inc = make_incident(
        title='Edge <b>trouble</b> & "quotes"',
        last_message="<script>alert(1)</script>",
    )
    xml = rss([inc], LABELS, None, NOW)
    assert "<b>trouble</b>" not in xml
    assert "<script>" not in xml
    (item,) = _items(xml)
    assert item.findtext("title") == '[fake] major: Edge <b>trouble</b> & "quotes"'
    assert item.findtext("description") == "<script>alert(1)</script>"


def test_unknown_provider_label_falls_back_to_its_name():
    inc = make_incident(provider="mystery")
    (item,) = _items(rss([inc], {}, None, NOW))
    assert (item.findtext("title") or "").startswith("[mystery] ")
    assert _texts(item, "category")[0] == "mystery"


# Integration: the feed comes out of render with the page's own data.


def _fresh_polls(conn):
    from statusboard.render import PROVIDER_ORDER

    for name, _ in PROVIDER_ORDER:
        db.record_poll(conn, name, NOW, None)


def test_render_writes_feed_beside_the_page(conn, tmp_path):
    target = render(conn, tmp_path / "site", now=NOW)
    feed_file = target.parent / FEED_NAME
    assert feed_file.exists()
    assert _items(feed_file.read_text(encoding="utf-8")) == []


def test_page_links_to_the_feed(conn, tmp_path):
    html = render(conn, tmp_path / "site", now=NOW).read_text()
    assert (
        '<link rel="alternate" type="application/rss+xml" '
        f'title="{FEED_TITLE}" href="{FEED_NAME}">'
    ) in html
    assert f'<a href="{FEED_NAME}" type="application/rss+xml">' in html


def test_feed_lists_open_incidents_only_in_table_order(conn, tmp_path):
    _fresh_polls(conn)
    db.upsert_incident(
        conn,
        make_incident(
            provider="cloudflare",
            external_id="minor-new",
            title="Minor, newest",
            severity="minor",
            updated_at=utc(2026, 9, 5, 11, 0, 0),
        ),
    )
    db.upsert_incident(
        conn,
        make_incident(
            provider="aws",
            external_id="major-old",
            title="Major, older",
            severity="major",
            updated_at=utc(2026, 9, 5, 9, 0, 0),
        ),
    )
    db.upsert_incident(
        conn,
        make_incident(
            provider="aws",
            external_id="major-new",
            title="Major, newer",
            severity="major",
            updated_at=utc(2026, 9, 5, 10, 0, 0),
        ),
    )
    db.upsert_incident(
        conn,
        make_incident(
            provider="aws",
            external_id="done",
            title="Resolved, must not appear",
            severity="critical",
            resolved_at=utc(2026, 9, 5, 11, 30, 0),
        ),
    )
    target = render(conn, tmp_path / "site", now=NOW)
    xml = (target.parent / FEED_NAME).read_text(encoding="utf-8")
    assert [i.findtext("title") for i in _items(xml)] == [
        "[AWS] major: Major, newer",
        "[AWS] major: Major, older",
        "[Cloudflare] minor: Minor, newest",
    ]
    assert "Resolved, must not appear" not in xml


def test_feed_ignores_the_region_filter(conn, monkeypatch, tmp_path):
    """A filtered page still feeds every open incident; readers can filter."""
    _fresh_polls(conn)
    db.upsert_incident(
        conn,
        make_incident(
            provider="aws",
            external_id="far",
            title="Elsewhere",
            regions=[Region("aws", "ap-southeast-2")],
        ),
    )
    monkeypatch.setattr(
        "statusboard.render.load_config",
        lambda: Config(frozenset({("aws", "eu-west-2")}), "https://status.example"),
    )
    context = build_context(conn, NOW)
    assert context["open"] == []
    assert len(context["open_elsewhere"]) == 1
    (item,) = _items(context["feed_xml"])
    assert item.findtext("title") == "[AWS] major: Elsewhere"
    channel = ET.fromstring(context["feed_xml"]).find("channel")
    assert channel is not None
    assert channel.findtext("link") == "https://status.example/"
