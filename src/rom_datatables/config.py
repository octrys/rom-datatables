"""Load datapack.toml and the per-entity schemas under schema/."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path


class DatapackError(Exception):
    """A config, schema or source problem that makes the datapack wrong."""


# Output field spec: a dot-path into the source row, or a table of nested
# output fields (an object in the output).
type FieldSpec = str | dict[str, FieldSpec]

# A schema only selects and renames source fields: every source row is kept.
SCHEMA_KEYS = frozenset({"source", "key", "fields"})


@dataclass(frozen=True)
class EntitySchema:
    """How one source table becomes one datapack entity."""

    name: str
    source: str
    key: str
    fields: dict[str, FieldSpec]


@dataclass(frozen=True)
class PackConfig:
    source_dir: Path
    schema_dir: Path
    output_dir: Path
    explore_dir: Path
    client_release: str
    schema_version: int


def load_config(path: Path) -> PackConfig:
    document = _read_toml(path)
    base_dir = path.parent
    paths = _require_table(document, "paths", path)
    meta = _require_table(document, "meta", path)
    return PackConfig(
        source_dir=_resolve(base_dir, _require_str(paths, "source", path)),
        schema_dir=_resolve(base_dir, _require_str(paths, "schema", path)),
        output_dir=_resolve(base_dir, _require_str(paths, "output", path)),
        explore_dir=_resolve(base_dir, _require_str(paths, "explore", path)),
        client_release=_require_str(meta, "client_release", path),
        schema_version=_require_int(meta, "schema_version", path),
    )


def load_schemas(schema_dir: Path) -> list[EntitySchema]:
    """Every schema/<entity>.toml, ordered by entity name."""
    paths = sorted(schema_dir.glob("*.toml"))
    if not paths:
        raise DatapackError(f"no entity schemas (*.toml) in {schema_dir}")
    return [load_schema(path) for path in paths]


def load_schema(path: Path) -> EntitySchema:
    document = _read_toml(path)
    unknown_keys = sorted(set(document) - SCHEMA_KEYS)
    if unknown_keys:
        raise DatapackError(
            f"{path}: unknown keys {unknown_keys}; a schema has only "
            f"{sorted(SCHEMA_KEYS)}"
        )
    fields = _load_fields(_require_table(document, "fields", path), "fields", path)
    key = _require_str(document, "key", path)
    if not isinstance(fields.get(key), str):
        raise DatapackError(f"{path}: key {key!r} is not a top-level output field")
    return EntitySchema(
        name=path.stem,
        source=_require_str(document, "source", path),
        key=key,
        fields=fields,
    )


def _load_fields(
    table: dict[str, object], prefix: str, path: Path
) -> dict[str, FieldSpec]:
    if not table:
        raise DatapackError(f"{path}: [{prefix}] has no fields")
    fields: dict[str, FieldSpec] = {}
    for output_field, spec in table.items():
        name = f"{prefix}.{output_field}"
        if isinstance(spec, dict):
            fields[output_field] = _load_fields(spec, name, path)
        elif isinstance(spec, str) and spec:
            fields[output_field] = spec
        else:
            raise DatapackError(
                f"{path}: {name} must be a dot-path string or a table of fields"
            )
    return fields


def _read_toml(path: Path) -> dict[str, object]:
    try:
        with path.open("rb") as handle:
            return tomllib.load(handle)
    except FileNotFoundError as error:
        raise DatapackError(f"file not found: {path}") from error
    except tomllib.TOMLDecodeError as error:
        raise DatapackError(f"{path}: invalid TOML: {error}") from error


def _resolve(base_dir: Path, value: str) -> Path:
    candidate = Path(value).expanduser()
    return candidate if candidate.is_absolute() else (base_dir / candidate).resolve()


def _require_table(
    document: dict[str, object], name: str, path: Path
) -> dict[str, object]:
    value = document.get(name)
    if not isinstance(value, dict):
        raise DatapackError(f"{path}: missing [{name}] table")
    return value


def _require_str(document: dict[str, object], name: str, path: Path) -> str:
    value = document.get(name)
    if not isinstance(value, str) or not value:
        raise DatapackError(f"{path}: {name} must be a non-empty string")
    return value


def _require_int(document: dict[str, object], name: str, path: Path) -> int:
    value = document.get(name)
    if not isinstance(value, int) or isinstance(value, bool):
        raise DatapackError(f"{path}: {name} must be an integer")
    return value
