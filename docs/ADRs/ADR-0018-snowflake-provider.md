# ADR-0018: Snowflake provider with region mapping

## Goal

Add Snowflake, and put its incidents on the map. Snowflake's Statuspage groups its 728 components under 53 region groups named like `AWS - Europe (London)`. An incident lists the affected leaf components, each carrying a `group_id`. Resolve group ids to group names, map group names to canonical region codes, and emit regions the way Databricks does.

## Non-goals

- No per-component or per-product tiles.
- No storage of component ids or group ids. They are resolved at fetch time and discarded.
- No schema changes.

## Outcome shape

```
statusboard/providers/snowflake.py                 # SnowflakeProvider(StatuspageProvider) and the group-name table
tests/test_snowflake.py
tests/fixtures/snowflake_components.json           # trimmed live copy: the 53 group components plus a few leaves
tests/fixtures/snowflake_incidents.json            # trimmed live copy, three incidents
statusboard/render.py                              # group entry and source URL
statusboard/templates/index.html.j2                # legend note gains Snowflake
```

## What carries over from previous specs

From ADR-0010: `StatuspageProvider` and its `_to_incident`. Subclass it.

From ADR-0006: a Databricks incident carries `Region(cloud=<host cloud>, code)` and colours the host cloud's marker. Snowflake does the same.

From ADR-0005: canonical codes, `regions.lookup(cloud, code)`.

From ADR-0014: the Data platforms group.

## Implementation plan

1. Write `SnowflakeProvider(StatuspageProvider)` with `name = "snowflake"`, `host = "status.snowflake.com"`, `label = "Snowflake"`.
2. Override `fetch()`:
   - Fetch `https://status.snowflake.com/api/v2/components.json`. Build `group_names: dict[id, name]` from components where `group` is true.
   - Fetch `incidents.json` as the parent does.
   - For each incident, collect `group_id` from every entry in `components`, look up the group name, map it through `REGION_GROUPS` below, and set `regions` to the deduplicated result in first-seen order. Unknown group names are dropped, not errors.
3. Write `REGION_GROUPS`, the table below, as a module constant.
4. Register the provider. Add `("snowflake", "Snowflake")` to Data platforms after `dbt` and the source URL `https://status.snowflake.com/`.
5. Change the legend note in the template to `Databricks and Snowflake incidents are shown on their host cloud's marker.`
6. Capture the two fixtures.

## Behavioural definitions and contracts

Verified live on 2026-09-06: 728 components, 53 groups, 50 incidents, 1 open. Incident component entries carry `id`, `name`, `group_id`, `group` (false for leaves), and `status`. Leaf names are products such as `Virtual Warehouses` and `Databases, Tables, and Views`.

### Region group table

Every group name seen live, mapped to a canonical code. Names are matched exactly, after `strip()`.

