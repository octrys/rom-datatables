"""Read rom-tools' source/schema.json: each table's columns and their metadata."""

from __future__ import annotations

import json
from pathlib import Path

from rom_datatables.config import DatapackError

type Column = dict[str, object]


def load_source_schema(source_dir: Path) -> dict[str, object]:
    path = source_dir / "schema.json"
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise DatapackError(f"source schema not found: {path}") from error
    except json.JSONDecodeError as error:
        raise DatapackError(f"{path}: invalid JSON: {error}") from error
    if not isinstance(document, dict):
        raise DatapackError(f"{path}: expected an object of {{table: schema}}")
    return document


def table_columns(source_schema: dict[str, object], table: str) -> list[Column]:
    table_schema = source_schema.get(table)
    if not isinstance(table_schema, dict):
        raise DatapackError(f"table {table!r} not in source schema.json")
    columns = table_schema.get("fields")
    if not isinstance(columns, list):
        raise DatapackError(f"table {table!r} has no columns in source schema.json")
    return columns


def child_columns(column: Column) -> list[Column] | None:
    """The columns inside a struct (or each element of a list of structs)."""
    children = column.get("fields")
    return children if isinstance(children, list) else None


def find_column(columns: list[Column], key: str) -> Column | None:
    return next((column for column in columns if decoded_key(column) == key), None)


def resolve_column(columns: list[Column], source_path: str) -> Column:
    """The column a dot-path ends at."""
    column: Column | None = None
    for part in source_path.split("."):
        if column is not None:
            children = child_columns(column)
            if children is None or column.get("list"):
                raise DatapackError(f"{source_path!r}: {part!r} is inside a non-struct")
            columns = children
        column = find_column(columns, part)
        if column is None:
            raise DatapackError(f"{source_path!r}: {part!r} not in source schema.json")
    if column is None:
        raise DatapackError("empty source path")
    return column


def decoded_key(column: Column) -> str:
    """The key rom-tools writes in tables/: the name when there is one."""
    return str(column.get("name") or column.get("field"))
