# ADR-0005: Region table and region name normalisation

## Goal

Add a static table of cloud regions with coordinates, and helpers that turn provider-specific region names into canonical codes. Two later ADRs need this:

- ADR-0006 and ADR-0007 turn display names such as `US East 1` or `Australia East` into codes.
- ADR-0009 places each region on the world map.

## Non-goals

- No database table. The region list is a data file in the package, loaded at runtime.
- No region data for GitHub. It has none.
- No availability zones. Regions only.
- No automatic download from cloud APIs. The file is hand-maintained and committed.

## Outcome shape

```
statusboard/data/regions.csv
statusboard/regions.py
tests/test_regions.py
```

## What carries over from previous specs

From ADR-0001, the canonical region code forms:

| cloud | form | example |
|---|---|---|
| aws | lowercase hyphenated | `us-east-1` |
| gcp | lowercase hyphenated | `us-central1` |
| azure | ARM short name, lowercase, no spaces | `eastus`, `australiaeast` |

## Implementation plan

1. Write `statusboard/data/regions.csv` with the header `cloud,code,name,lat,lon`. One row per region. Fill it from the tables below, then add any region that the official region lists show and the tables below miss.
2. Write `statusboard/regions.py` with the functions in the contracts.
3. Write tests.
4. Add `regions.csv` to the package data in `pyproject.toml` so `uv run` and an installed wheel both find it. Load it with `importlib.resources`.

## Behavioural definitions and contracts

### regions.csv

Columns and who reads them:

| column | read by |
|---|---|
| cloud | ADR-0006, ADR-0007, ADR-0009 |
| code | ADR-0006, ADR-0007, ADR-0009 |
| name | ADR-0007 text matching for Azure, ADR-0009 tooltip |
| lat, lon | ADR-0009 marker position |

`name` is the provider's own display name. For Azure it must be the exact display name Microsoft uses on the status page, because ADR-0007 matches it in free text.

`lat` and `lon` are decimal degrees of the city that hosts the region. One decimal place is enough.

### regions.py

```python
@dataclass(frozen=True)
class RegionInfo:
    cloud: str
    code: str
    name: str
    lat: float
    lon: float

def all_regions() -> list[RegionInfo]
    # cached after first load
def lookup(cloud: str, code: str) -> RegionInfo | None
def normalise(cloud: str, text: str) -> str
    # aws:   "US East 1"        -> "us-east-1"     lowercase, whitespace to hyphen
    # gcp:   "US-Central1"      -> "us-central1"   lowercase, whitespace to hyphen
    # azure: "Australia East"   -> "australiaeast" lowercase, remove whitespace
    # Result is a code. It may or may not exist in the table. Callers use lookup() to check.
def azure_names_longest_first() -> list[tuple[str, str]]
    # [(name, code), ...] sorted by len(name) descending. ADR-0007 uses this for text matching.
```

### Region seed data

Add every row below. Look up coordinates for the host city from a reliable atlas source. Where the official list shows a region not in this table, add it.

AWS, verified against the AWS regions page, September 2026:

