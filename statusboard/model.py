"""Normalised data model shared by every provider."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

Severity = Literal["minor", "major", "critical"]
SEVERITIES: tuple[str, ...] = ("minor", "major", "critical")

Cloud = Literal["aws", "gcp", "azure"]
CLOUDS: tuple[str, ...] = ("aws", "gcp", "azure")


@dataclass(frozen=True)
class Region:
    cloud: Cloud
    code: str


@dataclass
class Incident:
    provider: str
    external_id: str
    title: str
    severity: Severity
    started_at: datetime
    updated_at: datetime
    resolved_at: datetime | None
    url: str | None
    last_message: str
    regions: list[Region] = field(default_factory=list)
