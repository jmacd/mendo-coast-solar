from __future__ import annotations

import argparse
import tomllib
from pathlib import Path

from .acquire import fetch_all
from .analysis import analyze


def load_config(path: Path) -> dict:
    with path.open("rb") as config_file:
        return tomllib.load(config_file)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="Acquire and rank Mendocino Coast solar siting data"
    )
    result.add_argument(
        "--config",
        type=Path,
        default=Path("config/mendocino.toml"),
    )
    result.add_argument("--data-dir", type=Path, default=Path("data"))
    result.add_argument("--output-dir", type=Path, default=Path("output"))
    subcommands = result.add_subparsers(dest="command", required=True)

    fetch = subcommands.add_parser("fetch", help="download and cache public datasets")
    fetch.add_argument("--refresh", action="store_true")

    analysis = subcommands.add_parser("analyze", help="rank parcels")
    analysis.add_argument("--known-sites", type=Path)

    run = subcommands.add_parser("run", help="fetch and analyze")
    run.add_argument("--refresh", action="store_true")
    run.add_argument("--known-sites", type=Path)
    return result


def main() -> None:
    args = parser().parse_args()
    config = load_config(args.config)
    if args.command in {"fetch", "run"}:
        fetch_all(config, args.data_dir, refresh=args.refresh)
    if args.command in {"analyze", "run"}:
        analyze(config, args.data_dir, args.output_dir, args.known_sites)


if __name__ == "__main__":
    main()

