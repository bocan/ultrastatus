# ADR-0004: AWS provider

## Goal

Add the AWS provider from the public JSON feed behind the AWS Health Dashboard. This is the first provider whose feed lists only open incidents, so it exercises `mark_missing_resolved`.

## Non-goals

- No AWS Health API. That needs credentials and a paid support plan.
- No per-service RSS feeds. The JSON feed covers every region in one call.
- No storage of the `impacted_services` list. Only the event summary and region are stored.
- No changes to the schema.

## Outcome shape

```
statusboard/providers/aws.py
tests/test_aws.py
tests/fixtures/aws_currentevents.json     # saved live copy, re-encoded as UTF-8
```

## What carries over from previous specs

From ADR-0001:

- `Incident`, `Region`, `Severity`, `Provider`, `register()`, `fetch_bytes`
- `lists_resolved = False` makes the poll loop resolve incidents that vanish from the feed.
- AWS region code form: lowercase hyphenated, for example `us-east-1`.

## Implementation plan

1. Fetch `https://health.aws.amazon.com/public/currentevents`.
2. Decode. The response is UTF-16 with a byte order mark. Check the first two bytes for `\xff\xfe` or `\xfe\xff` and decode as `utf-16`. Otherwise decode as `utf-8`. Write a small `_decode(b: bytes) -> str` helper and test both branches.
3. Parse the JSON array. Map each item to an `Incident`.
4. Register with `lists_resolved = False`.
5. Import the module from `statusboard/providers/__init__.py`.
6. Save the live response as the fixture. Re-encode it as UTF-8 so the fixture is diffable. Keep a second tiny fixture `aws_utf16_sample.bin` of one event encoded as UTF-16 with BOM for the decode test.

## Behavioural definitions and contracts

Feed shape, verified 2026-09-05. This endpoint is undocumented. Treat every field as best effort.

```json
[
  {
    "date": "1772369485",                       // unix seconds, as a string
    "arn": "arn:aws:health:me-central-1::event/MULTIPLE_SERVICES/AWS_MULTIPLE_SERVICES_OPERATIONAL_ISSUE/AWS_MULTIPLE_SERVICES_OPERATIONAL_ISSUE_5E6B8_EF2498889B5",
    "region_name": "UAE",
    "status": "3",                              // "1" info, "2" degradation, "3" disruption
    "service": "multipleservices-me-central-1",
    "service_name": "Multiple services",
    "summary": "Increased Error Rates",
    "event_log": [
      { "summary": "Increased Error Rates", "message": "We are investigating ...", "status": 1, "timestamp": 1772369485 },
      ...
    ],
    "impacted_services": { "s3-me-central-1": { "service_name": "...", "current": "3", "max": "3" } },
    "impacted_service_status_changes": [ ... ]
  }
]
```

`event_log` is oldest first. The last entry is the newest.

Field mapping:

| Incident field | source |
|---|---|
| provider | `"aws"` |
| external_id | `arn` |
| title | `service_name + ": " + summary`, for example `Multiple services: Increased Error Rates` |
| severity | `status`: `"1"` to `minor`, `"2"` to `major`, `"3"` to `critical`. Any other value to `major`. |
| started_at | `date` as int, unix seconds, UTC |
| updated_at | `event_log[-1].timestamp` if the log is non-empty, else `started_at` |
| resolved_at | always `None`. The poll loop resolves missing events. |
| url | `"https://health.aws.amazon.com/health/status"`. There is no per-event public URL. |
| last_message | `event_log[-1].message`, first 2000 characters. Empty string if the log is empty. |
| regions | the region field of the ARN. Split `arn` on `:`. Index 3 is the region. If it is non-empty, emit `[Region("aws", region)]`. If empty, the event is global, emit `[]`. |

Timestamps: `event_log[].timestamp` is unix seconds. `impacted_service_status_changes[].timestamp` is unix milliseconds. Only the first is used. Do not read the second.

## Context7 lookups

- None documented. Search the web for "health.aws.amazon.com public currentevents" if the shape has changed. Record what you find in the project `README.md`.

## Dependencies

- ADR-0001 complete, `make test` green.
- No new packages.

## Test plan

`tests/test_aws.py`:

- `_decode` handles UTF-16 LE with BOM, UTF-16 BE with BOM, and plain UTF-8.
- Fixture parses. Each `external_id` is the ARN.
- Region from ARN: `arn:aws:health:me-central-1::event/...` gives `me-central-1`. An ARN with an empty region field gives `[]`.
- Severity mapping for `"1"`, `"2"`, `"3"`, and `"9"`.
- `updated_at` comes from the last log entry. An event with an empty `event_log` falls back to `started_at` and an empty message.
- End to end: poll with the fixture, then poll with a fixture that drops one event. The dropped event has `resolved_at` set. The remaining one is open.

## Acceptance criteria

- `make test` passes.
- `make poll` prints `aws: N incidents, 0 newly resolved` with the live feed. N may be 0 on a quiet day. That is a pass.

## Gotchas

- The `Content-Type` header says `application/json;charset=utf-16`. Do not trust the header. Sniff the BOM.
- Events can stay in this feed for months. The two events seen on 2026-09-05 began in March 2026. That is correct behaviour, not a bug.
- `date` is a string, `event_log[].timestamp` is an int. Cast both with `int()`.
- The feed may also list scheduled or informational events. They arrive with `status: "1"` and map to `minor`. Do not filter them out.

## Handoff

Next session runs ADR-0005 (region table). No new shared contracts from this ADR.
