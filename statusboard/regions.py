"""Static cloud region table and region name normalisation.

The table lives in statusboard/data/regions.csv. Nothing joins on it in SQL,
so it is not in the database.
"""

import csv
import io
import re
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources

_WHITESPACE = re.compile(r"\s+")


@dataclass(frozen=True)
class RegionInfo:
    cloud: str
    code: str
    name: str
    lat: float
    lon: float


@lru_cache(maxsize=1)
def all_regions() -> list[RegionInfo]:
    path = resources.files("statusboard").joinpath("data/regions.csv")
    handle = io.StringIO(path.read_text(encoding="utf-8"), newline="")
    return [
        RegionInfo(
            cloud=row["cloud"],
            code=row["code"],
            name=row["name"],
            lat=float(row["lat"]),
            lon=float(row["lon"]),
        )
        for row in csv.DictReader(handle)
    ]


@lru_cache(maxsize=1)
def _index() -> dict[tuple[str, str], RegionInfo]:
    return {(r.cloud, r.code): r for r in all_regions()}


def lookup(cloud: str, code: str) -> RegionInfo | None:
    return _index().get((cloud, code))


def normalise(cloud: str, text: str) -> str:
    """Turn a provider's display form into the canonical code for that cloud.

    aws:   "US East 1"      -> "us-east-1"
    gcp:   "US-Central1"    -> "us-central1"
    gcp:   "EU-West1"       -> "europe-west1"   (Databricks writes EU, GCP says europe)
    azure: "Australia East" -> "australiaeast"
    """
    lowered = text.strip().lower()
    if cloud == "azure":
        return _WHITESPACE.sub("", lowered)
    code = _WHITESPACE.sub("-", lowered)
    if cloud == "gcp" and code.startswith("eu-"):
        code = "europe-" + code[len("eu-") :]
    return code


@lru_cache(maxsize=1)
def azure_names_longest_first() -> list[tuple[str, str]]:
    """[(display_name, code), ...] sorted so longer names match before their prefixes."""
    pairs = [(r.name, r.code) for r in all_regions() if r.cloud == "azure"]
    return sorted(pairs, key=lambda pair: (-len(pair[0]), pair[0]))
