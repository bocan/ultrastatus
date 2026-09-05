# ADR-0001: Project skeleton, data model, and SQLite store

## Goal

Create the Python project that every later ADR builds on. Deliver:

- A package layout, `pyproject.toml`, and a `Makefile`.
- One normalised `Incident` model that all providers emit.
- A SQLite schema with only the columns that this ADR and later ADRs read or write.
- A provider registry and a `poll` command that runs every registered provider and writes to SQLite.
- A test suite that runs with `make test`.

No real provider is built here. A fake provider proves the pipeline end to end.

## Non-goals

- No HTTP calls to real status pages. Later ADRs add providers.
- No dashboard, HTML, or map. See ADR-0008 and ADR-0009.
- No region lookup table. See ADR-0005.
- No retention or deletion of old rows.
- No component tables. A provider is green when it has no open incident. Do not add a components table.
- No speculative columns. Every column in the schema is read or written by code in this ADR or a named later ADR. Do not add columns "for later".

## Outcome shape

```
statusboard/
  Makefile
  pyproject.toml
  README.md
  statusboard/
    __init__.py
    __main__.py          # python -m statusboard
    cli.py               # argparse: poll, init-db
    model.py             # Incident, Region dataclasses, Severity
    db.py                # connect, init_schema, upsert_incident, record_poll, mark_missing_resolved, queries
    http.py              # fetch_bytes(url, timeout) with a User-Agent
    providers/
      __init__.py        # PROVIDERS registry dict
      base.py            # Provider protocol
      fake.py            # test-only provider, registered only in tests
  tests/
    conftest.py
    test_db.py
    test_poll.py
  docs/ADRs/             # already exists
```

## What carries over from previous specs

Nothing. This is the first spec.

## Implementation plan

1. Run `uv init --package statusboard` or write `pyproject.toml` by hand. Python 3.12 or newer. Runtime dependencies: none beyond the standard library. Dev dependencies: `pytest`.
2. Write the `Makefile` with targets `help`, `install`, `test`, `poll`, `init-db`. `make help` prints each target with a one-line comment. Use `uv run` for Python commands.
3. Write `model.py` (see contracts below).
4. Write `db.py` with the schema and the five functions listed in contracts.
5. Write `providers/base.py` and `providers/__init__.py`.
6. Write `cli.py`. `poll` loops over the registry, calls each provider inside a try/except, writes incidents, then records the poll run. One provider failure must not stop the others.
7. Write `http.py`. Later ADRs monkeypatch `statusboard.http.fetch_bytes` in tests.
8. Write the tests. Add `providers/fake.py` for tests.
9. Write a short project `README.md`: what it is, `make help`, and the database path.

## Behavioural definitions and contracts

### Severity

```python
Severity = Literal["minor", "major", "critical"]
```

Each provider maps its own scale to these three values. The mapping lives in the provider ADR.

### Region

```python
@dataclass(frozen=True)
class Region:
    cloud: Literal["aws", "gcp", "azure"]
    code: str
```

Canonical region code forms. Providers must normalise to these before they emit:

| cloud | form | example |
|---|---|---|
| aws | lowercase, hyphenated, as AWS uses it | `us-east-1`, `me-central-1` |
| gcp | lowercase, hyphenated, as GCP uses it | `us-central1`, `europe-west2` |
| azure | ARM short name: lowercase, no spaces | `eastus`, `australiaeast`, `uksouth` |

GitHub has no regions. A Databricks incident carries the region of its host cloud, so `cloud` is `aws`, `azure`, or `gcp` and `provider` is `databricks`.

### Incident

```python
@dataclass
class Incident:
    provider: str            # "github" | "gcp" | "aws" | "databricks" | "azure"
    external_id: str         # the provider's own id, stable across polls
    title: str
    severity: Severity
    started_at: datetime     # timezone-aware UTC
    updated_at: datetime     # timezone-aware UTC
    resolved_at: datetime | None
    url: str | None
    last_message: str        # most recent update text, plain text, may be empty
    regions: list[Region]
```

`external_id` plus `provider` is the identity. A provider must emit the same `external_id` for the same incident on every poll.

### Provider protocol

```python
class Provider(Protocol):
    name: str                       # "github", "gcp", ...
    lists_resolved: bool            # True if the feed includes resolved incidents with a resolved time
    def fetch(self) -> list[Incident]: ...
```

`lists_resolved` drives the poll loop:

- `True`: the provider sets `resolved_at` itself. The loop only upserts.
- `False`: the feed only shows open incidents. After the upsert, the loop calls `mark_missing_resolved(provider, seen_ids, now)`. Every open incident for that provider whose id is not in `seen_ids` gets `resolved_at = now`.

If `fetch()` raises, the loop records the error in `poll_run` and does nothing else for that provider. It must not call `mark_missing_resolved`. A failed fetch tells us nothing about which incidents are still open.

The registry is a dict:

```python
PROVIDERS: dict[str, Provider] = {}
def register(p: Provider) -> None
```

Provider modules register themselves at import. `providers/__init__.py` imports each provider module explicitly. Do not use auto-discovery.

### SQLite schema

Database path: `STATUSBOARD_DB` environment variable, default `./statusboard.sqlite3`.

