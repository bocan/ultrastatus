# ADR-0008: Static HTML dashboard and cron

## Goal

Add a `render` command that reads SQLite and writes one self-contained HTML page. Add cron instructions so `poll` then `render` run every few minutes with no server process.

## Non-goals

- No web server, no API, no JavaScript framework.
- No world map. ADR-0009 adds it inside the page this ADR builds.
- No history charts or uptime percentages.
- No authentication. The output is a file. Serve it however you like.

## Outcome shape

```
statusboard/render.py
statusboard/templates/index.html.j2
site/index.html                     # generated, git-ignored
docs/cron.md
Makefile                            # new targets: render, refresh
```

## What carries over from previous specs

From ADR-0001, the only read helpers:

```python
db.open_incidents(conn) -> list[Incident]
db.recent_resolved(conn, since) -> list[Incident]
db.last_polls(conn) -> dict[provider, (polled_at, error | None)]
```

The nine provider names: `aws`, `gcp`, `azure`, `github`, `databricks`, `cloudflare`, `claude`, `npm`, `docker`. The last four come from ADR-0010.

## Implementation plan

1. Add `jinja2` as a runtime dependency. It is the only runtime package in the project.
2. Write `render.py` with `build_context(conn, now)` and `render(conn, out_dir, now)`.
3. Write the template. Inline all CSS in a `<style>` block. No external assets.
4. Add the CLI command `python -m statusboard render --out site` (default `site`).
5. Add Makefile targets `render` and `refresh`. `refresh` runs `poll` then `render` and exits non-zero if either fails.
6. Write `docs/cron.md`.
7. Add `site/` to `.gitignore`.

## Behavioural definitions and contracts

### build_context

Returns a plain dict the template consumes:

```python
{
  "generated_at": "2026-09-05T20:10:00Z",
  "providers": [
    {
      "name": "aws",
      "label": "AWS",
      "level": "critical",          # "ok" | "minor" | "major" | "critical" | "stale"
      "open_count": 2,
      "polled_at": "2026-09-05T20:09:31Z",
      "poll_error": None,           # str when the last poll failed
    },
    ...
  ],
  "open": [ ...Incident as dict, plus "region_labels": ["aws us-east-1", ...] ],
  "resolved": [ ...same shape, last 7 days ],
}
```

Rules:

- Provider order is fixed: AWS, GCP, Azure, GitHub, Databricks, Cloudflare, Claude, npm, Docker. Tiles wrap onto a second row on narrow screens.
- `level` is the worst severity among that provider's open incidents. `ok` when there are none.
- `level` is `stale` when the last poll is older than 15 minutes or its `error` is not None, regardless of incidents. A stale provider still lists its open incidents.
- A provider with no `poll_run` row is `stale` with `polled_at: None`.
- `resolved` is `recent_resolved(conn, now - 7 days)`.
- Timestamps in the context are ISO strings. The template shows them as `2026-09-05 20:09 UTC`.
- `region_labels` is `f"{cloud} {code}"` per region, for display only.

### Page layout, top to bottom

1. Header: `Cloud status`, generated time, and a note `refreshes every 2 minutes` if the meta refresh is set.
2. `<meta http-equiv="refresh" content="120">`.
3. A row of nine provider tiles. Each tile shows the label, a large coloured status word, open incident count, and `polled 3 min ago` or the error text.
4. `Open incidents` table: provider, severity, title linked to `url` when present, started, updated, regions, last message truncated to 240 characters with a `title` attribute holding the full text.
5. `Resolved in the last 7 days` table: same columns plus resolved time.
6. Footer: links to the nine source status pages.

An empty open table shows `No open incidents.` An empty resolved table shows `Nothing resolved in the last 7 days.`

### Colours

Use CSS custom properties. Define light values on `:root` and dark values under `@media (prefers-color-scheme: dark)`.

| level | meaning | light | dark |
|---|---|---|---|
| ok | operational | `#1a7f37` on `#dafbe1` | `#3fb950` on `#12261e` |
| minor | informational or degraded | `#9a6700` on `#fff8c5` | `#d29922` on `#2b2410` |
| major | partial disruption | `#bc4c00` on `#fff1e5` | `#f0883e` on `#2f1a0a` |
| critical | outage | `#cf222e` on `#ffebe9` | `#f85149` on `#2e1214` |
| stale | no fresh data | `#57606a` on `#eaeef2` | `#8b949e` on `#21262d` |

Never rely on colour alone. Every tile and severity cell also shows the level as text.

### Makefile and cron

```
make render     # python -m statusboard render --out site
make refresh    # make poll && make render
```

`docs/cron.md` documents this crontab line and the two things people get wrong: absolute paths and the `PATH` for `uv`.

```
*/2 * * * * cd /Users/chris/Play/statusboard && PATH=/opt/homebrew/bin:$PATH make refresh >> /tmp/statusboard.log 2>&1
```

Also note: `poll` exits 1 when one provider fails but still writes the others, so `refresh` should run `render` even when `poll` fails. Implement `refresh` as `poll; render` and return the poll exit code at the end.

## Context7 lookups

- `/pallets/jinja`: `Environment`, `PackageLoader`, autoescape, `select_autoescape`, custom filters for date formatting.

## Dependencies

- ADR-0001 through ADR-0007 complete.
- New runtime package: `jinja2`.

## Test plan

`tests/test_render.py`:

- `build_context` with an empty database gives nine providers, all `stale`, `polled_at` None, empty lists.
- With one open `critical` aws incident and a fresh poll, aws is `critical`, the others are `ok` or `stale` as their polls dictate.
- A provider whose last poll is 20 minutes old is `stale` even with no incidents.
- A provider whose last poll has an error is `stale` and the context carries the error text.
- `resolved` excludes an incident resolved 8 days ago.
- `render` writes `site/index.html`. The file contains `No open incidents.` for an empty database, and contains the incident title and a link to its `url` when one exists.
- The output has no `<script` tag.

## Acceptance criteria

- `make test` passes.
- `make refresh` produces `site/index.html`. Opening it in a browser shows nine tiles and both tables.
- The page validates as HTML with no external requests. Check the browser network tab: one request only.

## Gotchas

- Jinja autoescape must be on. Incident text comes from third parties.
- Truncate `last_message` in Python, not in the template, so the `title` attribute keeps the full text.
- `now` is a parameter of `build_context` so tests can pin it.
- Do not add a `data.json` output. Nothing reads it.

## Handoff

Next session runs ADR-0009 (world map). It adds a block to `index.html.j2` between the header and the tiles, and adds `map_svg` to the context. Keep the template structure simple so that insertion is one line.
