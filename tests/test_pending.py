from __future__ import annotations

from rom_datatables.config import EntitySchema, FieldSpec
from rom_datatables.pending import PendingField, find_pending
from rom_datatables.source_schema import Column


def column(
    name: str | None,
    naming: str,
    type_name: str = "System.Int32",
    children: list[Column] | None = None,
    is_list: bool = False,
) -> Column:
    result: Column = {"field": name or "OBFUSCATEDX", "naming": naming}
    result["type"] = type_name
    if name is not None:
        result["name"] = name
    if children is not None:
        result["fields"] = children
    if is_list:
        result["list"] = True
    return result


COLUMNS: list[Column] = [
    column("index", "confirmed"),
    column("capacity", "tentative"),
    column(
        "mapSize",
        "confirmed",
        "OBF.SIZE",
        [column("width", "confirmed"), column("height", "confirmed")],
    ),
    column(
        "scene",
        "confirmed",
        "OBF.SCENE",
        [column("name", "confirmed", "System.String"), column("bundle", "confirmed")],
    ),
    column("buffs", "confirmed", "System.Int32[]", is_list=True),
    column(None, "obfuscated", "OBF.FLAGS", [column("minimap", "confirmed")]),
]

ROWS: list[dict[str, object]] = [
    {
        "index": 1,
        "mapSize": {"width": 300, "height": 300},
        "scene": {"name": "Beach_Forest"},
        "buffs": [5000001],
    }
]


def pending_paths(fields: dict[str, FieldSpec]) -> list[str]:
    schema = EntitySchema(name="map", source="Map_Data", key="id", fields=fields)
    return [field.source_path for field in find_pending(COLUMNS, schema, ROWS)]


def test_lists_usable_fields_the_schema_does_not_read() -> None:
    paths = pending_paths({"id": "index", "size": {"width": "mapSize.width"}})

    assert paths == ["mapSize.height", "scene.name", "scene.bundle", "buffs"]


def test_copied_object_covers_its_fields() -> None:
    paths = pending_paths({"id": "index", "size": "mapSize", "scene": "scene"})

    assert paths == ["buffs"]


def test_skips_unreviewed_names_and_fields_under_them() -> None:
    paths = pending_paths(
        {"id": "index", "size": "mapSize", "scene": "scene", "buffs": "buffs"}
    )

    assert paths == []


def test_reports_type_and_whether_every_row_has_it() -> None:
    schema = EntitySchema(
        name="map",
        source="Map_Data",
        key="id",
        fields={"id": "index", "size": "mapSize", "scene": {"name": "scene.name"}},
    )

    pending = find_pending(COLUMNS, schema, ROWS)

    assert pending == [
        PendingField("scene.bundle", "int32", is_in_every_row=False),
        PendingField("buffs", "list<int32>", is_in_every_row=True),
    ]
