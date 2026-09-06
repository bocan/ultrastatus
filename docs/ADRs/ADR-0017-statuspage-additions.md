# ADR-0017: dbt Cloud, OpenAI, Atlassian, and PyPI on the Statuspage class

## Goal

Add four providers that serve the Statuspage v2 incidents feed. Each is one instance of `StatuspageProvider` from ADR-0010 plus one entry in a tile group. No new parsing.

Airbyte and Snowflake were on the same list but need their own ADRs. Airbyte runs on Instatus, which serves no incidents JSON. Snowflake needs region mapping. See ADR-0018 and ADR-0019.

## Non-goals

- No regions. None of the four pages carry a region field.
- No component storage.
- No schema changes.

## Outcome shape

```
statusboard/providers/statuspage.py        # four more instances
statusboard/render.py                      # four group entries, four source URLs
tests/test_statuspage.py                   # registry and routing assertions extended
```

## What carries over from previous specs

From ADR-0010: `StatuspageProvider(name, host, label)`, the `impact` mapping, the newest-first `incident_updates` rule, and the two fallbacks for pages that omit `started_at` and `shortlink`.

From ADR-0014: `GROUPS` in `render.py` and the registration guard in `tests/test_groups.py`.

## Implementation plan

1. Append four instances to `STATUSPAGE_PROVIDERS`:

   | name | host | label | group | verified 2026-09-06 |
   |---|---|---|---|---|
   | dbt | status.getdbt.com | dbt Cloud | Data platforms | 25 incidents, incident.io shape, no `started_at`, no `shortlink` |
   | openai | status.openai.com | OpenAI | AI | 25 incidents, incident.io shape |
   | atlassian | status.atlassian.com | Atlassian | Workplace | 34 incidents, classic Statuspage |
   | pypi | status.python.org | PyPI | Developer tooling | 50 incidents, classic Statuspage |

2. Add the group entries in `render.GROUPS`, in this order within each group: Data platforms gets `dbt` after `databricks`; AI gets `openai` after `claude`; Workplace gets `atlassian` after `slack`; Developer tooling gets `pypi` after `docker`.
3. Add source URLs: `https://status.getdbt.com/`, `https://status.openai.com/`, `https://status.atlassian.com/`, `https://status.python.org/`.
4. Extend the registry and routing tests.

## Behavioural definitions and contracts

Nothing new. The incident.io fallbacks from ADR-0010 cover dbt and OpenAI: `started_at` falls back to `created_at`, and `url` falls back to `https://<host>/incidents/<id>`.

Labels: `dbt Cloud`, `OpenAI`, `Atlassian`, `PyPI`. The PyPI page calls itself `Python Infrastructure` and covers PyPI, docs.python.org, and the mirrors. The tile says `PyPI` because that is the part that breaks builds.

## Context7 lookups

- None. ADR-0010 confirmed the Statuspage incident object and ADR-0010's README note records the incident.io behaviour.

## Dependencies

- ADR-0010 and ADR-0014 complete.
- No new packages.

## Test plan

`tests/test_statuspage.py`:

- The nine-provider registry assertion becomes a table with the four new names, hosts, and labels.
- The per-host routing test covers all nine and asserts the request order.
- A synthetic incident.io-shaped item served for `status.getdbt.com` gets `started_at == created_at` and the `/incidents/<id>` URL. Reuse the Docker fixture with the host swapped, no new fixture file.

`tests/test_groups.py` passes unchanged, which proves the four group entries.

## Acceptance criteria

- `make test` passes.
- `make poll` prints a line for each of `dbt`, `openai`, `atlassian`, and `pypi` and exits 0.
- The page shows the four new tiles in their groups, and the flat tile count in `tests/test_render.py` is updated to 15.

## Gotchas

- `EXPECTED_NAMES` in `tests/test_render.py` pins the flat order. Update it, do not remove the assertion.
- Statuspage rate limit is 1 request per second per page. Four more pages add four requests per poll. Still trivial.
- OpenAI's page has had brief periods of returning HTML on the API path during their own incidents. The poll loop records the error and moves on. Do not add retries here.

## Handoff

ADR-0018 adds Snowflake to Data platforms with region mapping. ADR-0019 adds Airbyte from its Instatus RSS.
