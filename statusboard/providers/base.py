from typing import Protocol

from statusboard.model import Incident


class Provider(Protocol):
    name: str
    label: str
    lists_resolved: bool

    def fetch(self) -> list[Incident]: ...