| Snowflake group | cloud | code |
|---|---|---|
| AWS - Africa (Cape Town) | aws | af-south-1 |
| AWS - Asia Pacific (Jakarta) | aws | ap-southeast-3 |
| AWS - Asia Pacific (Malaysia) | aws | ap-southeast-5 |
| AWS - Asia Pacific (Mumbai) | aws | ap-south-1 |
| AWS - Asia Pacific (New Zealand) | aws | ap-southeast-6 |
| AWS - Asia Pacific (Osaka) | aws | ap-northeast-3 |
| AWS - Asia Pacific (Seoul) | aws | ap-northeast-2 |
| AWS - Asia Pacific (Singapore) | aws | ap-southeast-1 |
| AWS - Asia Pacific (Sydney) | aws | ap-southeast-2 |
| AWS - Asia Pacific (Thailand) | aws | ap-southeast-7 |
| AWS - Asia Pacific (Tokyo) | aws | ap-northeast-1 |
| AWS - Canada (Central) | aws | ca-central-1 |
| AWS - Europe (Frankfurt) | aws | eu-central-1 |
| AWS - Europe (Ireland) | aws | eu-west-1 |
| AWS - Europe (London) | aws | eu-west-2 |
| AWS - Europe (Paris) | aws | eu-west-3 |
| AWS - Europe (Stockholm) | aws | eu-north-1 |
| AWS - Europe (Zürich) | aws | eu-central-2 |
| AWS - GovCloud (US-East) | aws | us-gov-east-1 |
| AWS - GovCloud (US-West) | aws | us-gov-west-1 |
| AWS - South America (São Paulo) | aws | sa-east-1 |
| AWS - US East (Commercial Gov-Virginia) | aws | us-east-1 |
| AWS - US East (N. Virginia) | aws | us-east-1 |
| AWS - US East (Ohio) | aws | us-east-2 |
| AWS - US West (Commercial Gov - Oregon) | aws | us-west-2 |
| AWS - US West (Oregon) | aws | us-west-2 |
| AWS GovCloud - DoD | none | dropped, no public region |
| Azure - Australia East (New South Wales) | azure | australiaeast |
| Azure - Canada Central (Toronto) | azure | canadacentral |
| Azure - Central India (Pune) | azure | centralindia |
| Azure - Central Korea (Seoul) | azure | koreacentral |
| Azure - Central US (Iowa) | azure | centralus |
| Azure - East US (Virginia) | azure | eastus |
| Azure - East US 2 (Virginia) | azure | eastus2 |
| Azure - Japan East (Tokyo, Saitama) | azure | japaneast |
| Azure - Mexico (Central) | azure | mexicocentral |
| Azure - North Europe (Ireland) | azure | northeurope |
| Azure - South Central US (Texas) | azure | southcentralus |
| Azure - Southeast Asia (Singapore) | azure | southeastasia |
| Azure - Sweden Central (Gävle) | azure | swedencentral |
| Azure - Switzerland North (Zürich) | azure | switzerlandnorth |
| Azure - UAE North (Dubai) | azure | uaenorth |
| Azure - UK South (London) | azure | uksouth |
| Azure - US Gov (Virginia) | azure | usgovvirginia |
| Azure - West Europe (Netherlands) | azure | westeurope |
| Azure - West US 2 (Washington) | azure | westus2 |
| GCP - Australia Southeast 2 (Melbourne) | gcp | australia-southeast2 |
| GCP - Europe West 2 (London) | gcp | europe-west2 |
| GCP - Europe West 3 (Frankfurt) | gcp | europe-west3 |
| GCP - Europe West 4 (Eemshaven) | gcp | europe-west4 |
| GCP - Middle East (Dammam) | gcp | me-central2 |
| GCP - US Central 1 (Iowa) | gcp | us-central1 |
| GCP - US East 4 (N. Virginia) | gcp | us-east4 |

Two AWS groups map to the same code on purpose. Snowflake runs a commercial and a commercial-gov deployment in the same region.

### Field mapping

Everything from `StatuspageProvider._to_incident`, plus `regions` from the group table. `provider` is `snowflake`. An incident with no components, or only unmapped groups, has `regions == []` and shows as global.

### Fetch order and failure

`components.json` first, then `incidents.json`. If either raises, `fetch()` raises and the poll loop records the error. Do not fall back to region-less incidents on a components failure. That would quietly move incidents off the map.

## Context7 lookups

- `/websites/developer_statuspage_io`: confirm that incident `components[]` entries carry `group_id`, and that `components.json` lists group components with `group: true`. Both were seen live; the lookup is a check.

## Dependencies

- ADR-0017 complete, so the Data platforms group has `dbt` before `snowflake`.
- No new packages.

## Test plan

`tests/test_snowflake.py`:

- Every group name in the components fixture is a key of `REGION_GROUPS`, or is `AWS GovCloud - DoD`. This is the guard that catches a new Snowflake region.
- Every code in `REGION_GROUPS` exists in `regions.lookup()`.
- An incident whose components sit under `AWS - Europe (London)` and `Azure - UK South (London)` gets `[Region("aws","eu-west-2"), Region("azure","uksouth")]`.
- Two components under the same group give one region.
- A component with an unknown `group_id` is ignored.
- Fetch requests `components.json` then `incidents.json`, in that order, on `status.snowflake.com`.
- A failing `components.json` makes `fetch()` raise and nothing is returned.
- End to end: rows land in `incident_region` with `provider = 'snowflake'`.

`tests/test_render.py`: a Snowflake incident on `aws eu-west-2` colours the London AWS marker, same as the Databricks test.

## Acceptance criteria

- `make test` passes.
- `make poll` prints `snowflake: 50 incidents, 0 newly resolved` or similar.
- The legend reads `Databricks and Snowflake incidents are shown on their host cloud's marker.`
- With the example region config, a Snowflake incident in `eu-west-2` counts as mine.

## Gotchas

- Two HTTP calls per poll. `components.json` is about 150 KB. Fine.
- Group names contain non-ASCII characters, `Zürich`, `São Paulo`, `Gävle`. Keep the source file UTF-8 and match exactly. Do not normalise.
- Snowflake adds regions a few times a year. The fixture guard test will fail then. Add the row to the table and refresh the fixture.
- Do not store the group name. Only the region code is kept, through `incident_region`.

## Handoff

None. Airbyte is ADR-0019 and is independent of this one.
