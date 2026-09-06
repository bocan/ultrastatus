"""Command line entry points: init-db and poll."""

import argparse
import sqlite3
import sys
from datetime import datetime, timezone

from statusboard import db
from statusboard.providers import PROVIDERS
from statusboard.providers.base import Provider


def poll_providers(
    conn: sqlite3.Connection,
    providers: dict[str, Provider],
    out=sys.stdout,
    now: datetime | None = None,
) -> int:
    """Poll each provider in turn. Returns 0 if all succeeded, else 1."""
    exit_code = 0
    for name, provider in providers.items():
        polled_at = now or datetime.now(timezone.utc)
        try:
            incidents = provider.fetch()
            for inc in incidents:
                db.upsert_incident(conn, inc)
            newly_resolved = 0
            if not provider.lists_resolved:
                seen = {inc.external_id for inc in incidents}
                newly_resolved = db.mark_missing_resolved(conn, name, seen, polled_at)
            db.record_poll(conn, name, polled_at, None)
            print(f"{name}: {len(incidents)} incidents, {newly_resolved} newly resolved", file=out)
        except Exception as exc:  # one provider must not stop the others
            db.record_poll(conn, name, polled_at, f"{type(exc).__name__}: {exc}")
            print(f"{name}: ERROR {exc}", file=out)
            exit_code = 1
    return exit_code


def _cmd_init_db(args: argparse.Namespace) -> int:
    conn = db.connect(args.db)
    db.init_schema(conn)
    print(f"initialised {args.db or db.db_path()}")
    return 0


def _cmd_poll(args: argparse.Namespace) -> int:
    providers = dict(PROVIDERS)
    if args.only:
        if args.only not in providers:
            print(f"unknown provider '{args.only}'. Known: {', '.join(sorted(providers)) or 'none'}", file=sys.stderr)
            return 2
        providers = {args.only: providers[args.only]}
    conn = db.connect(args.db)
    db.init_schema(conn)
    return poll_providers(conn, providers)


def _cmd_render(args: argparse.Namespace) -> int:
    from statusboard.config import ConfigError
    from statusboard.render import render

    conn = db.connect(args.db)
    db.init_schema(conn)
    try:
        target = render(conn, args.out)
    except ConfigError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 1
    print(f"wrote {target}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="statusboard")
    parser.add_argument("--db", default=None, help="SQLite path (default: $STATUSBOARD_DB or ./statusboard.sqlite3)")
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init-db", help="create the database and schema")
    p_init.set_defaults(func=_cmd_init_db)

    p_poll = sub.add_parser("poll", help="poll every registered provider")
    p_poll.add_argument("--only", default=None, help="poll a single provider by name")
    p_poll.set_defaults(func=_cmd_poll)

    p_render = sub.add_parser("render", help="write the static dashboard from the database")
    p_render.add_argument("--out", default="site", help="output directory (default: site)")
    p_render.set_defaults(func=_cmd_render)
    return parser


def main(argv: list[str] | None = None) -> int:
    from statusboard.http import prefer_ipv4_from_env

    prefer_ipv4_from_env()
    args = build_parser().parse_args(argv)
    return args.func(args)
