from __future__ import annotations

import argparse

from .pipeline import build, fetch_support, inspect, stats


def _add_version_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--version",
        default="latest",
        help="CommunityDragon patch or latest",
    )
    parser.add_argument(
        "--locale",
        default="zh_CN",
        help="Data Dragon locale, e.g. zh_CN/en_US",
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build Lolok offline League of Legends SQLite data."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    build_parser = sub.add_parser("build")
    _add_version_args(build_parser)

    fetch_parser = sub.add_parser(
        "fetch",
        help="Warm raw/ with the runes / summoner-spell sources only",
    )
    _add_version_args(fetch_parser)

    inspect_parser = sub.add_parser("inspect")
    inspect_parser.add_argument("--db", required=True)
    inspect_parser.add_argument("--champion", default="")
    inspect_parser.add_argument(
        "--item",
        default=None,
        help="Inspect a single item by name or id instead of a champion",
    )
    inspect_parser.add_argument(
        "--monster",
        default=None,
        help="Inspect a single jungle monster by codename (e.g. sru_baron)",
    )

    stats_parser = sub.add_parser("stats")
    stats_parser.add_argument("--db", required=True)

    args = parser.parse_args()

    if args.command == "build":
        build(args.version, args.locale)
    elif args.command == "fetch":
        fetch_support(args.version, args.locale)
    elif args.command == "inspect":
        inspect(args.db, args.champion, args.item, args.monster)
    elif args.command == "stats":
        stats(args.db)


if __name__ == "__main__":
    main()