| code | name (host city) |
|---|---|
| us-east-1 | N. Virginia (Ashburn) |
| us-east-2 | Ohio (Columbus) |
| us-west-1 | N. California (San Francisco) |
| us-west-2 | Oregon (Boardman) |
| ca-central-1 | Canada Central (Montreal) |
| ca-west-1 | Canada West (Calgary) |
| mx-central-1 | Mexico Central (Queretaro) |
| sa-east-1 | Sao Paulo |
| eu-west-1 | Ireland (Dublin) |
| eu-west-2 | London |
| eu-west-3 | Paris |
| eu-central-1 | Frankfurt |
| eu-central-2 | Zurich |
| eu-north-1 | Stockholm |
| eu-south-1 | Milan |
| eu-south-2 | Spain (Zaragoza) |
| il-central-1 | Tel Aviv |
| me-south-1 | Bahrain (Manama) |
| me-central-1 | UAE (Abu Dhabi) |
| af-south-1 | Cape Town |
| ap-east-1 | Hong Kong |
| ap-east-2 | Taipei |
| ap-south-1 | Mumbai |
| ap-south-2 | Hyderabad |
| ap-northeast-1 | Tokyo |
| ap-northeast-2 | Seoul |
| ap-northeast-3 | Osaka |
| ap-southeast-1 | Singapore |
| ap-southeast-2 | Sydney |
| ap-southeast-3 | Jakarta |
| ap-southeast-4 | Melbourne |
| ap-southeast-5 | Malaysia (Kuala Lumpur) |
| ap-southeast-6 | New Zealand (Auckland) |
| ap-southeast-7 | Thailand (Bangkok) |
| us-gov-east-1 | GovCloud US-East (Ohio) |
| us-gov-west-1 | GovCloud US-West (Oregon) |
| cn-north-1 | Beijing |
| cn-northwest-1 | Ningxia |

GCP:

| code | name (host city) |
|---|---|
| us-central1 | Iowa (Council Bluffs) |
| us-east1 | South Carolina (Moncks Corner) |
| us-east4 | N. Virginia (Ashburn) |
| us-east5 | Ohio (Columbus) |
| us-south1 | Texas (Dallas) |
| us-west1 | Oregon (The Dalles) |
| us-west2 | Los Angeles |
| us-west3 | Salt Lake City |
| us-west4 | Las Vegas |
| northamerica-northeast1 | Montreal |
| northamerica-northeast2 | Toronto |
| northamerica-south1 | Queretaro |
| southamerica-east1 | Sao Paulo |
| southamerica-west1 | Santiago |
| europe-west1 | Belgium (St. Ghislain) |
| europe-west2 | London |
| europe-west3 | Frankfurt |
| europe-west4 | Netherlands (Eemshaven) |
| europe-west6 | Zurich |
| europe-west8 | Milan |
| europe-west9 | Paris |
| europe-west10 | Berlin |
| europe-west12 | Turin |
| europe-north1 | Finland (Hamina) |
| europe-north2 | Stockholm |
| europe-central2 | Warsaw |
| europe-southwest1 | Madrid |
| asia-east1 | Taiwan (Changhua) |
| asia-east2 | Hong Kong |
| asia-northeast1 | Tokyo |
| asia-northeast2 | Osaka |
| asia-northeast3 | Seoul |
| asia-south1 | Mumbai |
| asia-south2 | Delhi |
| asia-southeast1 | Singapore |
| asia-southeast2 | Jakarta |
| australia-southeast1 | Sydney |
| australia-southeast2 | Melbourne |
| me-central1 | Doha |
| me-central2 | Dammam |
| me-west1 | Tel Aviv |
| africa-south1 | Johannesburg |

Azure. `name` must be the exact display name. If the `az` CLI is installed, `az account list-locations -o json` gives `name`, `displayName`, and `metadata.latitude` and `metadata.longitude` for every region, and is the preferred source. Otherwise use this table:

