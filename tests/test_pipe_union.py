"""Tests for Python 3.12+ pipe union syntax (A | B) handling."""

from __future__ import annotations

from typing import Annotated, Literal

from schema_gen import Field, Schema
from schema_gen.core.schema import SchemaRegistry
from schema_gen.core.usr import FieldType
from schema_gen.parsers.schema_parser import SchemaParser

# ------------------------------------------------------------------
# Module-level @Schema classes (required for forward-reference resolution)
# ------------------------------------------------------------------


@Schema
class _PipeSchemaA:
    tag: Literal["a"]
    value: int


@Schema
class _PipeSchemaB:
    tag: Literal["b"]
    value: str


@Schema
class _PipeUnionHolder:
    value: _PipeSchemaA | _PipeSchemaB


@Schema
class _PipeOptionalHolder:
    value: str | None = None


@Schema
class _PipeDiscriminatedHolder:
    leg: Annotated[_PipeSchemaA | _PipeSchemaB, Field(discriminator="tag")]


# ------------------------------------------------------------------
# Tests
# ------------------------------------------------------------------


def _parse(cls):
    SchemaRegistry._schemas.clear()
    for c in (
        _PipeSchemaA,
        _PipeSchemaB,
        _PipeUnionHolder,
        _PipeOptionalHolder,
        _PipeDiscriminatedHolder,
    ):
        SchemaRegistry.register(c)
    return SchemaParser().parse_schema(cls)


class TestPipeUnionSyntax:
    """Python 3.12+ pipe union (A | B) must be handled like Union[A, B]."""

    def test_pipe_union_detected_as_union_type(self):
        schema = _parse(_PipeUnionHolder)
        field = next(f for f in schema.fields if f.name == "value")
        assert field.type == FieldType.UNION
        assert len(field.union_types) == 2

    def test_pipe_optional_syntax(self):
        schema = _parse(_PipeOptionalHolder)
        field = next(f for f in schema.fields if f.name == "value")
        assert field.optional is True

    def test_pipe_union_discriminated(self):
        schema = _parse(_PipeDiscriminatedHolder)
        field = next(f for f in schema.fields if f.name == "leg")
        assert field.type == FieldType.UNION
        assert field.discriminator == "tag"
        assert len(field.union_types) == 2
        assert len(field.union_tag_values) == 2
