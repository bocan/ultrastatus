# ADR-0003: Google Cloud provider

## Goal

Add the GCP provider. GCP publishes a documented JSON incident feed with region ids. This is the first provider that emits regions.

## Non-goals

- No product or component list.
- No changes to the schema.
- No region coordinate lookup. Only the region code is stored. ADR-0005 adds coordinates.

## Outcome shape

```
statusboard/providers/gcp.py
tests/test_gcp.py
tests/fixtures/gcp_incidents.json     # trimmed live copy, 4 to 6 incidents
```

## What carries over from previous specs

From ADR-0001:

- `Incident`, `Region(cloud, code)`, `Severity`
- `Provider` protocol, `register()`, `fetch_bytes`
- GCP region code form: lowercase hyphenated as GCP uses it, for example `us-central1`.

From ADR-0002: the pattern of one provider module, one fixture, one test file.

## Implementation plan

1. Fetch `https://status.cloud.google.com/incidents.json`. It returns a JSON array of incidents, newest first, resolved ones included. About 160 KB.
2. Map each item to an `Incident`.
3. Register with `lists_resolved = True`.
4. Import the module from `statusboard/providers/__init__.py`.
5. Save a trimmed fixture. Include at least one incident with `end: null` if one exists at capture time. If none is open, hand-edit one fixture item to set `end` to `null` and `currently_affected_locations` to a non-empty list, and say so in a comment file next to it (`gcp_incidents.README.md`).

## Behavioural definitions and contracts

Feed shape, verified 2026-09-05:

```json
[
  {
    "id": "J5ia5t9p3g9Q5Wi7r8Ev",
    "number": "847028556969787721",
    "begin": "2026-09-01T14:44:00+00:00",
    "created": "2026-09-01T16:03:12+00:00",
    "end": "2026-09-01T18:52:00+00:00",          // null while open
    "modified": "2026-09-03T17:47:02+00:00",
    "external_desc": "Multiple products in us-central1-b are experiencing network service degradation.",
    "severity": "medium",                         // low | medium | high
    "status_impact": "SERVICE_DISRUPTION",        // SERVICE_INFORMATION | SERVICE_DISRUPTION | SERVICE_OUTAGE
    "service_key": "zall",
    "service_name": "Multiple Products",
    "uri": "incidents/J5ia5t9p3g9Q5Wi7r8Ev",
    "currently_affected_locations": [],
    "previously_affected_locations": [ { "title": "Iowa (us-central1)", "id": "us-central1" } ],
    "affected_products": [ { "title": "Cloud Run", "id": "..." } ],
    "most_recent_update": { "when": "...", "text": "## Preliminary Incident Report\n...", "status": "AVAILABLE", "affected_locations": [] },
    "updates": [ ... ]
  }
]
```

Field mapping:

| Incident field | source |
|---|---|
| provider | `"gcp"` |
| external_id | `id` |
| title | `external_desc` |
| severity | `status_impact`: `SERVICE_INFORMATION` to `minor`, `SERVICE_DISRUPTION` to `major`, `SERVICE_OUTAGE` to `critical`. Any other value to `major`. |
| started_at | `begin` |
| updated_at | `modified` |
| resolved_at | `end`, `None` when null |
| url | `"https://status.cloud.google.com/" + uri` |
| last_message | `most_recent_update.text`, first 2000 characters. Strip nothing else. Markdown is fine as plain text. |
| regions | union of `id` values from `currently_affected_locations` and `previously_affected_locations`, each as `Region("gcp", id)`. Deduplicate. Keep order of first appearance. |

Timestamps carry a `+00:00` offset. `datetime.fromisoformat` handles them.

Location ids that are not regions, for example `global` or a multi-region such as `us` or `europe`, pass through unchanged. ADR-0005 decides which codes have coordinates. Do not filter here.

## Context7 lookups

- Google Cloud status dashboard JSON: search "status.cloud.google.com incidents.json schema" or "Google Cloud Service Health incidents.json". Confirm the `status_impact` enum.

## Dependencies

- ADR-0001 and ADR-0002 complete, `make test` green.
- No new packages.

## Test plan

`tests/test_gcp.py`:

- Fixture parses to N incidents.
- All three `status_impact` values map correctly. Add a synthetic item with an unknown value and assert `major`.
- Region union: an item with `us-central1` in previously and `us-east1` in currently yields both, in that order, no duplicates.
- `end: null` gives `resolved_at is None`.
- `url` starts with `https://status.cloud.google.com/incidents/`.
- End to end through the poll loop: `incident_region` rows exist for the fixture regions.

## Acceptance criteria

- `make test` passes.
- `make poll` prints `gcp: N incidents, 0 newly resolved`.
- `select count(*) from incident_region where provider='gcp'` is greater than 0.

## Gotchas

- The feed contains the whole incident history, hundreds of items. Upserting them all every poll is acceptable for v1. Do not add a cutoff filter unless polls take longer than 10 seconds.
- `most_recent_update.text` can be several KB of markdown. Truncate to 2000 characters.
- Some incidents have `currently_affected_locations` empty and `previously_affected_locations` filled once resolved. That is why the mapping takes the union.

## Handoff

Next session runs ADR-0004 (AWS). Nothing new is added to shared contracts.
