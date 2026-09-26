from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

from rom_datatables.explore import (
    build_database,
    build_metadata,
    describe,
    flatten,
    is_stale,
    read_table,
)

SOURCE_SCHEMA: dict[str, object] = {
    "Map_Data": {
        "name": "Map_Data",
        "naming": {"confirmed": 2, "obfuscated": 1},
        "fields": [
            {
                "field": "DNIEOGFIAHC",
                "name": "index",
                "type": "System.Int32",
                "naming": "confirmed",
                "fk": "MapInfo",
            },
            {
                "field": "MFGNLFAOAGB",
                "name": "mapSize",
                "type": "OBF.SIZE",
                "naming": "confirmed",
                "fields": [
                    {
                        "field": "BPFBMIDLJKI",
                        "name": "width",
                        "type": "System.Int32",
                        "naming": "confirmed",
                    }
                ],
            },
            {
                "field": "JDPOGLGHHIB",
                "type": "System.Collections.Generic.List<System.Int32>",
                "list": True,
                "naming": "obfuscated",
            },
        ],
    },
    "MapInfo": {"name": "MapInfo", "fields": []},
}


def write_tables(tables_dir: Path) -> None:
    tables_dir.mkdir(parents=True, exist_ok=True)
    maps = {
        "10": {"index": 10, "mapSize": {"width": 300}, "JDPOGLGHHIB": [1, 2]},
        "2": {"index": 2, "mapSize": {"width": 200}, "JDPOGLGHHIB": []},
    }
    tables = {
        "Map_Data": maps,
        "MapInfo": {"2": {"index": 2}, "10": {"index": 10}},
        "Localization": {"UI_OK": "OK"},
    }
    for name, rows in tables.items():
        (tables_dir / f"{name}.json").write_text(json.dumps(rows), encoding="utf-8")


def test_flatten_nests_to_dot_paths_and_lists_to_json() -> None:
    row = {"index": 1, "mapSize": {"width": 3, "at": {"x": 1.5}}, "buffs": [1, 2]}

    assert flatten(row) == {
        "index": 1,
        "mapSize.width": 3,
        "mapSize.at.x": 1.5,
        "buffs": "[1, 2]",
    }


def test_read_table_orders_integer_keys_numerically(tmp_path: Path) -> None:
    write_tables(tmp_path)

    table = read_table(tmp_path / "Map_Data.json")

    assert table.has_integer_keys
    assert table.columns == ["index", "mapSize.width", "JDPOGLGHHIB"]
    assert table.rows == [(2, 2, 200, "[]"), (10, 10, 300, "[1, 2]")]


def test_read_table_keeps_text_tables_as_key_and_text(tmp_path: Path) -> None:
    write_tables(tmp_path)

    table = read_table(tmp_path / "Localization.json")

    assert not table.has_integer_keys
    assert table.columns == ["text"]
    assert table.rows == [("UI_OK", "OK")]


def test_build_database_writes_rows_and_foreign_keys(tmp_path: Path) -> None:
    write_tables(tmp_path / "tables")
    database_path = tmp_path / "source.db"

    build_database(tmp_path / "tables", SOURCE_SCHEMA, database_path)

    connection = sqlite3.connect(database_path)
    try:
        rows = connection.execute(
            'SELECT _key, "mapSize.width" FROM Map_Data ORDER BY _key'
        ).fetchall()
        foreign_keys = connection.execute(
            "PRAGMA foreign_key_list(Map_Data)"
        ).fetchall()
    finally:
        connection.close()
    assert rows == [(2, 200), (10, 300)]
    assert [(key[2], key[3], key[4]) for key in foreign_keys] == [
        ("MapInfo", "index", "_key")
    ]
    assert not database_path.with_suffix(".partial").exists()


def test_build_metadata_describes_flattened_columns(tmp_path: Path) -> None:
    write_tables(tmp_path)
    tables = {"Map_Data": read_table(tmp_path / "Map_Data.json")}

    metadata = build_metadata(SOURCE_SCHEMA, tables)

    table = metadata["databases"]["source"]["tables"]["Map_Data"]  # type: ignore[index]
    assert table["description"] == "columns: confirmed 2, obfuscated 1"
    assert table["columns"] == {
        "_key": "row key in the source JSON",
        "index": "confirmed · int32 · field DNIEOGFIAHC · → MapInfo",
        "mapSize.width": "confirmed · int32 · field BPFBMIDLJKI",
        "JDPOGLGHHIB": "obfuscated · list<int32>",
    }


def test_describe_cuts_long_enums_short() -> None:
    column: dict[str, object] = {
        "field": "A",
        "name": "kind",
        "type": "OBF.ENUM",
        "naming": "tentative",
        "enum": {str(value): f"K{value}" for value in range(14)},
    }

    assert describe(column) == (
        "tentative · enum · field A · "
        "K0, K1, K2, K3, K4, K5, K6, K7, K8, K9, K10, K11, … (+2)"
    )


def test_is_stale_when_a_source_file_is_newer(tmp_path: Path) -> None:
    write_tables(tmp_path / "tables")
    (tmp_path / "schema.json").write_text("{}", encoding="utf-8")
    database_path = tmp_path / "source.db"
    assert is_stale(tmp_path, database_path)

    database_path.write_bytes(b"")
    os.utime(database_path, (2_000_000_000, 2_000_000_000))
    assert not is_stale(tmp_path, database_path)

    os.utime(tmp_path / "tables" / "MapInfo.json", (2_000_000_001, 2_000_000_001))
    assert is_stale(tmp_path, database_path)
