# ADR-0011: Region filter, "my regions" first

## Goal

Let the operator name the regions they use. The dashboard then answers "is anything wrong where I run" before it answers "is anything wrong anywhere". Tiles, tables, and the map all change to put the operator's regions first and push everything else back.

## Non-goals

- No per-service filtering. Regions only.
- No filtering at poll time. The database keeps every incident. The filter applies at render time only.
- No user accounts or per-viewer settings. One config file, one view.
- No schema changes.
- No change to the Statuspage providers. GitHub, Cloudflare, Claude, npm, and Docker have no regions and are always "mine".

## Outcome shape

```
statusboard.example.toml               # committed example, copy to statusboard.toml
statusboard/config.py                  # load and validate the config
statusboard/render.py                  # split incidents into mine and elsewhere
statusboard/mapgen.py                  # Marker gains a mine flag
statusboard/templates/index.html.j2    # new sections and tile lines
tests/test_config.py
tests/test_render.py                   # extended
tests/test_mapgen.py                   # extended
.gitignore                             # add statusboard.toml
README.md                              # config section
```

## What carries over from previous specs

From ADR-0001: `Incident.regions` as `list[Region(cloud, code)]`. Databricks incidents carry their host cloud's regions, so the filter covers them for free.

From ADR-0005: `regions.lookup(cloud, code)` and `regions.all_regions()`. Canonical codes are `us-east-1`, `europe-west2`, `uksouth`.

From ADR-0008: `build_context(conn, now)` returns `providers`, `open`, `resolved`, `global_incidents`. The provider `level` vocabulary is `ok | minor | major | critical | stale`. Incident dicts carry `region_labels`.

From ADR-0009: `marker_layout(regions, levels, titles, stale_clouds)` returns `Marker` objects. `render_svg` writes one `<circle>` per marker with a `marker-<level>` class.

## Implementation plan

1. Write `statusboard.example.toml` and commit it. Add `statusboard.toml` to `.gitignore`.
2. Write `config.py` with `load_config(path=None) -> Config`. Use `tomllib` from the standard library.
3. In `render.py`, load the config once in `build_context`. Classify every open and resolved incident as `mine` or `elsewhere`. Compute tile levels from `mine` plus global incidents only.
4. In `mapgen.py`, add `mine: bool` to `Marker`. `marker_layout` takes a `my_regions: set[tuple[str, str]]` argument. Markers not in the set get class `marker-other`, radius 4, and opacity 0.4 via CSS. Markers in the set get radius 6. When the set is empty, every marker is `mine` and the map looks as it does today.
5. In the template, split the open table into "Open in your regions" and a collapsed "Open elsewhere" `<details>`. Do the same for resolved. Add a one-line status banner at the top.
6. Update ADR-0008's tests for the new tile fields and the banner text.
7. Document the config in the project `README.md`.

## Behavioural definitions and contracts

### Config file

Path from `STATUSBOARD_CONFIG`, default `./statusboard.toml`. A missing file is not an error. It means "no filter", and the page renders as it does today.

```toml
# statusboard.toml
[regions]
aws   = ["eu-west-2", "us-east-1"]
gcp   = ["europe-west2"]
azure = ["uksouth", "westeurope"]
```

```python
@dataclass(frozen=True)
class Config:
    my_regions: frozenset[tuple[str, str]]   # {("aws", "eu-west-2"), ...}

    @property
    def active(self) -> bool:                  # False when my_regions is empty

def load_config(path: str | None = None) -> Config
```

Validation on load. Each of these raises `ConfigError` with a message that names the bad value and the file:

- A cloud key that is not `aws`, `gcp`, or `azure`.
- A region code that `regions.lookup()` does not know. The message lists up to five near matches by prefix so a typo like `eu-west2` gets `eu-west-2` suggested.
- A value that is not a list of strings.

An empty `[regions]` table, or a file with no `[regions]` table, loads as inactive. That is not an error.

### Classifying incidents

An incident is **mine** when any of these hold:

