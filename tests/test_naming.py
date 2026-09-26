from __future__ import annotations

import pytest

from rom_datatables.config import DatapackError, EntitySchema, FieldSpec
from rom_datatables.naming import check_naming


def column(
    field: str,
    name: str | None,
    naming: str,
    children: list[dict[str, object]] | None = None,
    is_list: bool = False,
) -> dict[str, object]:
    result: dict[str, object] = {"field": field, "naming": naming}
    if name is not None:
        result["name"] = name
    if children is not None:
        result["fields"] = children
    if is_list:
        result["list"] = True
    return result


SOURCE_SCHEMA: dict[str, object] = {
    "Map_Data": {
        "name": "Map_Data",
        "fields": [
            column("DNIEOGFIAHC", "index", "confirmed"),
            column("LFEOJGHOCLC", "mapName", "suggested"),
            column("JDPOGLGHHIB", None, "obfuscated"),
            column(
                "MFGNLFAOAGB",
                "mapSize",
                "confirmed",
                [
                    column("BPFBMIDLJKI", "width", "confirmed"),
                    column("JJGJIEJMNMM", "height", "confirmed"),
                ],
            ),
            column(
                "PHLMAFEGEKD",
                "scene",
                "confirmed",
                [
                    column("COBIGMMMLJP", "name", "confirmed"),
                    column("KGCCDLKLPKA", "bundle", "tentative"),
                ],
            ),
            column(
                "AAAAAAAAAAA", "position", "confirmed", [column("x", None, "plaintext")]
            ),
            column("BBBBBBBBBBB", "buffs", "confirmed", [], is_list=True),
        ],
    },
    "LocalName": {"name": "LocalName", "kind": "string-map"},
}


def map_schema(fields: dict[str, FieldSpec], source: str = "Map_Data") -> EntitySchema:
    return EntitySchema(name="map", source=source, key="id", fields=fields)


@pytest.mark.parametrize(
    "fields",
    [
        {"id": "index"},
        {"id": "index", "size": {"width": "mapSize.width"}},
        {"id": "index", "size": "mapSize"},
        {"id": "index", "scene": {"name": "scene.name"}},
        {"id": "index", "x": "position.x"},
        {"id": "index", "position": "position"},
    ],
)
def test_check_naming_accepts_confirmed_and_plaintext(
    fields: dict[str, FieldSpec],
) -> None:
    check_naming(SOURCE_SCHEMA, [map_schema(fields)])


@pytest.mark.parametrize(
    ("fields", "message"),
    [
        (
            {"id": "index", "name": "mapName"},
            r"'mapName' is suggested \(field LFEOJGHOCLC\)",
        ),
        ({"id": "JDPOGLGHHIB"}, r"'JDPOGLGHHIB' is obfuscated"),
        ({"id": "index", "bundle": "scene.bundle"}, r"'scene.bundle' is tentative"),
        (
            {"id": "index", "scene": "scene"},
            r"'scene' copies 'scene.bundle', which is tentative",
        ),
        (
            {"id": "index", "depth": "mapSize.depth"},
            r"'mapSize.depth' not in source schema",
        ),
        ({"id": "index", "x": "buffs.x"}, r"'buffs' has no fields to go into"),
        ({"id": "index", "x": "index.x"}, r"'index' has no fields to go into"),
    ],
)
def test_check_naming_rejects_unreviewed_or_unknown_paths(
    fields: dict[str, FieldSpec], message: str
) -> None:
    with pytest.raises(DatapackError, match=message):
        check_naming(SOURCE_SCHEMA, [map_schema(fields)])


def test_check_naming_reports_every_problem_at_once() -> None:
    fields: dict[str, FieldSpec] = {"id": "JDPOGLGHHIB", "name": "mapName"}

    with pytest.raises(DatapackError) as caught:
        check_naming(SOURCE_SCHEMA, [map_schema(fields)])

    assert "JDPOGLGHHIB" in str(caught.value)
    assert "mapName" in str(caught.value)


@pytest.mark.parametrize(
    ("source", "message"),
    [
        ("Missing_Table", "'Missing_Table' not in source schema"),
        ("LocalName", "'LocalName' has no columns"),
    ],
)
def test_check_naming_fails_on_unusable_source_table(source: str, message: str) -> None:
    with pytest.raises(DatapackError, match=message):
        check_naming(SOURCE_SCHEMA, [map_schema({"id": "index"}, source)])
