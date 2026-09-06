# ADR-0019: Airbyte provider from Instatus RSS

## Goal

Add Airbyte. Its status page runs on Instatus, which serves no incidents JSON, but publishes an RSS history feed with the full incident timeline in each item. Parse that.

## Non-goals

- No regions. Airbyte names regions in free text such as `US-Central`, but they are Airbyte Cloud regions, not host cloud regions.
- No component storage.
- No schema changes.

## Outcome shape

```
statusboard/providers/airbyte.py
tests/test_airbyte.py
tests/fixtures/airbyte_history.xml          # trimmed live copy, three items
statusboard/render.py                       # group entry and source URL
```

## What carries over from previous specs

From ADR-0007: RSS parsing with `xml.etree.ElementTree`, `parsedate_to_datetime`, and `_strip_html`.

From ADR-0016: the pattern of picking the newest timeline entry and prefixing the affected services.

From ADR-0014: the Data platforms group.

## Implementation plan

1. Fetch `https://status.airbyte.com/history.rss`. Verified live on 2026-09-06: 50 items, 103 KB.
2. Parse `channel/item`. Map each to an `Incident`.
3. Register with `lists_resolved = True`. The feed includes resolved incidents and their timelines say so.
4. Add `("airbyte", "Airbyte")` to Data platforms after `snowflake` and the source URL `https://status.airbyte.com/`.
5. Capture the fixture: the newest item, one resolved item with a multi-step timeline, and one maintenance item if the feed has one. Cut descriptions to the first three timeline entries.

## Behavioural definitions and contracts

Item shape, verified live:

```xml
<item>
  <title>Jobs are failing to launch in US-Central region.</title>
  <description>
    Type: Incident
    Duration: 1 day, 8 hours and 32 minutes

    Affected Components: Data Sync
    Sep 1, 15:30:00 GMT+0 - Investigating - We are currently investigating this incident. Sep 1, 15:50:00 GMT+0 - Monitoring - We implemented a fix and are currently monitoring the result. Sep 1, 16:02:31 GMT+0 - Resolved - This incident has been resolved.
  </description>
  <content:encoded>...HTML version of the same...</content:encoded>
  <pubDate>Tue, 1 Sep 2026 15:30:00 +0000</pubDate>
  <link>https://status.airbyte.com/incident/cmtiukc5l0m7k1ao1dcpz87yt</link>
  <guid>https://status.airbyte.com/incident/cmtiukc5l0m7k1ao1dcpz87yt</guid>
</item>
```

Use `description`, the plain-text version. Ignore `content:encoded`.

### Parsing the description

Split into a header and a timeline.

- Header lines match `^(Type|Duration|Affected Components):\s*(.*)$`. Collect them into a dict.
- The timeline is everything after the header. Entries match `(\w{3} \d{1,2}, \d{2}:\d{2}:\d{2}) GMT\+0 - (\w+) - (.*?)(?=\s+\w{3} \d{1,2}, \d{2}:\d{2}:\d{2} GMT\+0 - |\s*$)` with `re.DOTALL`. Each gives a timestamp text, a state word, and a message.
- Timeline timestamps have no year. Use the year from `pubDate`. If the resulting datetime is earlier than `started_at`, add one year. This handles a December incident resolved in January.
- Do not use `Duration`. The live value `1 day, 8 hours and 32 minutes` did not match the 32 minute timeline. It is unreliable.

### Field mapping

| Incident field | source |
|---|---|
| provider | `"airbyte"` |
| external_id | last path segment of `guid`, for example `cmtiukc5l0m7k1ao1dcpz87yt`. Fall back to the whole `guid`, then to `link`. |
| title | `title` |
| severity | header `Type`: `Incident` to `major`, `Maintenance` to `minor`. Anything else to `major`. |
| started_at | `pubDate` |
| updated_at | timestamp of the last timeline entry, else `started_at` |
| resolved_at | timestamp of the last timeline entry when its state is `Resolved` or `Completed`, else `None` |
| url | `link`, else the default page URL |
| last_message | last timeline entry's message, first 2000 characters. If `Affected Components` is non-empty, prefix `Components: Data Sync. ` |
| regions | `[]` |

State words seen live: `Investigating`, `Identified`, `Monitoring`, `Resolved`. Maintenance items use `Scheduled`, `In progress`, `Completed`. Match case-insensitively.

## Context7 lookups

- None for the feed. Instatus documents a private API only. The RSS is the public contract.
- `/python/cpython`: `re.DOTALL` and lookahead, if needed.

## Dependencies

- ADR-0014 complete. ADR-0018 is not required, but the group order puts `airbyte` after `snowflake`, so if Snowflake is not yet there, place `airbyte` after `dbt`.
- No new packages.

## Test plan

`tests/test_airbyte.py`:

- Fixture parses to three incidents with ids taken from the guid path.
- The resolved item has `resolved_at` equal to the last timeline timestamp in UTC, and `updated_at` equal to it.
- An item whose last entry is `Monitoring` has `resolved_at is None`.
- Year rollover: a hand-built item with `pubDate` in December and a `Resolved` entry dated `Jan 2` resolves in the following year.
- `Type: Maintenance` gives `minor`; `Type: Incident` gives `major`; missing type gives `major`.
- `last_message` starts with `Components: Data Sync. ` and holds the last entry's text, no HTML.
- A description with no timeline gives `updated_at == started_at`, `resolved_at is None`, and a message of only the components prefix or empty.
- End to end through the poll loop.

## Acceptance criteria

- `make test` passes.
- `make poll` prints `airbyte: 50 incidents, 0 newly resolved` or similar.
- The Data platforms group shows the Airbyte tile.

## Gotchas

- The `description` element is indented with spaces and newlines. Normalise whitespace before matching the timeline, but keep the line structure for the header.
- Timeline entries are separated by a space, not a newline, in the plain-text description. The lookahead in the regex handles that.
- `GMT+0` is literal text, not a parseable zone. Strip it and treat the time as UTC.
- Instatus can list the same incident twice if it was reopened. The upsert keys on the guid, so the second wins.

## Handoff

None. With ADR-0017, ADR-0018, and ADR-0019 done, Data platforms holds Databricks, dbt, Snowflake, and Airbyte.
