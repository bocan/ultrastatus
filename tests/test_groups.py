"""ADR-0014: every registered provider sits in exactly one tile group."""

from collections import Counter

from statusboard.providers import PROVIDERS
from statusboard.render import GROUPS, PROVIDER_ORDER


def _grouped_names():
    return [name for _, pairs in GROUPS for name, _ in pairs]


def test_every_registered_provider_has_a_group():
    registered = set(PROVIDERS)
    grouped = set(_grouped_names())
    assert registered == grouped, (
        f"registered but not in render.GROUPS: {sorted(registered - grouped)}; "
        f"in render.GROUPS but not registered: {sorted(grouped - registered)}"
    )


def test_no_provider_appears_in_two_groups():
    duplicates = [name for name, n in Counter(_grouped_names()).items() if n > 1]
    assert duplicates == []


def test_provider_order_is_the_groups_flattened():
    assert [name for name, _ in PROVIDER_ORDER] == _grouped_names()