```sql
CREATE TABLE IF NOT EXISTS incident (
  provider     TEXT NOT NULL,
  external_id  TEXT NOT NULL,
  title        TEXT NOT NULL,
  severity     TEXT NOT NULL CHECK (severity IN ('minor','major','critical')),
  started_at   TEXT NOT NULL,   -- ISO 8601 UTC, e.g. 2026-09-05T19:35:30Z
  updated_at   TEXT NOT NULL,
  resolved_at  TEXT,            -- NULL means open
  url          TEXT,
  last_message TEXT NOT NULL,
  PRIMARY KEY (provider, external_id)
);

CREATE TABLE IF NOT EXISTS incident_region (
  provider     TEXT NOT NULL,
  external_id  TEXT NOT NULL,
  cloud        TEXT NOT NULL CHECK (cloud IN ('aws','gcp','azure')),
  region_code  TEXT NOT NULL,
  PRIMARY KEY (provider, external_id, cloud, region_code),
  FOREIGN KEY (provider, external_id) REFERENCES incident(provider, external_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS poll_run (
  provider   TEXT NOT NULL,
  polled_at  TEXT NOT NULL,     -- ISO 8601 UTC
  error      TEXT,              -- NULL means success
  PRIMARY KEY (provider, polled_at)
);
```

Who uses each column:

| column | written by | read by |
|---|---|---|
| incident.* | this ADR, upsert | ADR-0008 dashboard |
| incident_region.* | this ADR, upsert | ADR-0009 map |
| poll_run.* | this ADR, record_poll | ADR-0008 staleness banner |

Enable `PRAGMA foreign_keys = ON` on every connection. Store all timestamps as `YYYY-MM-DDTHH:MM:SSZ`. Truncate to seconds.

### db.py functions

```python
def connect(path: str | None = None) -> sqlite3.Connection
def init_schema(conn) -> None
def upsert_incident(conn, inc: Incident) -> None
    # INSERT ... ON CONFLICT(provider, external_id) DO UPDATE all non-key columns.
    # Then delete and re-insert the incident_region rows for this incident.
def mark_missing_resolved(conn, provider: str, seen_ids: set[str], now: datetime) -> int
    # UPDATE incident SET resolved_at = now WHERE provider = ? AND resolved_at IS NULL AND external_id NOT IN seen_ids
    # returns row count
def record_poll(conn, provider: str, polled_at: datetime, error: str | None) -> None
def open_incidents(conn) -> list[Incident]
    # resolved_at IS NULL, ordered by started_at DESC, regions attached
def recent_resolved(conn, since: datetime) -> list[Incident]
    # resolved_at >= since, ordered by resolved_at DESC, regions attached
def last_polls(conn) -> dict[str, tuple[datetime, str | None]]
    # latest polled_at and error per provider
```

`open_incidents`, `recent_resolved`, and `last_polls` are the only read paths ADR-0008 and ADR-0009 use. Do not add other query helpers here.

### CLI

```
python -m statusboard init-db
python -m statusboard poll [--only PROVIDER]
```

Exit code 0 if every provider succeeded. Exit code 1 if any provider raised. Print one line per provider: `github: 3 incidents, 0 newly resolved` or `aws: ERROR <message>`.

### http.py

```python
def fetch_bytes(url: str, timeout: float = 20.0) -> bytes
```

Uses `urllib.request`. Sends `User-Agent: statusboard/0.1 (+https://github.com/cloudcauldron/statusboard)`. Raises on non-2xx. Tests never call this. Provider tests monkeypatch it.

## Context7 lookups

- `/python/cpython` or the sqlite3 stdlib docs: `ON CONFLICT DO UPDATE` (upsert) syntax and `PRAGMA foreign_keys`.
- `/astral-sh/uv`: `uv init`, `uv add --dev pytest`, `uv run`.
- `/pytest-dev/pytest`: `monkeypatch` and `tmp_path` fixtures.

## Dependencies

- Python 3.12+
- `uv` for environment management
- `pytest` (dev only)

## Test plan

`tests/conftest.py` gives a `conn` fixture backed by `tmp_path`, with schema initialised.

`test_db.py`:

- upsert then select returns the same incident with regions.
- upsert twice with a changed title updates in place, row count stays one.
- upsert with a changed region list replaces the regions.
- `mark_missing_resolved` resolves only open rows not in `seen_ids`, and returns the count.
- `recent_resolved` excludes rows resolved before `since`.
- `last_polls` returns the newest row per provider.

`test_poll.py` uses `providers/fake.py`:

- Fake provider with `lists_resolved=False` returns ids `{a, b}` on poll one and `{a}` on poll two. After poll two, `b` is resolved and `a` is open.
- A fake provider that raises records a `poll_run` row with `error` set and does not stop a second fake provider from being polled. Exit code is 1.

## Acceptance criteria

- `make help` lists the targets.
- `make test` passes.
- `make init-db` creates `statusboard.sqlite3` with the three tables and no other tables.
- `make poll` with no real providers registered prints nothing and exits 0.
- `sqlite3 statusboard.sqlite3 .schema` shows exactly the columns in this ADR.

## Gotchas

- `datetime.utcnow()` is deprecated. Use `datetime.now(timezone.utc)`.
- SQLite `NOT IN (...)` with an empty set is a syntax error. Handle `seen_ids == set()` as a separate branch.
- `sqlite3` default isolation commits late. Call `conn.commit()` in every write helper.
- Do not add an `id INTEGER PRIMARY KEY` to any table. The composite keys above are the identity.
- Keep the fake provider out of the production registry. Register it inside the test, not in `providers/__init__.py`.

## Handoff

The next session runs ADR-0002 (GitHub provider). It needs: the `Incident` and `Region` dataclasses, the `Provider` protocol, `register()`, `fetch_bytes`, and the `conn` test fixture. Record in the project `README.md` any deviation from the contracts above so later sessions see it.
