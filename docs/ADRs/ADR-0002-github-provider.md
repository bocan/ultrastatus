# ADR-0002: GitHub provider

## Goal

Add the first real provider. GitHub runs on Atlassian Statuspage, which has the cleanest public API of the five. This proves the poll pipeline with live data.

## Non-goals

- No component status. Do not store the `components` array.
- No scheduled maintenances.
- No regions. GitHub is global.
- No changes to the schema.

## Outcome shape

```
statusboard/providers/github.py
tests/test_github.py
tests/fixtures/github_incidents.json     # a saved copy of the live feed
```

## What carries over from previous specs

From ADR-0001:

- `Incident(provider, external_id, title, severity, started_at, updated_at, resolved_at, url, last_message, regions)`
- `Severity = "minor" | "major" | "critical"`
- `Provider` protocol with `name`, `lists_resolved`, `fetch()`
- `register(provider)` in `statusboard.providers`
- `statusboard.http.fetch_bytes(url)` to monkeypatch in tests

## Implementation plan

1. Fetch `https://www.githubstatus.com/api/v2/incidents.json`. This returns the last 50 incidents, resolved ones included. Do not use `summary.json`. It omits resolved incidents, so `resolved_at` would never be set.
2. Map each item in `incidents` to an `Incident`.
3. Register the provider with `lists_resolved = True`.
4. Import `statusboard.providers.github` from `statusboard/providers/__init__.py`.
5. Save one live response as the fixture. Trim it to five incidents that cover `resolved` and at least two `impact` values. Keep the JSON valid.

## Behavioural definitions and contracts

Feed shape, verified 2026-09-05:

```json
{
  "page": {...},
  "incidents": [
    {
      "id": "abc123",
      "name": "Incidents with Actions",
      "status": "resolved",            // investigating | identified | monitoring | resolved | postmortem
      "impact": "minor",               // none | minor | major | critical
      "shortlink": "https://stspg.io/xyz",
      "started_at": "2026-08-17T18:01:00.000Z",
      "updated_at": "2026-08-17T18:23:47.000Z",
      "resolved_at": "2026-08-17T18:23:47.000Z",   // null while open
      "incident_updates": [
        { "body": "This incident has been resolved.", "status": "resolved", "created_at": "..." },
        ...
      ],
      "components": [...]
    }
  ]
}
```

Field mapping:

| Incident field | source |
|---|---|
| provider | `"github"` |
| external_id | `id` |
| title | `name` |
| severity | `impact`: `none` and `minor` to `minor`, `major` to `major`, `critical` to `critical` |
| started_at | `started_at` |
| updated_at | `updated_at` |
| resolved_at | `resolved_at`, `None` when null |
| url | `shortlink` |
| last_message | `incident_updates[0].body`. The array is newest first. Empty string if the array is empty. |
| regions | `[]` |

Timestamps arrive as ISO 8601 with milliseconds and a `Z`. Parse with `datetime.fromisoformat` (Python 3.11+ accepts `Z`). Truncate to seconds when storing. ADR-0001's `db.py` does the truncation.

A `postmortem` status with a `resolved_at` is a resolved incident. Do not treat `status` as the open/closed signal. Only `resolved_at` matters.

## Context7 lookups

- Atlassian Statuspage public API: search for "statuspage api v2 incidents.json". Confirm the `impact` values and that `incident_updates` is newest first.

## Dependencies

- ADR-0001 complete and `make test` green.
- No new packages.

## Test plan

`tests/test_github.py`:

- Monkeypatch `fetch_bytes` to return the fixture bytes. `fetch()` returns one `Incident` per fixture item.
- Severity mapping covers all four `impact` values, `none` included.
- An item with `resolved_at: null` gives `resolved_at is None`.
- `last_message` is the first update body.
- `regions == []` for every item.
- End to end: run the poll loop from ADR-0001 with only this provider against the `conn` fixture. `open_incidents` plus `recent_resolved(since=year 2000)` equals the fixture count.

## Acceptance criteria

- `make test` passes.
- `make poll` against the live feed prints `github: N incidents, 0 newly resolved` and exits 0.
- `sqlite3 statusboard.sqlite3 "select count(*) from incident where provider='github'"` matches N.

## Gotchas

- The feed is about 4 KB for summary but the incidents list can be 100 KB plus. That is fine.
- `impact` can be `none`. Do not crash on it.
- Do not add the `status` string to the database. It is not read anywhere.

## Handoff

Next session runs ADR-0003 (GCP). Nothing new is added to the shared contracts. If the Statuspage docs disagree with the field mapping above, note the difference in the project `README.md`.
