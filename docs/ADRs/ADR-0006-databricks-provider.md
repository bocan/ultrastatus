# ADR-0006: Databricks provider

## Goal

Add Databricks. Databricks runs three separate status.io pages, one per host cloud. One provider fetches all three, merges them, and tags each incident with the host cloud's region codes.

## Non-goals

- No component or container status storage. Green means no open incident.
- No scheduled maintenance.
- No changes to the schema.

## Outcome shape

```
statusboard/providers/databricks.py
tests/test_databricks.py
tests/fixtures/databricks_aws_quiet.json       # live capture with zero incidents
tests/fixtures/databricks_aws_incident.json    # hand-built from the status.io docs sample, one open incident
```

## What carries over from previous specs

From ADR-0001: `Incident`, `Region`, `Severity`, `Provider`, `register()`, `fetch_bytes`, `lists_resolved = False` behaviour.

From ADR-0005: `regions.normalise(cloud, text)` and `regions.lookup(cloud, code)`.

## Implementation plan

1. Define the three pages:

   | key | page id | public page |
   |---|---|---|
   | aws | `5cf02dde58a00904bda41926` | https://status.databricks.com |
   | azure | `5d49ec10226b9e13cb6a422e` | https://status.azuredatabricks.net |
   | gcp | `60087ab5608daf0535dc8e23` | https://status.gcp.databricks.com |

   All ids verified on 2026-09-05.
2. For each page, fetch `https://api.status.io/1.0/status/{page_id}`.
3. Read `result.incidents`. Map each to an `Incident`. Prefix `external_id` with the page key so ids from different pages cannot collide.
4. Concatenate the three lists. If one page fails, raise. The poll loop records the error and skips `mark_missing_resolved` for this provider on that run, so a partial fetch never resolves incidents by mistake. Confirm the ADR-0001 loop behaves that way. If it does not, fix the loop: on exception, do not call `mark_missing_resolved`.
5. Register with `lists_resolved = False`.
6. Import the module from `statusboard/providers/__init__.py`.

## Behavioural definitions and contracts

Verified live shape of the response, top level:

```json
{
  "result": {
    "status_overall": { "updated": "...", "status": "Operational", "status_code": 100 },
    "status": [ { "id": "...", "name": "Compute", "status": "Operational", "status_code": 100,
                  "containers": [ { "id": "...", "name": "US East 1", "status": "Operational", "status_code": 100 } ] } ],
    "incidents": [],
    "maintenance": { "active": [], "upcoming": [] }
  }
}
```

No incident was live at capture time. The status.io developer docs give the incident shape. Fetch them with Context7 and confirm the field names before coding. The expected shape is:

```json
{
  "_id": "5f3e...",
  "name": "Elevated error rates on job launches",
  "datetime_open": "2026-09-05T10:00:00.000Z",
  "components_affected": [ { "_id": "...", "name": "Compute" } ],
  "containers_affected": [ { "_id": "...", "name": "US East 1" }, { "_id": "...", "name": "EU West 1" } ],
  "messages": [
    { "details": "We are investigating ...", "state": 100, "status": 500, "datetime": "2026-09-05T10:05:00.000Z" }
  ],
  "current_status": 500,
  "current_state": 100
}
```

status.io status codes: 100 Operational, 300 Degraded Performance, 400 Partial Service Disruption, 500 Service Disruption, 600 Security Event.

Field mapping:

| Incident field | source |
|---|---|
| provider | `"databricks"` |
| external_id | `page_key + ":" + _id`, for example `aws:5f3e...` |
| title | `name` |
| severity | `current_status` or, if absent, the `status` of the newest message: 300 to `minor`, 400 to `major`, 500 and 600 to `critical`. Anything else to `major`. |
| started_at | `datetime_open` |
| updated_at | newest `messages[].datetime`, else `started_at` |
| resolved_at | `None`. The poll loop resolves incidents that vanish. |
| url | `https://<public page host>/pages/incident/<page_id>/<_id>`. Confirm this pattern in the docs. If the docs show a different pattern, use that. |
| last_message | `details` of the newest message, first 2000 characters. Empty if no messages. |
| regions | for each `containers_affected[].name`, `Region(cloud=page_key, code=regions.normalise(page_key, name))`. Keep only codes where `regions.lookup()` is not None. Deduplicate. |

Message order: check the docs. If `messages` is newest first, take index 0. If oldest first, take index -1. Write the choice as a named constant with a comment.

Container names seen live:

- aws page: `US East 1`, `EU West 2`, `AP Southeast 1`, `US Gov West 1`
- azure page: `Australia East`, `Central US`, `China East 2`
- gcp page: `US-Central1`, `EU-West1`, `Asia-Northeast1`

## Context7 lookups

- status.io API docs: resolve "status.io" and query "Status API GET /1.0/status/:statuspage_id incidents response fields". Confirm `incidents[]` field names, message order, and the incident page URL pattern.

## Dependencies

- ADR-0001 and ADR-0005 complete, `make test` green.
- No new packages.

## Test plan

`tests/test_databricks.py`:

- Quiet fixture for all three pages yields zero incidents.
- Incident fixture on the aws page yields one incident with `external_id` starting `aws:`, severity `critical` for status 500, and regions `[Region("aws","us-east-1"), Region("aws","eu-west-1")]`.
- Same incident body served on the azure page with container `Australia East` yields `Region("azure","australiaeast")`.
- A container name that does not normalise to a known region, for example `Global`, is dropped and does not raise.
- Status code mapping for 300, 400, 500, 600, and 999.
- If the fetch for the gcp page raises, `fetch()` raises and no partial list is returned.
- End to end: poll with the incident fixture, then poll with the quiet fixture. The incident is marked resolved.

Monkeypatch `fetch_bytes` with a function that keys on the URL so each page can return a different fixture.

## Acceptance criteria

- `make test` passes.
- `make poll` prints `databricks: N incidents, 0 newly resolved` and exits 0. N is usually 0.

## Gotchas

- Three HTTP calls per poll. Keep the 20 second timeout per call.
- The aws page RSS feed is titled `AWS`. That is the Databricks-on-AWS page, not Amazon's own status. Do not confuse the two.
- `status_overall.status_code` can be 100 while a maintenance window is active. Ignore maintenance.
- Do not store `components_affected`. Product names are not read anywhere.

## Handoff

Next session runs ADR-0007 (Azure). Nothing new is added to shared contracts. Record the confirmed status.io incident field names in the project `README.md`.
