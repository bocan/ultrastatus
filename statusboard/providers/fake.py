"""Test-only providers. Never registered by the package itself."""

from statusboard.model import Incident


class FakeProvider:
    """Returns one batch of incidents per fetch, in order. Repeats the last batch."""

    def __init__(self, name: str, lists_resolved: bool, batches: list[list[Incident]]):
        self.name = name
        self.label = name.title()
        self.lists_resolved = lists_resolved
        self._batches = batches
        self.calls = 0

    def fetch(self) -> list[Incident]:
        index = min(self.calls, len(self._batches) - 1)
        self.calls += 1
        return list(self._batches[index])


class RaisingProvider:
    def __init__(self, name: str, message: str = "boom", lists_resolved: bool = False):
        self.name = name
        self.label = name.title()
        self.lists_resolved = lists_resolved
        self._message = message

    def fetch(self) -> list[Incident]:
        raise RuntimeError(self._message)
