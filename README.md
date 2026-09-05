# statusboard

Polls the public status feeds of AWS, GCP, Azure, GitHub, and Databricks into one SQLite file, then renders one dashboard page. Python, standard library, cron-friendly.

The design lives in `docs/ADRs/`. Read `docs/ADRs/README.md` first.

## Quick start

```
make install
make init-db
make poll
make test
```

`make help` lists every target.

## Database

Path comes from `STATUSBOARD_DB`, default `./statusboard.sqlite3`. Three tables: `incident`, `incident_region`, `poll_run`. See ADR-0001 for the schema and the rule that every column must have a reader and a writer.

## Deviations from the ADRs

None yet. Record any here so later sessions see them.
