# ADR-0007: Azure provider

## Goal

Add Azure from its public RSS feed. This is the weakest feed of the five: no JSON, no severity, no structured region field. The provider must parse RSS and find region names in free text.

## Non-goals

- No Azure Service Health or Resource Health API. Those need credentials.
- No HTML scraping of the status grid page.
- No changes to the schema.

## Outcome shape

```
statusboard/providers/azure.py
tests/test_azure.py
tests/fixtures/azure_empty.xml       # live capture, no items
tests/fixtures/azure_items.xml       # two items, see test plan for how to build it
```

## What carries over from previous specs

From ADR-0001: `Incident`, `Region`, `Severity`, `Provider`, `register()`, `fetch_bytes`, `lists_resolved = False` behaviour.

From ADR-0005: `regions.azure_names_longest_first()` returning `[(display_name, code), ...]`.

## Implementation plan

1. Fetch `https://azure.status.microsoft/en-us/status/feed/`.
2. Parse with `xml.etree.ElementTree`. Read `channel/item` elements.
3. Map each item to an `Incident`.
4. Register with `lists_resolved = False`.
5. Import the module from `statusboard/providers/__init__.py`.
6. Build the fixtures. See the test plan.

## Behavioural definitions and contracts

Verified live on 2026-09-05, the feed with no incidents is:

```xml
<?xml version="1.0" encoding="utf-8"?>
<rss xmlns:a10="http://www.w3.org/2005/Atom" version="2.0">
  <channel ...>
    <title>Azure Status</title>
    <link>https://azure.status.microsoft/en-us/status/</link>
    <description>Azure Status</description>
    <language>en-us</language>
    <lastBuildDate>Sat, 05 Sep 2026 20:02:00 Z</lastBuildDate>
  </channel>
</rss>
```

When incidents exist, each is an RSS 2.0 `item` with `title`, `description`, `link`, `pubDate`, and normally `guid`. The `description` is HTML. Treat every one of these as optional except `title`.

Field mapping:

| Incident field | source |
|---|---|
| provider | `"azure"` |
| external_id | `guid` text if present and non-empty. Otherwise the first 16 hex characters of `sha1(title + "|" + pubDate)`. |
| title | `title` |
| severity | always `major`. The feed carries no severity. |
| started_at | `pubDate` parsed with `email.utils.parsedate_to_datetime`. If absent or unparseable, the time of the poll. |
| updated_at | same as `started_at` |
| resolved_at | if the title or the plain-text description contains the word `resolved` or `mitigated`, case-insensitive, use `started_at`. Else `None`. |
| url | `link` text, else `https://azure.status.microsoft/en-us/status/` |
| last_message | description with HTML tags removed, whitespace collapsed, first 2000 characters. Use `html.parser.HTMLParser` or a simple regex `<[^>]+>`. Unescape entities with `html.unescape`. |
| regions | see below |

Region extraction. Build `text = title + " " + plain_description`. Loop over `azure_names_longest_first()`. For each `(name, code)`, search with a word-boundary regex, case-insensitive: `r"\b" + re.escape(name) + r"\b"`. On a match, add `Region("azure", code)` and delete the matched span from `text` so that a shorter name inside it, for example `East US` inside `East US 2`, does not match again. Return regions in match order, deduplicated. Incidents that name no region get `[]`.

`pubDate` in this feed ends in ` Z` rather than ` GMT`. `parsedate_to_datetime` may reject it. If parsing fails, replace a trailing ` Z` with ` +0000` and retry.

## Context7 lookups

- `/python/cpython`: `email.utils.parsedate_to_datetime`, `xml.etree.ElementTree`, `html.unescape`.

## Dependencies

- ADR-0001 and ADR-0005 complete, `make test` green.
- No new packages.

## Test plan

Building `azure_items.xml`. Try the Wayback Machine first: `https://web.archive.org/web/2025*/https://azure.status.microsoft/en-us/status/feed/` and pick a capture that has items. If none is found within ten minutes, write the fixture by hand as valid RSS 2.0 with two items:

- Item one: title `Azure Kubernetes Service - West Europe and North Europe - Investigating`, description mentions `West Europe` and `North Europe` inside `<p>` tags, a `guid`, a `pubDate` ending in ` Z`.
- Item two: title `Storage - East US 2 - Mitigated`, description mentions `East US 2`, no `guid`.

Tests:

- Empty fixture yields zero incidents and does not raise.
- Item one yields two regions: `westeurope`, `northeurope`, severity `major`, `resolved_at is None`, `external_id` equal to the guid.
- Item two yields `[Region("azure", "eastus2")]` and not `eastus`. `resolved_at` is set. `external_id` is 16 hex characters and is stable across two parses.
- HTML is stripped from `last_message` and entities are unescaped.
- `pubDate` with a trailing ` Z` parses to a UTC datetime.
- End to end: poll with the items fixture, then with the empty fixture. Item one becomes resolved.

## Acceptance criteria

- `make test` passes.
- `make poll` prints `azure: 0 incidents, 0 newly resolved` on a quiet day and exits 0.

## Gotchas

- The feed is empty most of the time. An empty feed is a success, not an error.
- Do not use `feedparser`. The standard library is enough and keeps the runtime dependency count at zero.
- Region names in text can appear as `West Europe` and as `westeurope`. Only match display names. ARM names in free text are rare and are ignored in v1.
- The `link` often points to the whole status page, not to the incident. That is acceptable.

## Handoff

Next session runs ADR-0008 (static dashboard). All five providers are now registered. Confirm `make poll` runs all five and exits 0 before starting ADR-0008.
