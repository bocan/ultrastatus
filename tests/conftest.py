from datetime import datetime, timezone

import pytest

from statusboard import db
from statusboard.model import Incident, Region


@pytest.fixture
def conn(tmp_path):
    connection = db.connect(str(tmp_path / "test.sqlite3"))
    db.init_schema(connection)
    yield connection
    connection.close()


def utc(year, month, day, hour=0, minute=0, second=0):
    return datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc)


def make_incident(
    provider="fake",
    external_id="a",
    title="Something broke",
    severity="major",
    started_at=None,
    updated_at=None,
    resolved_at=None,
    url="https://example.test/a",
    last_message="Investigating.",
    regions=None,
) -> Incident:
    return Incident(
        provider=provider,
        external_id=external_id,
        title=title,
        severity=severity,
        started_at=started_at or utc(2026, 9, 5, 10, 0, 0),
        updated_at=updated_at or utc(2026, 9, 5, 10, 5, 0),
        resolved_at=resolved_at,
        url=url,
        last_message=last_message,
        regions=list(regions) if regions else [Region("aws", "us-east-1")],
    )
