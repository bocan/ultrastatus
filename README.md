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

- ADR-0004: no `aws_utf16_sample.bin` fixture. The test builds the UTF-16 bytes from the UTF-8 fixture at run time, so no binary file sits in git. Coverage is the same.

## Notes from implementation

- ADR-0002: the Statuspage docs do not state the order of `incident_updates`. The live GitHub feed, checked on 2026-09-05 across 12 incidents, is newest first. The provider reads index 0.
- ADR-0010: Context7 documents only incident.io's authenticated API, not its public Statuspage mimic. Checked live on 2026-09-05: `https://www.dockerstatus.com/incidents/<id>` returns 200 for a real incident id, so that is the URL fallback. `incident_updates` on Docker is newest first, same as Statuspage.
- ADR-0003: Context7 has no entry for the GCP status feed. The live feed on 2026-09-05 confirmed the three `status_impact` values in the ADR. The feed held 6 incidents, not hundreds, so no cutoff filter is needed.