| code | name |
|---|---|
| eastus | East US |
| eastus2 | East US 2 |
| centralus | Central US |
| northcentralus | North Central US |
| southcentralus | South Central US |
| westcentralus | West Central US |
| westus | West US |
| westus2 | West US 2 |
| westus3 | West US 3 |
| canadacentral | Canada Central |
| canadaeast | Canada East |
| brazilsouth | Brazil South |
| brazilsoutheast | Brazil Southeast |
| mexicocentral | Mexico Central |
| chilecentral | Chile Central |
| northeurope | North Europe |
| westeurope | West Europe |
| uksouth | UK South |
| ukwest | UK West |
| francecentral | France Central |
| francesouth | France South |
| germanywestcentral | Germany West Central |
| germanynorth | Germany North |
| switzerlandnorth | Switzerland North |
| switzerlandwest | Switzerland West |
| norwayeast | Norway East |
| norwaywest | Norway West |
| swedencentral | Sweden Central |
| polandcentral | Poland Central |
| italynorth | Italy North |
| spaincentral | Spain Central |
| austriaeast | Austria East |
| belgiumcentral | Belgium Central |
| uaenorth | UAE North |
| uaecentral | UAE Central |
| qatarcentral | Qatar Central |
| israelcentral | Israel Central |
| southafricanorth | South Africa North |
| southafricawest | South Africa West |
| eastasia | East Asia |
| southeastasia | Southeast Asia |
| japaneast | Japan East |
| japanwest | Japan West |
| koreacentral | Korea Central |
| koreasouth | Korea South |
| centralindia | Central India |
| southindia | South India |
| westindia | West India |
| indonesiacentral | Indonesia Central |
| malaysiawest | Malaysia West |
| newzealandnorth | New Zealand North |
| australiaeast | Australia East |
| australiasoutheast | Australia Southeast |
| australiacentral | Australia Central |
| australiacentral2 | Australia Central 2 |
| usgovvirginia | US Gov Virginia |
| usgovarizona | US Gov Arizona |
| usgovtexas | US Gov Texas |
| chinaeast2 | China East 2 |
| chinaeast3 | China East 3 |
| chinanorth2 | China North 2 |
| chinanorth3 | China North 3 |

Host cities for Azure, when the `az` CLI is not available: East US and East US 2 are Virginia, Central US is Iowa, North Central US is Illinois, South Central US is Texas, West Central US is Wyoming, West US is California, West US 2 is Washington state, West US 3 is Arizona, North Europe is Dublin, West Europe is Amsterdam, UK South is London, UK West is Cardiff, Germany West Central is Frankfurt, Switzerland North is Zurich, Sweden Central is Gavle, Japan East is Tokyo, Japan West is Osaka, Korea Central is Seoul, Central India is Pune, South India is Chennai, West India is Mumbai, Australia East is Sydney, Australia Southeast is Melbourne, Australia Central is Canberra, East Asia is Hong Kong, Southeast Asia is Singapore.

## Context7 lookups

- `/python/cpython`: `importlib.resources.files()` for reading package data.
- If `az` is available, Azure CLI docs for `az account list-locations`.

## Dependencies

- ADR-0001 complete.
- No new packages.

## Test plan

`tests/test_regions.py`:

- Every row has a valid cloud, non-empty code and name, lat in [-90, 90], lon in [-180, 180].
- No duplicate `(cloud, code)`.
- Every code already matches its canonical form: `normalise(cloud, code) == code`.
- `lookup("aws", "us-east-1")` and `lookup("azure", "eastus")` and `lookup("gcp", "us-central1")` are not None. `lookup("aws", "nope")` is None.
- `normalise("aws", "US East 1") == "us-east-1"`, `normalise("gcp", "US-Central1") == "us-central1"`, `normalise("azure", "Australia East") == "australiaeast"`.
- `azure_names_longest_first()` puts `East US 2` before `East US`.
- Spot check coordinates within 1 degree: `us-east-1` near (39.0, -77.5), `eu-west-2` near (51.5, -0.1), `ap-southeast-2` near (-33.9, 151.2), `us-central1` near (41.3, -95.9), `eastus` near (37.4, -79.8), `westeurope` near (52.4, 4.9).

## Acceptance criteria

- `make test` passes.
- `regions.csv` has at least 38 aws rows, 42 gcp rows, and 60 azure rows.

## Gotchas

- Do not put the region table in SQLite. Nothing joins on it in SQL.
- `normalise` for gcp must also hyphenate whitespace, because the Databricks GCP page writes `US-Central1` and could write `US Central1` in future.
- Coordinates for AWS and GCP are not published. City coordinates are the accepted proxy.
- Keep the CSV sorted by cloud then code so diffs stay readable.

## Handoff

Next session runs ADR-0006 (Databricks). It uses `normalise()` and `lookup()`. ADR-0007 uses `azure_names_longest_first()`. ADR-0009 uses `all_regions()`.
