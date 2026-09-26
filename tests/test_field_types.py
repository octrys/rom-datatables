from __future__ import annotations

import pytest

from rom_datatables.config import DatapackError
from rom_datatables.field_types import FieldType, describe_column, describe_fields
from rom_datatables.source_schema import Column

VECTOR3: Column = {
    "field": "AAAAAAAAAAA",
    "name": "position",
    "type": "UnityEngine.Vector3",
    "fields": [
        {"field": "x", "type": "System.Single"},
        {"field": "y", "type": "System.Single"},
    ],
}


@pytest.mark.parametrize(
    ("column", "expected"),
    [
        ({"field": "A", "type": "System.Boolean"}, {"type": "bool"}),
        ({"field": "A", "type": "System.UInt32"}, {"type": "uint32"}),
        ({"field": "A", "type": "System.Int64"}, {"type": "int64"}),
        ({"field": "A", "type": "System.String"}, {"type": "string"}),
        (
            {"field": "A", "type": "OBF.ENUM", "enum": {"10": "B", "2": "A"}},
            {"type": "enum", "values": ["A", "B"]},
        ),
        (
            {
                "field": "A",
                "type": "System.Collections.Generic.List<System.Int32>",
                "list": True,
            },
            {"type": "list", "items": {"type": "int32"}},
        ),
        (
            {"field": "A", "type": "System.Single[]", "list": True},
            {"type": "list", "items": {"type": "float32"}},
        ),
        (
            {
                "field": "A",
                "type": "System.Collections.Generic.List<OBF.ENUM>",
                "list": True,
                "enum": {"1": "PT_ITEM"},
            },
            {"type": "list", "items": {"type": "enum", "values": ["PT_ITEM"]}},
        ),
        (
            {"field": "A", "type": "OBF.ROW[]", "list": True, "fields": [VECTOR3]},
            {
                "type": "list",
                "items": {
                    "type": "object",
                    "fields": {
                        "position": {
                            "type": "object",
                            "fields": {
                                "x": {"type": "float32"},
                                "y": {"type": "float32"},
                            },
                        }
                    },
                },
            },
        ),
    ],
)
def test_describe_column(column: Column, expected: FieldType) -> None:
    assert describe_column(column) == expected


@pytest.mark.parametrize(
    ("column", "message"),
    [
        ({"field": "A", "type": "System.Decimal"}, r"'System.Decimal' \(field A\)"),
        ({"field": "A", "type": "OBF.SET", "list": True}, "has no element type"),
    ],
)
def test_describe_column_fails_on_unknown_type(column: Column, message: str) -> None:
    with pytest.raises(DatapackError, match=message):
        describe_column(column)


def test_describe_fields_follows_output_nesting() -> None:
    columns: list[Column] = [
        {"field": "DNIEOGFIAHC", "name": "index", "type": "System.Int32"},
        VECTOR3,
    ]

    types = describe_fields(columns, {"id": "index", "at": {"x": "position.x"}})

    assert types == {
        "id": {"type": "int32"},
        "at": {"type": "object", "fields": {"x": {"type": "float32"}}},
    }
