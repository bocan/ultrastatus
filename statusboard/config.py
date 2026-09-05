"""Operator config: which regions are "mine". Read at render time only."""

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

from statusboard import regions
from statusboard.model import CLOUDS

DEFAULT_CONFIG_PATH = "./statusboard.toml"


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class Config:
    my_regions: frozenset[tuple[str, str]]

    @property
    def active(self) -> bool:
        return bool(self.my_regions)


INACTIVE = Config(frozenset())


def config_path() -> str:
    return os.environ.get("STATUSBOARD_CONFIG", DEFAULT_CONFIG_PATH)


def _near_matches(cloud: str, code: str, limit: int = 5) -> list[str]:
    """Codes for this cloud that look like the typo: same letters minus hyphens, then longest shared prefix."""
    candidates = [r.code for r in regions.all_regions() if r.cloud == cloud]
    squashed = code.replace("-", "").lower()
    exact = [c for c in candidates if c.replace("-", "") == squashed]
    if exact:
        return exact

    def shared_prefix(other: str) -> int:
        n = 0
        for a, b in zip(code.lower(), other):
            if a != b:
                break
            n += 1
        return n

    ranked = sorted(candidates, key=lambda c: (-shared_prefix(c), c))
    return [c for c in ranked if shared_prefix(c) >= 3][:limit]


def load_config(path: str | None = None) -> Config:
    """A missing file means no filter. Anything malformed raises ConfigError."""
    file = Path(path or config_path())
    if not file.exists():
        return INACTIVE
    try:
        data = tomllib.loads(file.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{file}: not valid TOML: {exc}") from exc

    table = data.get("regions", {})
    if not isinstance(table, dict):
        raise ConfigError(f"{file}: [regions] must be a table")

    mine: set[tuple[str, str]] = set()
    for cloud, codes in table.items():
        if cloud not in CLOUDS:
            raise ConfigError(f"{file}: unknown cloud '{cloud}' in [regions]. Use one of: {', '.join(CLOUDS)}")
        if not isinstance(codes, list) or not all(isinstance(c, str) for c in codes):
            raise ConfigError(f"{file}: [regions] {cloud} must be a list of strings")
        for code in codes:
            if regions.lookup(cloud, code) is None:
                message = f"{file}: unknown {cloud} region '{code}'"
                near = _near_matches(cloud, code)
                if near:
                    message += f". Did you mean: {', '.join(near)}"
                raise ConfigError(message)
            mine.add((cloud, code))
    return Config(frozenset(mine))
