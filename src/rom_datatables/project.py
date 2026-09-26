"""Project decoded source tables into datapack entities."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from rom_datatables.config import DatapackError, EntitySchema, FieldSpec, PackConfig
from rom_datatables.field_types import FieldType, describe_fields
from rom_datatables.naming import check_naming
from rom_datatables.source_schema import load_source_schema, table_columns

type Row = dict[str, object]


@dataclass(frozen=True)
class EntityReport:
    source: str
    rows: int
    fields: dict[str, FieldType]


def read_source_table(source_dir: Path, table: str) -> list[Row]:
    """Rows of source/tables/<table>.json ({key: row}), in ascending key order."""
    path = source_dir / "tables" / f"{table}.json"
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise DatapackError(f"source table not found: {path}") from error
    except json.JSONDecodeError as error:
        raise DatapackError(f"{path}: invalid JSON: {error}") from error
    if not isinstance(document, dict):
        raise DatapackError(f"{path}: expected an object of {{key: row}}")
    rows: list[Row] = []
    for key in sorted(document, key=_sort_key):
        row = document[key]
        if not isinstance(row, dict):
            raise DatapackError(f"{path}: row {key!r} is not an object")
        rows.append(row)
    return rows


def project_rows(schema: EntitySchema, rows: list[Row]) -> list[Row]:
    """Select and rename. Fails on a missing field or a duplicate key."""
    projected_rows: list[Row] = []
    seen_keys: set[object] = set()
    for row in rows:
        projected = project_fields(row, schema.fields, schema.name)
        key_value = projected[schema.key]
        if key_value in seen_keys:
            raise DatapackError(f"[{schema.name}] duplicate {schema.key}={key_value!r}")
        seen_keys.add(key_value)
        projected_rows.append(projected)
    return projected_rows


def project_fields(row: Row, fields: dict[str, FieldSpec], entity: str) -> Row:
    """Build one output object; nested field tables become nested objects."""
    return {
        output_field: extract(row, spec, entity)
        if isinstance(spec, str)
        else project_fields(row, spec, entity)
        for output_field, spec in fields.items()
    }


def extract(row: Row, source_path: str, entity: str) -> object:
    """Follow a dot-path into a nested row."""
    current: object = row
    for part in source_path.split("."):
        if not isinstance(current, dict) or part not in current:
            raise DatapackError(
                f"[{entity}] source path {source_path!r} not found at {part!r} "
                f"in row {_describe(row)}"
            )
        current = current[part]
    return current


def build_datapack(
    config: PackConfig, schemas: list[EntitySchema]
) -> dict[str, EntityReport]:
    """Write <entity>.json per schema plus version.json into the output dir."""
    source_schema = load_source_schema(config.source_dir)
    check_naming(source_schema, schemas)
    field_types = {
        schema.name: describe_fields(
            table_columns(source_schema, schema.source), schema.fields
        )
        for schema in schemas
    }
    config.output_dir.mkdir(parents=True, exist_ok=True)
    reports: dict[str, EntityReport] = {}
    for schema in schemas:
        rows = project_rows(schema, read_source_table(config.source_dir, schema.source))
        _write_json(config.output_dir / f"{schema.name}.json", rows)
        reports[schema.name] = EntityReport(
            source=schema.source, rows=len(rows), fields=field_types[schema.name]
        )
    version = {
        "client_release": config.client_release,
        "schema_version": config.schema_version,
        "entities": {name: vars(report) for name, report in reports.items()},
    }
    _write_json(config.output_dir / "version.json", version)
    return reports


def _sort_key(key: str) -> tuple[int, int | str]:
    """Numeric keys numerically, then any others as text."""
    return (0, int(key)) if key.lstrip("-").isdigit() else (1, key)


def _describe(row: Row) -> str:
    return repr(row)[:120]


def _write_json(path: Path, document: object) -> None:
    text = json.dumps(document, indent=2, ensure_ascii=False) + "\n"
    path.write_text(text, encoding="utf-8")
