# ADR-0010: Generic Statuspage provider for Cloudflare, Claude, npm, and Docker

## Goal

Add four more providers with one class. Cloudflare, Claude, and npm run on Atlassian Statuspage. Docker runs on incident.io, which serves the same `api/v2/incidents.json` shape with a few fields missing. Refactor the GitHub provider from ADR-0002 onto the same class so there is one Statuspage parser, not five.

## Non-goals

- No regions. None of these pages carry a region field. Cloudflare lists its points of presence as components, which could feed the map later. That is a separate ADR.
- No component status storage.
- No changes to the schema.

## Outcome shape

```
statusboard/providers/statuspage.py     # StatuspageProvider class and the five instances
statusboard/providers/github.py         # deleted
tests/test_statuspage.py                # replaces tests/test_github.py
tests/fixtures/github_incidents.json    # kept as is
tests/fixtures/docker_incidents.json    # new, trimmed live copy
```

## What carries over from previous specs

From ADR-0001: `Incident`, `Severity`, `Provider` protocol, `register()`, `fetch_bytes`.

From ADR-0002, unchanged and now shared:

- `impact` mapping: `none` and `minor` to `minor`, `major` to `major`, `critical` to `critical`, anything else to `major`.
- `incident_updates` is newest first. `last_message` is index 0's `body`.
- `lists_resolved = True`. `resolved_at` comes from the feed.

## Implementation plan

1. Create `statuspage.py` with `StatuspageProvider(name, host, label)`. `fetch()` reads `https://{host}/api/v2/incidents.json`.
2. Move `_to_incident` from `github.py` into it and add the two fallbacks below.
3. Instantiate and register five providers at import time:

   | name | host | verified 2026-09-05 |
   |---|---|---|
   | github | www.githubstatus.com | Statuspage, 50 incidents |
   | cloudflare | www.cloudflarestatus.com | Statuspage, 50 incidents, 1 open |
   | claude | status.claude.com | Statuspage, 50 incidents |
   | npm | status.npmjs.org | Statuspage, 50 incidents |
   | docker | www.dockerstatus.com | incident.io, 50 incidents, no `started_at`, no `shortlink` |

4. Delete `github.py`. Replace the import line in `providers/__init__.py` with one import of `statuspage`.
5. Rename `tests/test_github.py` to `tests/test_statuspage.py`. Keep every existing test. Point them at the `github` instance.
6. Capture `docker_incidents.json`. Trim to three incidents and two updates each, as ADR-0002 did.

## Behavioural definitions and contracts

Field mapping is ADR-0002's with two fallbacks:

| Incident field | source |
|---|---|
| started_at | `started_at` if present, else `created_at` |
| url | `shortlink` if present and non-empty, else `https://{host}/incidents/{id}` |

Docker's feed, verified live, has these incident keys only: `id`, `name`, `status`, `impact`, `created_at`, `updated_at`, `resolved_at`, `page_id`, `incident_updates`. Update objects carry `body`, `created_at`, `display_at`, `status`. Order is newest first, same as Statuspage.

`external_id` is the page's own `id`. Ids are only unique within one page, and `provider` is part of the primary key, so no prefix is needed.

The `label` is for ADR-0008's tiles: `GitHub`, `Cloudflare`, `Claude`, `npm`, `Docker`.

## Context7 lookups

- `/websites/developer_statuspage_io` for the incident object, already confirmed in ADR-0002.
- incident.io status page API docs, if Context7 has them: confirm the public `api/v2` compatibility and the incident URL pattern. If not found, check that `https://www.dockerstatus.com/incidents/<id>` resolves in a browser and note the result in the README.

## Dependencies

- ADR-0002 complete. This ADR can run any time after it. Run it before ADR-0008 so the dashboard shows every provider.
- No new packages.

## Test plan

`tests/test_statuspage.py`:

- All ADR-0002 tests, unchanged in intent, against the `github` instance.
- The Docker fixture parses. `started_at` equals `created_at`. `url` is `https://www.dockerstatus.com/incidents/<id>`.
- A GitHub item with `shortlink` keeps the shortlink.
- Five providers are registered with the expected names and hosts. Assert on `PROVIDERS` after importing `statusboard.providers`.
- `fetch()` for each instance requests its own host. Use a fake `fetch_bytes` that records the URL.

## Acceptance criteria

- `make test` passes and `tests/test_github.py` no longer exists.
- `make poll` prints one line for each of the five Statuspage providers and exits 0.
- `select provider, count(*) from incident group by provider` shows rows for all five.

## Gotchas

- Cloudflare's feed had one open incident at capture time. Expect open rows for it.
- Do not add `label` to the database. ADR-0008 reads it from the provider object.
- Cloudflare component names include city codes such as `Palmas, Brazil - (PMW)`. Ignore components entirely in this ADR.
- Docker's `resolved_at` can be earlier than `created_at` when they backfill an incident. Store both as given. Do not "fix" the order.

## Handoff

ADR-0008 must list nine providers in its tile order: AWS, GCP, Azure, GitHub, Databricks, Cloudflare, Claude, npm, Docker. ADR-0008 has been updated to say so. ADR-0009's global incident line applies to all Statuspage providers, since none have regions.
