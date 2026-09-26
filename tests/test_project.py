from __future__ import annotations

import json
from pathlib import Path

import pytest

from rom_datatables.config import (
    DatapackError,
    EntitySchema,
    PackConfig,
    load_config,
    load_schemas,
)
from rom_datatables.project import build_datapack, project_rows, read_source_table

MAP_SCHEMA = EntitySchema(
    name="map",
    source="Map_Data",
    key="id",
    fields={
        "id": "index",
        "type": "mapType",
        "map_size": {"width": "mapSize.width", "height": "mapSize.height"},
    },
)


def map_row(index: int, map_type: str = "MT_FIELD") -> dict[str, object]:
    return {
        "index": index,
        "mapType": map_type,
        "mapSize": {"width": 300, "height": 200},
    }


def write_source_table(source_dir: Path, table: str, rows: dict[str, object]) -> None:
    tables_dir = source_dir / "tables"
    tables_dir.mkdir(parents=True, exist_ok=True)
    (tables_dir / f"{table}.json").write_text(json.dumps(rows), encoding="utf-8")


def write_source_schema(source_dir: Path) -> None:
    int32 = {"type": "System.Int32", "naming": "confirmed"}
    confirmed = [
        {"field": "DNIEOGFIAHC", "name": "index", **int32},
        {
            "field": "FGNGEPEHCGC",
            "name": "mapType",
            "naming": "confirmed",
            "type": "FMMMEMCIFJF.DOENAADJPFF.OCOPGEPOLPA",
            "enum": {"2": "MT_FIELD", "0": "MT_NONE"},
        },
        {
            "field": "MFGNLFAOAGB",
            "name": "mapSize",
            "naming": "confirmed",
            "type": "EONGMLLJMOC.NGADEEAOLGP",
            "fields": [
                {"field": "BPFBMIDLJKI", "name": "width", **int32},
                {"field": "JJGJIEJMNMM", "name": "height", **int32},
            ],
        },
    ]
    schema = {"Map_Data": {"name": "Map_Data", "fields": confirmed}}
    (source_dir / "schema.json").write_text(json.dumps(schema), encoding="utf-8")


EXPECTED_MAP = {"id": 1, "type": "MT_FIELD", "map_size": {"width": 300, "height": 200}}


def test_project_rows_selects_and_renames_keeping_nesting() -> None:
    rows = project_rows(MAP_SCHEMA, [map_row(1)])

    assert rows == [EXPECTED_MAP]


def test_project_rows_keeps_every_row() -> None:
    rows = project_rows(
        MAP_SCHEMA,
        [map_row(1), map_row(2, "MT_TRIAL_TOWER"), map_row(501, "MT_TUTORIAL")],
    )

    assert [row["id"] for row in rows] == [1, 2, 501]


@pytest.mark.parametrize(
    ("row", "message"),
    [
        ({"index": 1, "mapType": "MT_FIELD"}, "'mapSize.width' not found at 'mapSize'"),
        ({"index": 1, "mapType": "MT_FIELD", "mapSize": 7}, "not found at 'width'"),
        (
            {"index": 1, "mapType": "MT_FIELD", "mapSize": {"width": 1}},
            "'mapSize.height' not found at 'height'",
        ),
        ({"index": 1, "mapSize": {"width": 1}}, "'mapType' not found"),
    ],
)
def test_project_rows_fails_on_missing_source_path(
    row: dict[str, object], message: str
) -> None:
    with pytest.raises(DatapackError, match=message):
        project_rows(MAP_SCHEMA, [row])


def test_project_rows_fails_on_duplicate_key() -> None:
    with pytest.raises(DatapackError, match="duplicate id=1"):
        project_rows(MAP_SCHEMA, [map_row(1), map_row(1)])


def test_read_source_table_orders_keys_numerically(tmp_path: Path) -> None:
    write_source_table(tmp_path, "Map_Data", {"10": map_row(10), "9": map_row(9)})

    rows = read_source_table(tmp_path, "Map_Data")

    assert [row["index"] for row in rows] == [9, 10]


def test_read_source_table_fails_when_missing(tmp_path: Path) -> None:
    with pytest.raises(DatapackError, match="source table not found"):
        read_source_table(tmp_path, "Map_Data")


def test_build_datapack_writes_entities_and_version(tmp_path: Path) -> None:
    source_dir = tmp_path / "source"
    output_dir = tmp_path / "datapack"
    write_source_table(source_dir, "Map_Data", {"1": map_row(1)})
    write_source_schema(source_dir)
    config = PackConfig(
        source_dir=source_dir,
        schema_dir=tmp_path / "schema",
        output_dir=output_dir,
        explore_dir=tmp_path / "explore",
        client_release="TestRelease",
        schema_version=3,
    )

    build_datapack(config, [MAP_SCHEMA])

    maps = json.loads((output_dir / "map.json").read_text(encoding="utf-8"))
    version = json.loads((output_dir / "version.json").read_text(encoding="utf-8"))
    assert maps == [EXPECTED_MAP]
    assert version == {
        "client_release": "TestRelease",
        "schema_version": 3,
        "entities": {
            "map": {
                "source": "Map_Data",
                "rows": 1,
                "fields": {
                    "id": {"type": "int32"},
                    "type": {"type": "enum", "values": ["MT_NONE", "MT_FIELD"]},
                    "map_size": {
                        "type": "object",
                        "fields": {
                            "width": {"type": "int32"},
                            "height": {"type": "int32"},
                        },
                    },
                },
            }
        },
    }


def write_schema(schema_dir: Path, body: str) -> None:
    (schema_dir / "map.toml").write_text(
        f'source = "Map_Data"\nkey = "id"\n{body}', encoding="utf-8"
    )


def test_load_schemas_reads_nested_fields(tmp_path: Path) -> None:
    write_schema(
        tmp_path,
        '[fields]\nid = "index"\n[fields.map_size]\nwidth = "mapSize.width"\n',
    )

    [schema] = load_schemas(tmp_path)

    assert schema.fields == {"id": "index", "map_size": {"width": "mapSize.width"}}


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ('[fields]\nname = "mapName"\n', "key 'id' is not a top-level"),
        ('[fields.id]\nvalue = "index"\n', "key 'id' is not a top-level"),
        ('[fields]\nid = "index"\n[fields.map_size]\n', r"\[fields.map_size\] has no"),
        ("[fields]\nid = 1\n", "fields.id must be a dot-path string"),
        (
            '[fields]\nid = "index"\n[filter]\nfield = "mapType"\n',
            r"unknown keys \['filter'\]",
        ),
    ],
)
def test_load_schemas_rejects_invalid_fields(
    tmp_path: Path, body: str, message: str
) -> None:
    write_schema(tmp_path, body)

    with pytest.raises(DatapackError, match=message):
        load_schemas(tmp_path)


def test_repo_config_and_schemas_load() -> None:
    repo_dir = Path(__file__).resolve().parent.parent

    config = load_config(repo_dir / "datapack.toml")
    schemas = load_schemas(config.schema_dir)

    assert [schema.name for schema in schemas] == ["map"]


def test_build_datapack_fails_without_source_schema(tmp_path: Path) -> None:
    write_source_table(tmp_path, "Map_Data", {"1": map_row(1)})
    config = PackConfig(
        source_dir=tmp_path,
        schema_dir=tmp_path / "schema",
        output_dir=tmp_path / "datapack",
        explore_dir=tmp_path / "explore",
        client_release="TestRelease",
        schema_version=1,
    )

    with pytest.raises(DatapackError, match="source schema not found"):
        build_datapack(config, [MAP_SCHEMA])
