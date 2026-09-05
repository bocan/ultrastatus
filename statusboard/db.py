"""SQLite store. Schema and the only read/write helpers the project uses."""

import os
import sqlite3
from datetime import datetime, timezone

from statusboard.model import Incident, Region

DEFAULT_DB_PATH = "./statusboard.sqlite3"

SCHEMA = """
CREATE TABLE IF NOT EXISTS incident (
  provider     TEXT NOT NULL,
  external_id  TEXT NOT NULL,
  title        TEXT NOT NULL,
  severity     TEXT NOT NULL CHECK (severity IN ('minor','major','critical')),
  started_at   TEXT NOT NULL,
  updated_at   TEXT NOT NULL,
  resolved_at  TEXT,
  url          TEXT,
  last_message TEXT NOT NULL,
  PRIMARY KEY (provider, external_id)
);

CREATE TABLE IF NOT EXISTS incident_region (
  provider     TEXT NOT NULL,
  external_id  TEXT NOT NULL,
  cloud        TEXT NOT NULL CHECK (cloud IN ('aws','gcp','azure')),
  region_code  TEXT NOT NULL,
  PRIMARY KEY (provider, external_id, cloud, region_code),
  FOREIGN KEY (provider, external_id) REFERENCES incident(provider, external_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS poll_run (
  provider   TEXT NOT NULL,
  polled_at  TEXT NOT NULL,
  error      TEXT,
  PRIMARY KEY (provider, polled_at)
);
"""


def to_iso(dt: datetime) -> str:
    """UTC, ISO 8601, seconds precision, trailing Z."""
    if dt.tzinfo is None:
        raise ValueError("timestamps must be timezone-aware")
    return dt.astimezone(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def from_iso(text: str) -> datetime:
    return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def db_path() -> str:
    return os.environ.get("STATUSBOARD_DB", DEFAULT_DB_PATH)


def connect(path: str | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(path or db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def upsert_incident(conn: sqlite3.Connection, inc: Incident) -> None:
    conn.execute(
        """
        INSERT INTO incident
          (provider, external_id, title, severity, started_at, updated_at, resolved_at, url, last_message)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(provider, external_id) DO UPDATE SET
          title = excluded.title,
          severity = excluded.severity,
          started_at = excluded.started_at,
          updated_at = excluded.updated_at,
          resolved_at = excluded.resolved_at,
          url = excluded.url,
          last_message = excluded.last_message
        """,
        (
            inc.provider,
            inc.external_id,
            inc.title,
            inc.severity,
            to_iso(inc.started_at),
            to_iso(inc.updated_at),
            to_iso(inc.resolved_at) if inc.resolved_at else None,
            inc.url,
            inc.last_message,
        ),
    )
    conn.execute(
        "DELETE FROM incident_region WHERE provider = ? AND external_id = ?",
        (inc.provider, inc.external_id),
    )
    conn.executemany(
        "INSERT OR IGNORE INTO incident_region (provider, external_id, cloud, region_code) VALUES (?, ?, ?, ?)",
        [(inc.provider, inc.external_id, r.cloud, r.code) for r in inc.regions],
    )
    conn.commit()


def mark_missing_resolved(
    conn: sqlite3.Connection, provider: str, seen_ids: set[str], now: datetime
) -> int:
    """Resolve every open incident for provider whose id is not in seen_ids."""
    resolved_at = to_iso(now)
    if not seen_ids:
        cursor = conn.execute(
            "UPDATE incident SET resolved_at = ? WHERE provider = ? AND resolved_at IS NULL",
            (resolved_at, provider),
        )
    else:
        ids = sorted(seen_ids)
        placeholders = ",".join("?" for _ in ids)
        cursor = conn.execute(
            f"UPDATE incident SET resolved_at = ? WHERE provider = ? AND resolved_at IS NULL "
            f"AND external_id NOT IN ({placeholders})",
            (resolved_at, provider, *ids),
        )
    conn.commit()
    return cursor.rowcount


def record_poll(
    conn: sqlite3.Connection, provider: str, polled_at: datetime, error: str | None
) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO poll_run (provider, polled_at, error) VALUES (?, ?, ?)",
        (provider, to_iso(polled_at), error),
    )
    conn.commit()


def _row_to_incident(row: sqlite3.Row, regions: list[Region]) -> Incident:
    return Incident(
        provider=row["provider"],
        external_id=row["external_id"],
        title=row["title"],
        severity=row["severity"],
        started_at=from_iso(row["started_at"]),
        updated_at=from_iso(row["updated_at"]),
        resolved_at=from_iso(row["resolved_at"]) if row["resolved_at"] else None,
        url=row["url"],
        last_message=row["last_message"],
        regions=regions,
    )


def _load_incidents(conn: sqlite3.Connection, where: str, params: tuple, order: str) -> list[Incident]:
    rows = conn.execute(f"SELECT * FROM incident WHERE {where} ORDER BY {order}", params).fetchall()
    if not rows:
        return []
    region_rows = conn.execute(
        "SELECT provider, external_id, cloud, region_code FROM incident_region "
        "ORDER BY provider, external_id, rowid"
    ).fetchall()
    regions_by_key: dict[tuple[str, str], list[Region]] = {}
    for r in region_rows:
        regions_by_key.setdefault((r["provider"], r["external_id"]), []).append(
            Region(cloud=r["cloud"], code=r["region_code"])
        )
    return [_row_to_incident(row, regions_by_key.get((row["provider"], row["external_id"]), [])) for row in rows]


def open_incidents(conn: sqlite3.Connection) -> list[Incident]:
    return _load_incidents(conn, "resolved_at IS NULL", (), "started_at DESC, provider, external_id")


def recent_resolved(conn: sqlite3.Connection, since: datetime) -> list[Incident]:
    return _load_incidents(
        conn, "resolved_at IS NOT NULL AND resolved_at >= ?", (to_iso(since),), "resolved_at DESC, provider, external_id"
    )


def last_polls(conn: sqlite3.Connection) -> dict[str, tuple[datetime, str | None]]:
    rows = conn.execute(
        "SELECT provider, MAX(polled_at) AS polled_at FROM poll_run GROUP BY provider"
    ).fetchall()
    result: dict[str, tuple[datetime, str | None]] = {}
    for row in rows:
        error_row = conn.execute(
            "SELECT error FROM poll_run WHERE provider = ? AND polled_at = ?",
            (row["provider"], row["polled_at"]),
        ).fetchone()
        result[row["provider"]] = (from_iso(row["polled_at"]), error_row["error"])
    return result