- The config is inactive.
- It has no regions at all (a global incident, or a Statuspage provider).
- None of its regions is in the region table (for example GCP's `global` location). These are already treated as global by ADR-0009.
- At least one of its regions is in `my_regions`.

Otherwise it is **elsewhere**.

### Context changes

`build_context` gains and changes these keys:

```python
{
  "filter_active": True,
  "my_region_labels": ["aws eu-west-2", "aws us-east-1", "gcp europe-west2", ...],   # sorted
  "all_clear": True,                # no open incident is mine
  "open": [...],                    # now only mine, same dict shape
  "open_elsewhere": [...],          # the rest
  "resolved": [...],                # mine, last 7 days
  "resolved_elsewhere": [...],
  "providers": [ { ..., "open_count": 2, "elsewhere_count": 3 }, ... ],
}
```

Provider tile rules:

- `level` is the worst severity among that provider's **mine** incidents. `elsewhere` incidents never raise the level. Staleness rules from ADR-0008 are unchanged.
- `open_count` counts mine. `elsewhere_count` counts the rest. When the filter is inactive, `elsewhere_count` is 0 for every provider.
- `global_incidents` is unchanged. Every global incident is mine by definition.

### Page changes

1. **Banner** under the header. When the filter is active and `all_clear`: `All clear in your regions: aws eu-west-2, aws us-east-1, gcp europe-west2`. When active and not clear: `N open incidents in your regions`. When inactive: no banner.
2. **Tiles.** Cloud tiles show `2 open in your regions` and a muted second line `3 elsewhere` when that count is non-zero. Non-cloud tiles keep `N open incidents`.
3. **Map.** Mine markers are radius 6 at full opacity. Others are radius 4 at 0.4 opacity with class `marker-other`. Draw order stays: markers with an incident last, and among those, mine after elsewhere. Legend gains `large = your regions`.
4. **Tables.** `Open in your regions` replaces `Open incidents`. Below it, `<details><summary>Open elsewhere (3)</summary>` holds the rest, collapsed. Same for resolved. Empty states: `No open incidents in your regions.` and no `<details>` block at all when the elsewhere list is empty.
5. When the filter is inactive, headings and wording revert to ADR-0008's exactly, so the no-config page is unchanged.

### Sorting

Both open tables sort by severity descending, then `updated_at` descending. This replaces ADR-0008's start-time order. Resolved tables keep `resolved_at` descending.

## Context7 lookups

- `/python/cpython`: `tomllib.load` and its `TOMLDecodeError`.
- `/websites/jinja_palletsprojects_en_stable`: `{% if %}` with `else`, and the `sort` filter with `attribute=` and `reverse=True`, in case sorting is done in the template. Prefer sorting in Python.

## Dependencies

- ADR-0008 and ADR-0009 complete.
- Python 3.11 or newer for `tomllib`. The project already requires 3.12.
- No new packages.

## Test plan

`tests/test_config.py`:

- Missing file gives an inactive config.
- The example file loads and is active with the expected set.
- Empty `[regions]` gives inactive.
- Unknown cloud key raises `ConfigError` naming it.
- Unknown region code raises `ConfigError` and the message contains the near match `eu-west-2` for `eu-west2`.
- A string instead of a list raises `ConfigError`.
- `STATUSBOARD_CONFIG` env var is honoured. Use `monkeypatch.setenv` and `tmp_path`.

`tests/test_render.py` additions. Use a `config` fixture that monkeypatches `render.load_config` to return a fixed `Config`:

- Inactive config: context keys match ADR-0008 exactly, `open_elsewhere == []`, `filter_active is False`.
- Active `{("aws","eu-west-2")}`: an aws `us-east-1` critical incident goes to `open_elsewhere`, aws tile level is `ok`, `elsewhere_count` is 1, `open_count` is 0.
- Same config: an aws `eu-west-2` minor incident makes the aws tile `minor` and `all_clear` False.
- A GitHub incident with no regions is mine under any config.
- A GCP incident whose only region is `global` is mine.
- A Databricks incident on `aws eu-west-2` is mine and colours the aws marker, as before.
- Open table sorts critical above minor, and newer above older within a severity.
- Rendered HTML contains `All clear in your regions` when nothing is mine, contains `<details>` only when elsewhere is non-empty, and contains neither when the config is inactive.

`tests/test_mapgen.py` additions:

- With `my_regions` empty, every marker has `mine is True`.
- With one region in the set, that marker is `mine`, the others are not, and the SVG has exactly one circle without `marker-other`.
- Draw order: an elsewhere marker with an incident sits before a mine marker with an incident.

## Acceptance criteria

- `make test` passes.
- With no `statusboard.toml`, `make refresh` produces a page identical in structure to before this ADR. Compare headings.
- With the example config copied to `statusboard.toml`, the page shows the banner, large markers for the listed regions, and the elsewhere sections.
- A typo in the config makes `make render` exit 1 with a message that names the bad code and suggests the right one.

## Gotchas

- Do not filter at poll time. Later config changes must apply to history already stored.
- Keep `global_incidents` as is. Do not filter it.
- Sorting by severity means AWS's long-running Middle East events float to the top when they are mine. That is correct.
- `tomllib` returns plain dicts and lists. Validate types; do not trust them.
- Load the config once per render, not once per incident.

## Handoff

ADR-0012 (zoomable map) uses `my_regions` to offer a "My regions" zoom preset that frames the bounding box of those markers. It reads `Marker.mine` and `my_region_labels` from this ADR.
