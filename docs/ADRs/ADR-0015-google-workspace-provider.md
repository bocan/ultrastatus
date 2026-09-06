# ADR-0015: Google Workspace provider

## Goal

Add Gmail, Drive, Meet, Chat, and the rest of Google Workspace. The feed is the same JSON shape as GCP's, minus the location fields. Refactor the GCP provider into one class with two instances rather than copying the module.

## Non-goals

- No regions. The feed carries none, so every incident is global.
- No product-level tiles. One tile for all of Workspace.
- No schema changes.

## Outcome shape

```
statusboard/providers/google.py            # GoogleStatusProvider class and the two instances
statusboard/providers/gcp.py               # deleted
tests/test_google.py                       # replaces tests/test_gcp.py
tests/fixtures/gcp_incidents.json          # kept as is
tests/fixtures/gcp_incidents.README.md     # kept as is
tests/fixtures/workspace_incidents.json    # new, trimmed live copy
statusboard/render.py                      # one line in GROUPS, one in SOURCE_URLS
```

## What carries over from previous specs

From ADR-0003, now shared by both instances:

- `status_impact` mapping: `SERVICE_INFORMATION` to `minor`, `SERVICE_DISRUPTION` to `major`, `SERVICE_OUTAGE` to `critical`, anything else to `major`.
- `external_id` is `id`, `title` is `external_desc`, `started_at` is `begin`, `updated_at` is `modified`, `resolved_at` is `end` or None, `last_message` is `most_recent_update.text` cut to 2000 characters.
- Regions are the union of `currently_affected_locations` and `previously_affected_locations` ids. When both keys are absent, regions are `[]`.
- `lists_resolved = True`.

From ADR-0014: the `Workplace` group and the registration guard.

From ADR-0010: the pattern of one class, several registered instances, each with `name`, `host` or URL, and `label`.

## Implementation plan

1. Create `google.py` with `GoogleStatusProvider(name, feed_url, incident_url_base, label)`. Move `_to_incident` and `_regions` from `gcp.py` into it unchanged, except that `_regions` must tolerate missing keys and `url` is built from the instance's base.
2. Register two instances:

   | name | feed_url | incident_url_base | label |
   |---|---|---|---|
   | gcp | `https://status.cloud.google.com/incidents.json` | `https://status.cloud.google.com/` | GCP |
   | google-workspace | `https://www.google.com/appsstatus/dashboard/incidents.json` | `https://www.google.com/appsstatus/dashboard/` | Google Workspace |

3. Delete `gcp.py`. Replace its import in `providers/__init__.py` with `google`.
4. Add `("google-workspace", "Google Workspace")` to the Workplace group in `render.GROUPS` and its dashboard URL `https://www.google.com/appsstatus/dashboard/` to `SOURCE_URLS`.
5. Rename `tests/test_gcp.py` to `tests/test_google.py`. Keep every GCP test against the `gcp` instance. Add the Workspace tests.
6. Capture `workspace_incidents.json`. Trim to four incidents, two updates each, text cut to 300 characters, as ADR-0003 did.

## Behavioural definitions and contracts

Verified live on 2026-09-06. The Workspace feed returned 46 incidents, 416 KB. Keys per incident:

```
affected_products, begin, created, end, external_desc, id, modified,
most_recent_update, number, service_key, service_name, severity,
status_impact, updates, uri
```

That is the GCP key set without `currently_affected_locations` and `previously_affected_locations`. `status_impact` values seen: `SERVICE_INFORMATION` 21, `SERVICE_DISRUPTION` 23, `SERVICE_OUTAGE` 2. `uri` looks like `incidents/y2ufhCB886p7rveYNnko`.

`external_desc` on Workspace is often a multi-paragraph markdown block starting `**Summary:**`. Use it as the title anyway, but cut the title to its first line with the `**Summary:**` prefix stripped, then to 200 characters. Apply the same rule to the `gcp` instance. GCP titles are single lines, so nothing changes for them.

Provider name is `google-workspace`. Labels come from the instance. The tile sits in the Workplace group.

## Context7 lookups

- None. Context7 has no entry for either Google status feed, as ADR-0003 found. The live feed is the reference.

## Dependencies

- ADR-0014 complete.
- No new packages.

## Test plan

`tests/test_google.py`:

- All ADR-0003 tests, unchanged in intent, against the `gcp` instance.
- Workspace fixture parses to four incidents, every `regions == []`, `provider == "google-workspace"`, `url` starts with `https://www.google.com/appsstatus/dashboard/incidents/`.
- A Workspace item whose `external_desc` starts with `**Summary:**\nGoogle Chat users ...` gives the title `Google Chat users ...`, first line only, no markdown prefix.
- A title longer than 200 characters is cut to 200.
- Both instances are registered with the expected feed URLs. Each `fetch()` requests its own URL, checked with a fake `fetch_bytes` that records the URL.
- `tests/test_groups.py` from ADR-0014 passes without change, which proves the group entry exists.

## Acceptance criteria

- `make test` passes and `tests/test_gcp.py` no longer exists.
- `make poll` prints `google-workspace: N incidents, 0 newly resolved`.
- The Workplace group appears on the page with one tile.

## Gotchas

- The Workspace feed is 416 KB and lists about 46 incidents. Upserting them all each poll is fine.
- Workspace `external_desc` can contain newlines. The title rule above exists because of that. Do not store the whole block as the title.
- The `google` module name shadows nothing in the standard library, but do not name it `google.py` at the package root. It lives under `providers/`.

## Handoff

ADR-0016 adds Slack to the same Workplace group.
