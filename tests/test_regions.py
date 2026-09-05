import pytest

from statusboard import regions
from statusboard.model import CLOUDS


def test_every_row_is_well_formed():
    rows = regions.all_regions()
    assert rows
    for r in rows:
        assert r.cloud in CLOUDS
        assert r.code
        assert r.name
        assert -90.0 <= r.lat <= 90.0
        assert -180.0 <= r.lon <= 180.0


def test_no_duplicate_cloud_and_code():
    keys = [(r.cloud, r.code) for r in regions.all_regions()]
    assert len(keys) == len(set(keys))


def test_codes_are_already_canonical():
    for r in regions.all_regions():
        assert regions.normalise(r.cloud, r.code) == r.code


def test_row_counts_meet_the_floor():
    by_cloud = {}
    for r in regions.all_regions():
        by_cloud[r.cloud] = by_cloud.get(r.cloud, 0) + 1
    assert by_cloud["aws"] >= 38
    assert by_cloud["gcp"] >= 42
    assert by_cloud["azure"] >= 60


def test_csv_is_sorted_by_cloud_then_code():
    keys = [(r.cloud, r.code) for r in regions.all_regions()]
    assert keys == sorted(keys)


def test_lookup():
    assert regions.lookup("aws", "us-east-1") is not None
    assert regions.lookup("azure", "eastus") is not None
    assert regions.lookup("gcp", "us-central1") is not None
    assert regions.lookup("aws", "nope") is None


@pytest.mark.parametrize(
    "cloud,text,expected",
    [
        ("aws", "US East 1", "us-east-1"),
        ("aws", "  EU   West 2 ", "eu-west-2"),
        ("gcp", "US-Central1", "us-central1"),
        ("gcp", "US Central1", "us-central1"),
        ("azure", "Australia East", "australiaeast"),
        ("azure", "East US 2", "eastus2"),
    ],
)
def test_normalise(cloud, text, expected):
    assert regions.normalise(cloud, text) == expected


def test_azure_names_longest_first_puts_east_us_2_before_east_us():
    names = [name for name, _ in regions.azure_names_longest_first()]
    assert names.index("East US 2") < names.index("East US")
    assert all(len(a) >= len(b) for a, b in zip(names, names[1:]))
    codes = dict(regions.azure_names_longest_first())
    assert codes["East US 2"] == "eastus2"


@pytest.mark.parametrize(
    "cloud,code,lat,lon",
    [
        ("aws", "us-east-1", 39.0, -77.5),
        ("aws", "eu-west-2", 51.5, -0.1),
        ("aws", "ap-southeast-2", -33.9, 151.2),
        ("gcp", "us-central1", 41.3, -95.9),
        ("azure", "eastus", 37.4, -79.8),
        ("azure", "westeurope", 52.4, 4.9),
    ],
)
def test_spot_check_coordinates(cloud, code, lat, lon):
    r = regions.lookup(cloud, code)
    assert r is not None
    assert abs(r.lat - lat) <= 1.0
    assert abs(r.lon - lon) <= 1.0
