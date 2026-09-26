"""Source fields a schema could take but doesn't: `build --pending`.

A field is usable when every segment of its path passes the naming check. It is
covered when the schema reads it, or copies an object it is inside. Structs
expand to their fields; a list is one field, as in the output.
"""

from __future__ import annotations

from dataclasses import dataclass

from rom_datatables.config import EntitySchema
from rom_datatables.field_types import describe_column, type_label
from rom_datatables.naming import ALLOWED_NAMING, source_paths
from rom_datatables.project import Row
from rom_datatables.source_schema import Column, child_columns, decoded_key


@dataclass(frozen=True)
class PendingField:
    source_path: str
    type_label: str
    # False when schema.json lists the column but tables/ has no value for it
    # in some row: reading it would fail the build.
    is_in_every_row: bool


def find_pending(
    columns: list[Column], schema: EntitySchema, rows: list[Row]
) -> list[PendingField]:
    used_paths = source_paths(schema.fields)
    return [
        PendingField(
            source_path=path,
            type_label=type_label(describe_column(column)),
            is_in_every_row=all(_has_path(row, path) for row in rows),
        )
        for path, column in _usable_fields(columns, "")
        if not _is_covered(path, used_paths)
    ]


def _usable_fields(columns: list[Column], prefix: str) -> list[tuple[str, Column]]:
    """(path, column) of every field reachable through allowed names only."""
    fields: list[tuple[str, Column]] = []
    for column in columns:
        if column.get("naming") not in ALLOWED_NAMING:
            continue
        path = f"{prefix}{decoded_key(column)}"
        children = child_columns(column)
        if children is not None and not column.get("list"):
            fields.extend(_usable_fields(children, f"{path}."))
        else:
            fields.append((path, column))
    return fields


def _is_covered(path: str, used_paths: list[str]) -> bool:
    return any(path == used or path.startswith(f"{used}.") for used in used_paths)


def _has_path(row: Row, path: str) -> bool:
    current: object = row
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return False
        current = current[part]
    return True
