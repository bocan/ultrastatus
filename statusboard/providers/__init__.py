"""Provider registry. Each provider module registers itself at import."""

from statusboard.providers.base import Provider

PROVIDERS: dict[str, Provider] = {}


def register(provider: Provider) -> None:
    PROVIDERS[provider.name] = provider


# Provider modules are imported here explicitly, one line per provider.
import statusboard.providers.statuspage  # noqa: E402,F401
import statusboard.providers.gcp  # noqa: E402,F401
import statusboard.providers.aws  # noqa: E402,F401
import statusboard.providers.databricks  # noqa: E402,F401
