"""Regression tests for deterministic ordering of discovered schemas and enums.

Filesystem walk order (``Path.rglob``) and ``@Schema`` registration order
are environment-dependent, so two regenerations on different machines
could previously emit ``_enums.py`` / ``index.ts`` with different class
or export ordering. We now sort by name at the parser boundary.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel

from schema_gen.core.schema import Schema, SchemaRegistry
from schema_gen.parsers.schema_parser import SchemaParser


class ZColor(Enum):
    RED = "red"


class AStatus(Enum):
    ON = "on"


class MKind(Enum):
    K = "k"


def _reset_registry() -> None:
    SchemaRegistry._schemas.clear()


def test_parse_all_schemas_sorted_by_name() -> None:
    _reset_registry()

    @Schema
    class Zeta(BaseModel):
        x: int

    @Schema
    class Alpha(BaseModel):
        x: int

    @Schema
    class Mu(BaseModel):
        x: int

    names = [s.name for s in SchemaParser().parse_all_schemas()]
    assert names == ["Alpha", "Mu", "Zeta"]


def test_parse_schema_enums_sorted_by_name() -> None:
    _reset_registry()

    @Schema
    class Thing(BaseModel):
        # Declare fields so enums are encountered in a non-alphabetical order.
        c: ZColor
        s: AStatus
        k: MKind

    usr = SchemaParser().parse_schema(Thing)
    assert [e.name for e in usr.enums] == ["AStatus", "MKind", "ZColor"]
