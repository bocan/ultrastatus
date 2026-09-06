# ADR-0016: Slack provider

## Goal

Add Slack from its public status API. Slack runs its own status site with a small JSON API. The history endpoint lists recent incidents with a status field, so resolved incidents come from the feed.

## Non-goals

- No regions. Slack reports no geography.
- No per-service tiles. The feed names services such as `Messaging` per incident; they go into the message, not into tiles.
- No schema changes.

## Outcome shape

```
statusboard/providers/slack.py
tests/test_slack.py
tests/fixtures/slack_history.json          # trimmed live copy, three incidents including the active one
statusboard/render.py                      # one line in GROUPS, one in SOURCE_URLS
```

## What carries over from previous specs

From ADR-0001: `Incident`, `Severity`, `Provider`, `register()`, `fetch_bytes`, `lists_resolved`.

From ADR-0006: pick the newest note by its timestamp rather than trusting array order.

From ADR-0007: strip HTML with the standard library and unescape entities.

From ADR-0014: the `Workplace` group and the registration guard.

## Implementation plan

1. Fetch `https://slack-status.com/api/v2.0.0/history`. Do not use `/current`. It lists only active incidents, so `resolved_at` would never be set from the feed.
2. Map each item to an `Incident`.
3. Register with `lists_resolved = True`.
4. Import the module from `providers/__init__.py`.
5. Add `("slack", "Slack")` after Google Workspace in the Workplace group and `https://slack-status.com/` to `SOURCE_URLS`.
6. Capture the fixture. Keep the active incident, one resolved incident, and one more. Cut note bodies to 200 characters and keep at most two notes each.

## Behavioural definitions and contracts

Verified live on 2026-09-06. History returned 37 incidents, 97 KB. Shape:

```json
[
  {
    "id": 1576,
    "title": "Trouble Accessing Historical Messages With Custom Data Retention Policies Enabled",
    "type": "incident",                        // incident | outage | notice, per Slack's docs
    "status": "active",                        // ok | active | resolved | scheduled | completed | cancelled
    "url": "https://slack-status.com/2026-08/e07b9271f0346c3b",
    "date_created": "2026-08-13T14:21:41-07:00",
    "date_updated": "2026-09-04T10:00:57-07:00",
    "notes": [
      { "body": "<p>Users with custom data retention policies ...</p>", "date_created": "2026-08-13T14:21:41-07:00" },
      { "body": "<p>We're continuing to investigate ...</p>",            "date_created": "2026-08-13T14:49:40-07:00" }
    ],
    "services": ["Messaging", "Workspace/Org Administration"]
  }
]
```

Timestamps carry a `-07:00` offset. `datetime.fromisoformat` handles them. The store converts to UTC.

Field mapping:

| Incident field | source |
|---|---|
| provider | `"slack"` |
| external_id | `str(id)` |
| title | `title` |
| severity | `type`: `outage` to `critical`, `incident` to `major`, `notice` to `minor`. Anything else to `major`. |
| started_at | `date_created` |
| updated_at | `date_updated` |
| resolved_at | `date_updated` when `status` is terminal, else `None`. Slack's docs list `ok`, `active`, `resolved`, `scheduled`, `completed`, and `cancelled`; the last three belong to maintenance windows. Terminal means `resolved`, `completed`, `cancelled`, or `ok`. `active` and `scheduled` stay open. Slack gives no separate resolve time, so the last update is the best estimate. |
| url | `url` |
| last_message | body of the note with the newest `date_created`, HTML stripped, entities unescaped, whitespace collapsed, first 2000 characters. Empty when there are no notes. If `services` is non-empty, prefix the message with `Services: Messaging, Workspace/Org Administration. ` |
| regions | `[]` |

Note order in the live feed looked oldest first. Do not rely on it. Take the max by `date_created`.

## Context7 lookups

- Resolve `Slack` and query `slack-status.com API v2.0.0 history endpoint incident type values`. Slack documents the status API under api.slack.com. Confirm the three `type` values. If the docs list others, map them and note it in the README.

## Dependencies

- ADR-0014 complete.
- No new packages.

## Test plan

`tests/test_slack.py`:

- Fixture parses to three incidents. Ids are strings.
- The active incident has `resolved_at is None`. A resolved one has `resolved_at == date_updated` in UTC.
- `type` mapping for `outage`, `incident`, `notice`, and `weird`.
- The newest note wins when the notes array is reversed.
- HTML tags are gone from `last_message`, `&amp;` style entities are unescaped, and the `Services:` prefix appears when services are listed.
- An item with no notes gives an empty message, or only the services prefix.
- `url` passes through. `regions == []`.
- End to end through the poll loop: three rows stored, one open.
- `tests/test_groups.py` passes, proving the group entry.

## Acceptance criteria

- `make test` passes.
- `make poll` prints `slack: N incidents, 0 newly resolved`, N about 37.
- The Workplace group shows Google Workspace and Slack tiles.

## Gotchas

- Slack timestamps are Pacific time with an explicit offset. Never treat them as UTC without converting. `db.to_iso` converts, so pass aware datetimes through.
- The `id` is an integer in the feed and a string in the store. Cast once, in the provider.
- `resolved_at` from `date_updated` means a post-resolution edit moves the resolve time. Accept that.
- The `/current` endpoint has a top-level `status` field of `active` or `ok`. It is not used.

## Handoff

The Workplace group now holds two providers. Atlassian, when added, is a one-line Statuspage instance from ADR-0010 plus a group entry here.
