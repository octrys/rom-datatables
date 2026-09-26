"""Browse source/ tables in Datasette: filter, sort, facet and query with SQL.

source/tables/*.json become one SQLite table each, keyed by `_key` (the row's
key in the JSON). Nested objects are flattened to dot-path columns
(`mapSize.width`, the paths schema/*.toml uses); lists are stored as JSON text.
Column descriptions come from source/schema.json: naming status, type, enum
members, and the table a column references (a foreign key, so Datasette links
it).

The database is only a view of source/: nothing is filtered or derived.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sqlite3
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from rom_datatables.config import DatapackError
from rom_datatables.field_types import describe_column, type_label
from rom_datatables.source_schema import Column, child_columns, decoded_key

DATABASE_NAME = "source.db"
METADATA_NAME = "metadata.json"
KEY_COLUMN = "_key"
# Values shown in an enum column's description before it is cut short.
ENUM_PREVIEW = 12

type Row = dict[str, object]


@dataclass(frozen=True)
class SourceTable:
    name: str
    columns: list[str]
    rows: list[tuple[object, ...]]
    has_integer_keys: bool


def explore(
    source_dir: Path, explore_dir: Path, port: int, should_rebuild: bool
) -> int:
    """Build the database when source/ changed, then serve it until stopped."""
    if importlib.util.find_spec("datasette") is None:
        raise DatapackError("datasette is not installed: run `uv sync --group explore`")
    database_path = explore_dir / DATABASE_NAME
    metadata_path = explore_dir / METADATA_NAME
    if should_rebuild or is_stale(source_dir, database_path):
        explore_dir.mkdir(parents=True, exist_ok=True)
        source_schema = _load_json_object(source_dir / "schema.json")
        tables = build_database(source_dir / "tables", source_schema, database_path)
        metadata = build_metadata(source_schema, tables)
        _write_json(metadata_path, metadata)
    command = [
        sys.executable, "-m", "datasette", "serve",
        "-i", str(database_path),
        "--metadata", str(metadata_path),
        "--host", "127.0.0.1",
        "--port", str(port),
        "--setting", "sql_time_limit_ms", "5000",
    ]  # fmt: skip
    return subprocess.run(command, check=False).returncode


def is_stale(source_dir: Path, database_path: Path) -> bool:
    """True when the database is missing or older than any source file."""
    if not database_path.exists():
        return True
    built_at = database_path.stat().st_mtime
    sources = [source_dir / "schema.json", *(source_dir / "tables").glob("*.json")]
    return any(path.stat().st_mtime > built_at for path in sources)


def build_database(
    tables_dir: Path, source_schema: dict[str, object], database_path: Path
) -> dict[str, SourceTable]:
    """Write every source table into a fresh SQLite database."""
    paths = sorted(tables_dir.glob("*.json"))
    if not paths:
        raise DatapackError(f"no source tables (*.json) in {tables_dir}")
    tables = {path.stem: read_table(path) for path in paths}
    foreign_keys = {
        name: _foreign_keys(source_schema, name, table, tables)
        for name, table in tables.items()
    }
    partial_path = database_path.with_suffix(".partial")
    partial_path.unlink(missing_ok=True)
    with sqlite3.connect(partial_path) as connection:
        for name, table in tables.items():
            _write_table(connection, table, foreign_keys[name])
    connection.close()
    os.replace(partial_path, database_path)
    return tables


def read_table(path: Path) -> SourceTable:
    """One source table as flat rows: {key: row} or, for text tables, {key: text}."""
    document = _load_json_object(path)
    flat_rows: list[tuple[str, Row]] = []
    columns: dict[str, None] = {}
    for key, value in document.items():
        flat = flatten(value) if isinstance(value, dict) else {"text": value}
        columns.update(dict.fromkeys(flat))
        flat_rows.append((key, flat))
    has_integer_keys = all(_is_integer(key) for key, _ in flat_rows)
    flat_rows.sort(key=lambda item: int(item[0]) if has_integer_keys else item[0])
    names = list(columns)
    rows = [
        (int(key) if has_integer_keys else key, *(flat.get(name) for name in names))
        for key, flat in flat_rows
    ]
    return SourceTable(path.stem, names, rows, has_integer_keys)


def flatten(row: Row, prefix: str = "") -> Row:
    """Nested objects to dot-path keys; lists to JSON text."""
    flat: Row = {}
    for key, value in row.items():
        name = f"{prefix}{key}"
        if isinstance(value, dict):
            flat.update(flatten(value, f"{name}."))
        elif isinstance(value, list):
            flat[name] = json.dumps(value, ensure_ascii=False)
        else:
            flat[name] = value
    return flat


def build_metadata(
    source_schema: dict[str, object], tables: dict[str, SourceTable]
) -> dict[str, object]:
    """Datasette metadata: per table a naming summary and column descriptions."""
    table_metadata: dict[str, object] = {}
    for name, table in tables.items():
        table_schema = source_schema.get(name)
        if not isinstance(table_schema, dict):
            continue
        descriptions = {
            path: describe(column)
            for path, column in _schema_columns(table_schema).items()
            if path in table.columns
        }
        table_metadata[name] = {
            "description": _naming_summary(table_schema),
            "columns": {KEY_COLUMN: "row key in the source JSON", **descriptions},
        }
    return {
        "title": "rom-datatables source",
        "description": "source/tables from rom-tools, read-only. Column "
        "descriptions: naming status · type · field · referenced table · values.",
        "databases": {Path(DATABASE_NAME).stem: {"tables": table_metadata}},
    }


def describe(column: Column) -> str:
    """One column's description: naming · type · field · references · values."""
    parts = [str(column.get("naming")), type_label(describe_column(column))]
    field = column.get("field")
    if field != decoded_key(column):
        parts.append(f"field {field}")
    reference = column.get("fk")
    if isinstance(reference, str):
        parts.append(f"→ {reference}")
    enum = column.get("enum")
    if isinstance(enum, dict):
        members = [str(enum[value]) for value in sorted(enum, key=int)]
        preview = ", ".join(members[:ENUM_PREVIEW])
        hidden = len(members) - ENUM_PREVIEW
        parts.append(preview + (f", … (+{hidden})" if hidden > 0 else ""))
    return " · ".join(parts)


