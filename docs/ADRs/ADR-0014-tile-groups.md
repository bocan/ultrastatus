# ADR-0014: Group the provider tiles

## Goal

Nine tiles in one row already wrap awkwardly. More providers are coming: Google Workspace and Slack next, then Snowflake, dbt, OpenAI, and Atlassian. Put tiles into named groups, each with a heading and a group-level status chip, so the row stays readable at twenty providers. Add a guard so a new provider cannot be registered without a group.

## Non-goals

- No collapsing or hiding of groups. Every tile stays visible.
- No per-group configuration file. Groups are fixed in code.
- No change to the incident tables, the map, or the schema.
- No change to provider modules. Grouping lives in the renderer.

## Outcome shape

```
statusboard/render.py                  # GROUPS replaces PROVIDER_ORDER as the source of order
statusboard/templates/index.html.j2    # one tile row per group with a heading
tests/test_render.py                   # updated expectations, new group tests
tests/test_groups.py                   # the registration guard
```

## What carries over from previous specs

From ADR-0008: `PROVIDER_ORDER`, the provider dict shape (`name`, `label`, `level`, `open_count`, `elsewhere_count`, `has_regions`, `polled_at`, `polled_ago`, `poll_error`, `source_url`), the level vocabulary `ok | minor | major | critical | stale`, and `SOURCE_URLS`.

From ADR-0011: `open_count` counts mine, `elsewhere_count` counts the rest, and `level` comes from mine only.

From ADR-0001: `PROVIDERS`, the registry of every provider by name.

## Implementation plan

1. In `render.py`, replace `PROVIDER_ORDER` with `GROUPS`, an ordered list of `(group_label, [(provider_name, default_label), ...])`. Derive `PROVIDER_ORDER` from it so nothing else changes.
2. Extend `build_context` to return `groups`, a list of group dicts, each holding its provider dicts in order. Keep the flat `providers` list too. The footer and existing tests use it.
3. In the template, render one `<section class="group">` per group with an `<h2>`, a level chip, and the tile grid. Drop the single flat tile grid.
4. Write `tests/test_groups.py` with the registration guard.
5. Update `tests/test_render.py` for the new order.

## Behavioural definitions and contracts

### Groups

```python
GROUPS: list[tuple[str, list[tuple[str, str]]]] = [
    ("Clouds", [("aws", "AWS"), ("gcp", "GCP"), ("azure", "Azure")]),
    ("Data platforms", [("databricks", "Databricks")]),
    ("AI", [("claude", "Claude")]),
    ("Developer tooling", [("github", "GitHub"), ("cloudflare", "Cloudflare"), ("npm", "npm"), ("docker", "Docker")]),
    ("Workplace", []),
]
PROVIDER_ORDER = [pair for _, pairs in GROUPS for pair in pairs]
```

ADR-0015 adds `("google-workspace", "Google Workspace")` to Workplace. ADR-0016 adds `("slack", "Slack")` after it. Later ADRs add Snowflake, dbt, and Airbyte to Data platforms, OpenAI to AI, and Atlassian to Workplace.

A group with no providers is not rendered. That lets Workplace exist in this ADR before its first member arrives.

### Registration guard

Every provider in `PROVIDERS` must appear in exactly one group, and every name in `GROUPS` must be a registered provider. `tests/test_groups.py` asserts both. Adding a provider module without a group entry, or a group entry without a module, fails the suite with a message naming the provider.

### Context

`build_context` gains:

```python
"groups": [
  {
    "label": "Clouds",
    "level": "critical",          # worst level among the group's providers, see below
    "open_count": 2,              # sum of the providers' open_count
    "providers": [ ...provider dicts in order... ],
  },
  ...
]
```

Group level rule. Take the providers' levels. If any is `critical`, `major`, or `minor`, the group level is the worst of those. Else if every provider is `stale`, the group is `stale`. Else `ok`. A single stale provider among healthy ones does not make the group stale. The tile still shows it.

The flat `providers` list stays, in `PROVIDER_ORDER` order.

### Page

Between the legend and the tables, one section per non-empty group:

```html
<section class="group">
  <h2>Clouds <span class="chip level-critical">critical</span> <span class="muted">2 open</span></h2>
  <div class="tiles"> ...tiles as today... </div>
</section>
```

- The `open` word follows ADR-0011: `2 open in your regions` when the filter is active and the group has regional providers, else `2 open`. When the count is zero, omit the muted text.
- Tiles keep their exact markup from ADR-0008 and ADR-0011.
- Group headings use the same font size as the table headings. Tiles stay the same size. Groups stack vertically with a 1.5 rem gap.
- On a narrow screen tiles wrap within their group as before.

### Order

Clouds, Data platforms, AI, Developer tooling, Workplace. This changes `PROVIDER_ORDER` from the ADR-0008 order. The new flat order is `aws, gcp, azure, databricks, claude, github, cloudflare, npm, docker`. Tests that pinned the old order change to this one. The database and the poll loop are unaffected. The poll loop iterates the registry, not this list.

## Context7 lookups

- `/websites/jinja_palletsprojects_en_stable`: nested `{% for %}` loops and `loop` variables, if needed. Nothing else.

## Dependencies

- ADR-0011 complete.
- No new packages.

## Test plan

`tests/test_groups.py`:

- `set(PROVIDERS) == {name for group in GROUPS for name, _ in group}`. The assertion message lists the difference in both directions.
- No provider name appears in two groups.
- `PROVIDER_ORDER` equals the groups flattened.

`tests/test_render.py`:

- Update `EXPECTED_NAMES` to the new order.
- `groups` has four entries when Workplace is empty. Labels and provider names match `GROUPS`.
- Group level: aws critical and gcp ok gives Clouds `critical`. All three clouds stale gives `stale`. aws stale, gcp ok, azure ok gives `ok`.
- Group `open_count` sums its providers.
- The rendered page has one `<section class="group">` per non-empty group, headings in order, and still exactly nine tiles.
- With the filter active and one aws incident in my regions, the Clouds heading reads `1 open in your regions`.

## Acceptance criteria

- `make test` passes.
- `make refresh` renders four headed groups. The screenshot shows Clouds first and Developer tooling last.
- Temporarily register a fake provider in a scratch test without a group entry and confirm `test_groups.py` fails with the provider's name in the message. Do not commit the scratch test.

## Gotchas

- The footer links iterate the flat `providers` list. Keep it.
- The map's `stale_clouds` logic uses provider names, not groups. Do not touch it.
- Keep `PROVIDER_ORDER` as a module attribute. `tests/test_render.py` imports it.
- The chip in the group heading uses the shared `.chip` class from ADR-0013. Do not scope it.

## Handoff

ADR-0015 and ADR-0016 each add one line to the Workplace group. They must run after this ADR, or the registration guard fails.
