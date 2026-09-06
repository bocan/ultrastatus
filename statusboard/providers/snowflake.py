"""Snowflake provider: Statuspage feed plus region mapping from component groups.

Snowflake groups its components under one group per cloud region, named like
"AWS - Europe (London)". Incident components carry a group_id, so the group
name gives the region. Incidents then colour the host cloud's marker, the
same way Databricks incidents do.
"""

import json

from statusboard import http, regions
from statusboard.model import Cloud, Incident, Region
from statusboard.providers import register
from statusboard.providers.statuspage import StatuspageProvider

# Exact Snowflake group name -> (cloud, canonical code). Verified live 2026-09-06.
# "AWS GovCloud - DoD" has no public region and is left out on purpose.
REGION_GROUPS: dict[str, tuple[Cloud, str]] = {
    "AWS - Africa (Cape Town)": ("aws", "af-south-1"),
    "AWS - Asia Pacific (Jakarta)": ("aws", "ap-southeast-3"),
    "AWS - Asia Pacific (Malaysia)": ("aws", "ap-southeast-5"),
    "AWS - Asia Pacific (Mumbai)": ("aws", "ap-south-1"),
    "AWS - Asia Pacific (New Zealand)": ("aws", "ap-southeast-6"),
    "AWS - Asia Pacific (Osaka)": ("aws", "ap-northeast-3"),
    "AWS - Asia Pacific (Seoul)": ("aws", "ap-northeast-2"),
    "AWS - Asia Pacific (Singapore)": ("aws", "ap-southeast-1"),
    "AWS - Asia Pacific (Sydney)": ("aws", "ap-southeast-2"),
    "AWS - Asia Pacific (Thailand)": ("aws", "ap-southeast-7"),
    "AWS - Asia Pacific (Tokyo)": ("aws", "ap-northeast-1"),
    "AWS - Canada (Central)": ("aws", "ca-central-1"),
    "AWS - Europe (Frankfurt)": ("aws", "eu-central-1"),
    "AWS - Europe (Ireland)": ("aws", "eu-west-1"),
    "AWS - Europe (London)": ("aws", "eu-west-2"),
    "AWS - Europe (Paris)": ("aws", "eu-west-3"),
    "AWS - Europe (Stockholm)": ("aws", "eu-north-1"),
    "AWS - Europe (Zürich)": ("aws", "eu-central-2"),
    "AWS - GovCloud (US-East)": ("aws", "us-gov-east-1"),
    "AWS - GovCloud (US-West)": ("aws", "us-gov-west-1"),
    "AWS - South America (São Paulo)": ("aws", "sa-east-1"),
    "AWS - US East (Commercial Gov-Virginia)": ("aws", "us-east-1"),
    "AWS - US East (N. Virginia)": ("aws", "us-east-1"),
    "AWS - US East (Ohio)": ("aws", "us-east-2"),
    "AWS - US West (Commercial Gov - Oregon)": ("aws", "us-west-2"),
    "AWS - US West (Oregon)": ("aws", "us-west-2"),
    "Azure - Australia East (New South Wales)": ("azure", "australiaeast"),
    "Azure - Canada Central (Toronto)": ("azure", "canadacentral"),
    "Azure - Central India (Pune)": ("azure", "centralindia"),
    "Azure - Central Korea (Seoul)": ("azure", "koreacentral"),
    "Azure - Central US (Iowa)": ("azure", "centralus"),
    "Azure - East US (Virginia)": ("azure", "eastus"),
    "Azure - East US 2 (Virginia)": ("azure", "eastus2"),
    "Azure - Japan East (Tokyo, Saitama)": ("azure", "japaneast"),
    "Azure - Mexico (Central)": ("azure", "mexicocentral"),
    "Azure - North Europe (Ireland)": ("azure", "northeurope"),
    "Azure - South Central US (Texas)": ("azure", "southcentralus"),
    "Azure - Southeast Asia (Singapore)": ("azure", "southeastasia"),
    "Azure - Sweden Central (Gävle)": ("azure", "swedencentral"),
    "Azure - Switzerland North (Zürich)": ("azure", "switzerlandnorth"),
    "Azure - UAE North (Dubai)": ("azure", "uaenorth"),
    "Azure - UK South (London)": ("azure", "uksouth"),
    "Azure - US Gov (Virginia)": ("azure", "usgovvirginia"),
    "Azure - West Europe (Netherlands)": ("azure", "westeurope"),
    "Azure - West US 2 (Washington)": ("azure", "westus2"),
    "GCP - Australia Southeast 2 (Melbourne)": ("gcp", "australia-southeast2"),
    "GCP - Europe West 2 (London)": ("gcp", "europe-west2"),
    "GCP - Europe West 3 (Frankfurt)": ("gcp", "europe-west3"),
    "GCP - Europe West 4 (Eemshaven)": ("gcp", "europe-west4"),
    "GCP - Middle East (Dammam)": ("gcp", "me-central2"),
    "GCP - US Central 1 (Iowa)": ("gcp", "us-central1"),
    "GCP - US East 4 (N. Virginia)": ("gcp", "us-east4"),
}

UNMAPPED_GROUPS = {"AWS GovCloud - DoD"}


class SnowflakeProvider(StatuspageProvider):
    def __init__(self):
        super().__init__("snowflake", "status.snowflake.com", "Snowflake")

    @property
    def components_url(self) -> str:
        return f"https://{self.host}/api/v2/components.json"

    def _group_names(self) -> dict[str, str]:
        payload = json.loads(http.fetch_bytes(self.components_url))
        return {
            c["id"]: c.get("name", "").strip()
            for c in payload.get("components", [])
            if c.get("group")
        }

    @staticmethod
    def regions_for(item: dict, group_names: dict[str, str]) -> list[Region]:
        found: list[Region] = []
        for component in item.get("components") or []:
            name = group_names.get(component.get("group_id") or "")
            mapped = REGION_GROUPS.get(name or "")
            if mapped is None:
                continue
            region = Region(*mapped)
            if regions.lookup(*mapped) is not None and region not in found:
                found.append(region)
        return found

    def fetch(self) -> list[Incident]:
        # Components first. If either call fails, raise: a region-less fallback
        # would quietly move incidents off the map.
        group_names = self._group_names()
        payload = json.loads(http.fetch_bytes(self.feed_url))
        incidents = []
        for item in payload.get("incidents", []):
            inc = self._to_incident(item)
            inc.regions = self.regions_for(item, group_names)
            incidents.append(inc)
        return incidents


register(SnowflakeProvider())
