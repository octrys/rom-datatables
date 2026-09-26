"""rom-datatables: source/ (rom-tools output) -> datapack/ (rom-server input)."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from rom_datatables.config import (
    DatapackError,
    EntitySchema,
    PackConfig,
    load_config,
    load_schemas,
)
from rom_datatables.explore import explore
from rom_datatables.pending import find_pending
from rom_datatables.project import build_datapack, read_source_table
from rom_datatables.source_schema import load_source_schema, table_columns

DEFAULT_CONFIG = Path("datapack.toml")
DEFAULT_PORT = 8001

logger = logging.getLogger("rom_datatables")


def main() -> None:
    parser = argparse.ArgumentParser(prog="rom-datatables", description=__doc__)
    parser.add_argument(
        "--config", type=Path, default=DEFAULT_CONFIG, help="default: datapack.toml"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    build_parser = commands.add_parser("build", help="project source/ into datapack/")
    build_parser.add_argument(
        "--pending",
        action="store_true",
        help="also list source fields the schemas could take but don't use",
    )
    explore_parser = commands.add_parser(
        "explore", help="browse source/ tables in Datasette (localhost only)"
    )
    explore_parser.add_argument(
        "--port", type=int, default=DEFAULT_PORT, help=f"default: {DEFAULT_PORT}"
    )
    explore_parser.add_argument(
        "--rebuild", action="store_true", help="rebuild the database even if current"
    )
    arguments = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    try:
        config = load_config(arguments.config)
        if arguments.command == "build":
            run_build(config, arguments.pending)
        else:
            sys.exit(
                explore(
                    config.source_dir,
                    config.explore_dir,
                    arguments.port,
                    arguments.rebuild,
                )
            )
    except DatapackError as error:
        logger.error("error: %s", error)
        sys.exit(1)


def run_build(config: PackConfig, should_list_pending: bool) -> None:
    schemas = load_schemas(config.schema_dir)
    reports = build_datapack(config, schemas)
    for name, report in reports.items():
        logger.info("%-12s %5d rows  <- %s", name, report.rows, report.source)
    logger.info(
        "wrote %d entities + version.json to %s", len(reports), config.output_dir
    )
    if should_list_pending:
        log_pending(config, schemas)


def log_pending(config: PackConfig, schemas: list[EntitySchema]) -> None:
    source_schema = load_source_schema(config.source_dir)
    for schema in schemas:
        pending = find_pending(
            table_columns(source_schema, schema.source),
            schema,
            read_source_table(config.source_dir, schema.source),
        )
        if not pending:
            logger.info("\n%s: no pending fields in %s", schema.name, schema.source)
            continue
        logger.info(
            "\n%s: %d %s fields not in schema/%s.toml",
            schema.name,
            len(pending),
            schema.source,
            schema.name,
        )
        for field in pending:
            line = f"  {field.source_path:<32} {field.type_label}"
            if not field.is_in_every_row:
                line = f"{line:<50} (missing from tables/: fix in rom-tools)"
            logger.info("%s", line)


if __name__ == "__main__":
    main()
