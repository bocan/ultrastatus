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
- ADR-0005: the Azure CLI was installed but its login had expired, so Azure coordinates are host-city proxies from the ADR table, not `az account list-locations` metadata. Hatchling packages `statusboard/data/regions.csv` by default; a wheel build confirmed it, so `pyproject.toml` needed no change.
- ADR-0006: Context7 has no status.io entry and developer.status.io is a JavaScript app with no static text. The incident shape was confirmed from a live status.io maintenance object, which uses the same fields. No named message-order constant exists: the provider sorts `messages` by `datetime` and takes the newest, so array order does not matter. The URL pattern `https://<host>/pages/incident/<page_id>/<incident_id>` returned 200 for a real incident. The Databricks GCP page writes `EU-West1` where GCP says `europe-west1`, so `regions.normalise` maps a leading `eu-` to `europe-` for gcp. `jioindiawest` was added to `regions.csv` because the Databricks Azure page lists it. After that, all 77 live container names resolve.
- ADR-0010: Context7 documents only incident.io's authenticated API, not its public Statuspage mimic. Checked live on 2026-09-05: `https://www.dockerstatus.com/incidents/<id>` returns 200 for a real incident id, so that is the URL fallback. `incident_updates` on Docker is newest first, same as Statuspage.
- ADR-0003: Context7 has no entry for the GCP status feed. The live feed on 2026-09-05 confirmed the three `status_impact` values in the ADR. The feed held 6 incidents, not hundreds, so no cutoff filter is needed.