def _schema_columns(table_schema: dict[str, object]) -> dict[str, Column]:
    """Columns by the dot-path they flatten to; structs expand, lists stay whole."""
    columns = table_schema.get("fields")
    return _flatten_columns(columns, "") if isinstance(columns, list) else {}


def _flatten_columns(columns: list[Column], prefix: str) -> dict[str, Column]:
    flat: dict[str, Column] = {}
    for column in columns:
        path = f"{prefix}{decoded_key(column)}"
        children = child_columns(column)
        if children is not None and not column.get("list"):
            flat.update(_flatten_columns(children, f"{path}."))
        else:
            flat[path] = column
    return flat


def _foreign_keys(
    source_schema: dict[str, object],
    name: str,
    table: SourceTable,
    tables: dict[str, SourceTable],
) -> dict[str, str]:
    """Column -> referenced table, for references to integer-keyed tables."""
    table_schema = source_schema.get(name)
    if not isinstance(table_schema, dict):
        return {}
    foreign_keys: dict[str, str] = {}
    for path, column in _schema_columns(table_schema).items():
        reference = column.get("fk")
        if (
            isinstance(reference, str)
            and path in table.columns
            and reference in tables
            and tables[reference].has_integer_keys
            and not column.get("list")
        ):
            foreign_keys[path] = reference
    return foreign_keys


def _write_table(
    connection: sqlite3.Connection, table: SourceTable, foreign_keys: dict[str, str]
) -> None:
    key_type = "INTEGER" if table.has_integer_keys else "TEXT"
    definitions = [f"{_quote(KEY_COLUMN)} {key_type} PRIMARY KEY"]
    definitions += [_quote(column) for column in table.columns]
    definitions += [
        f"FOREIGN KEY ({_quote(column)}) REFERENCES {_quote(other)}"
        f"({_quote(KEY_COLUMN)})"
        for column, other in foreign_keys.items()
    ]
    connection.execute(f"CREATE TABLE {_quote(table.name)} ({', '.join(definitions)})")
    placeholders = ", ".join("?" * (len(table.columns) + 1))
    connection.executemany(
        f"INSERT INTO {_quote(table.name)} VALUES ({placeholders})", table.rows
    )


def _naming_summary(table_schema: dict[str, object]) -> str:
    naming = table_schema.get("naming")
    if not isinstance(naming, dict):
        return ""
    return "columns: " + ", ".join(
        f"{status} {count}" for status, count in naming.items()
    )


def _is_integer(key: str) -> bool:
    return key.lstrip("-").isdigit()


def _quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _load_json_object(path: Path) -> dict[str, object]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise DatapackError(f"not found: {path}") from error
    except json.JSONDecodeError as error:
        raise DatapackError(f"{path}: invalid JSON: {error}") from error
    if not isinstance(document, dict):
        raise DatapackError(f"{path}: expected a JSON object")
    return document


def _write_json(path: Path, document: object) -> None:
    text = json.dumps(document, indent=2, ensure_ascii=False) + "\n"
    path.write_text(text, encoding="utf-8")
