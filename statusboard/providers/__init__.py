"""Provider registry. Each provider module registers itself at import."""

from statusboard.providers.base import Provider

PROVIDERS: dict[str, Provider] = {}


def register(provider: Provider) -> None:
    PROVIDERS[provider.name] = provider


# Provider modules are imported here explicitly, one line per provider.
import statusboard.providers.github  # noqa: E402,F401
