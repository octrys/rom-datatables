"""Check schema dot-paths against the naming status in source/schema.json.

rom-tools marks every column with how its name was established. Only reviewed
names may cross into the datapack: an obfuscated identifier changes every
client build, and a suggested or tentative name may still be wrong.
"""

from __future__ import annotations

from rom_datatables.config import DatapackError, EntitySchema, FieldSpec
from rom_datatables.source_schema import (
    Column,
    child_columns,
    decoded_key,
    find_column,
    table_columns,
)

# confirmed: reviewed in rom-tools' names.toml. plaintext: never obfuscated.
ALLOWED_NAMING = frozenset({"confirmed", "plaintext"})


def check_naming(source_schema: dict[str, object], schemas: list[EntitySchema]) -> None:
    """Fail listing every schema path that goes through an unreviewed name."""
    problems: list[str] = []
    for schema in schemas:
        columns = table_columns(source_schema, schema.source)
        for source_path in source_paths(schema.fields):
            problems.extend(
                f"[{schema.name}] {problem}"
                for problem in _check_path(columns, source_path)
            )
    if problems:
        allowed = ", ".join(sorted(ALLOWED_NAMING))
        raise DatapackError(
            f"schema uses fields whose naming is not {allowed}:\n  "
            + "\n  ".join(problems)
        )


def source_paths(fields: dict[str, FieldSpec]) -> list[str]:
    """Every dot-path a schema reads, in schema order."""
    paths: list[str] = []
    for spec in fields.values():
        if isinstance(spec, str):
            paths.append(spec)
        else:
            paths.extend(source_paths(spec))
    return paths


def _check_path(columns: list[Column], source_path: str) -> list[str]:
    """Problems along one dot-path, plus under the object it ends at."""
    parts = source_path.split(".")
    for depth, part in enumerate(parts):
        column = find_column(columns, part)
        where = ".".join(parts[: depth + 1])
        if column is None:
            return [f"{source_path!r}: {where!r} not in source schema.json"]
        if column.get("naming") not in ALLOWED_NAMING:
            return [f"{source_path!r}: {where!r} is {_describe(column)}"]
        children = child_columns(column)
        if depth == len(parts) - 1:
            return _check_subtree(children, source_path, source_path)
        if children is None or column.get("list"):
            return [f"{source_path!r}: {where!r} has no fields to go into"]
        columns = children
    return []


def _check_subtree(
    columns: list[Column] | None, prefix: str, source_path: str
) -> list[str]:
    """A path ending at an object copies it whole: every column in it counts."""
    if columns is None:
        return []
    problems: list[str] = []
    for column in columns:
        inner = f"{prefix}.{decoded_key(column)}"
        if column.get("naming") not in ALLOWED_NAMING:
            problems.append(
                f"{source_path!r} copies {inner!r}, which is {_describe(column)}"
            )
        problems.extend(_check_subtree(child_columns(column), inner, source_path))
    return problems


def _describe(column: Column) -> str:
    return f"{column.get('naming')} (field {column.get('field')})"
