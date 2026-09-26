"""Describe each datapack field's type from its column in source/schema.json.

A description mirrors the output's shape:
    {"type": "int32"}                                  scalar
    {"type": "enum", "values": ["MT_NONE", ...]}       enum member names
    {"type": "list", "items": {...}}                   list or array
    {"type": "object", "fields": {"width": {...}}}     nested object
"""

from __future__ import annotations

import re

from rom_datatables.config import DatapackError, FieldSpec
from rom_datatables.source_schema import (
    Column,
    child_columns,
    decoded_key,
    resolve_column,
)

type FieldType = dict[str, object]

SCALAR_TYPES = {
    "System.Boolean": "bool",
    "System.Int32": "int32",
    "System.UInt32": "uint32",
    "System.Int64": "int64",
    "System.Single": "float32",
    "System.Double": "float64",
    "System.String": "string",
}

LIST_ELEMENT = re.compile(r"^System\.Collections\.Generic\.List<(?P<element>.+)>$")
ARRAY_ELEMENT = re.compile(r"^(?P<element>.+)\[\]$")


def describe_fields(
    columns: list[Column], fields: dict[str, FieldSpec]
) -> dict[str, FieldType]:
    """Types of a schema's output fields; schema sub-tables become objects."""
    return {
        output_field: describe_column(resolve_column(columns, spec))
        if isinstance(spec, str)
        else {"type": "object", "fields": describe_fields(columns, spec)}
        for output_field, spec in fields.items()
    }


def describe_column(column: Column) -> FieldType:
    declared_type = str(column.get("type"))
    if not column.get("list"):
        return _describe_value(column, declared_type)
    match = LIST_ELEMENT.match(declared_type) or ARRAY_ELEMENT.match(declared_type)
    if match is None:
        raise DatapackError(
            f"list column {column.get('field')} has no element type in "
            f"{declared_type!r}"
        )
    return {"type": "list", "items": _describe_value(column, match["element"])}


def type_label(field_type: FieldType) -> str:
    """Short form of a description: int32, enum, list<int32>, object."""
    kind = str(field_type["type"])
    items = field_type.get("items")
    if kind == "list" and isinstance(items, dict):
        return f"list<{type_label(items)}>"
    return kind


def _describe_value(column: Column, declared_type: str) -> FieldType:
    """One value (a list's element for list columns)."""
    enum = column.get("enum")
    if isinstance(enum, dict):
        return {"type": "enum", "values": _enum_members(enum)}
    children = child_columns(column)
    if children is not None:
        return {
            "type": "object",
            "fields": {
                decoded_key(child): describe_column(child) for child in children
            },
        }
    scalar = SCALAR_TYPES.get(declared_type)
    if scalar is None:
        raise DatapackError(
            f"no datapack type for {declared_type!r} (field {column.get('field')})"
        )
    return {"type": scalar}


def _enum_members(enum: dict[str, object]) -> list[str]:
    """Member names in value order ({"0": "MT_NONE", "1": ...})."""
    return [str(enum[value]) for value in sorted(enum, key=int)]
