# ruff: noqa: UP042, UP045
"""Tests for:

- #70: Pydantic generator must escape double quotes inside ``description=``
  values (and other string config) so the emitted Python parses.
- #71: Enum class docstrings must be propagated to the Pydantic, Rust, Zod,
  and JSON Schema targets.
"""

import ast
from enum import Enum
from pathlib import Path

from schema_gen import Field, Schema
from schema_gen.core.schema import SchemaRegistry
from schema_gen.generators.jsonschema_generator import JsonSchemaGenerator
from schema_gen.generators.pydantic_generator import PydanticGenerator
from schema_gen.generators.rust_generator import RustGenerator
from schema_gen.generators.zod_generator import ZodGenerator
from schema_gen.parsers.schema_parser import SchemaParser

# ---------------------------------------------------------------------------
# Fixtures shared across the tests
# ---------------------------------------------------------------------------


_ENUM_DOC = (
    "Footprint candle window durations.\n\n"
    "Adding a new timeframe therefore requires coordinated updates in "
    "three places: this enum, the backend duration-lookup table, and "
    "the frontend constant."
)


def _reset_registry() -> None:
    SchemaRegistry._schemas.clear()


def _parse_schema_with_quoted_description() -> list:
    """Schema with a literal ``"`` inside ``Field(description=...)`` (#70)."""

    _reset_registry()

    @Schema
    class QuoteDescMsg:
        type: str = Field(
            description='Discriminator — required; must equal "gap_detected"',
        )

    parser = SchemaParser()
    return [parser.parse_schema(QuoteDescMsg)]


def _parse_schema_with_docstring_enum() -> list:
    """Schema referencing an enum that carries a class docstring (#71)."""

    _reset_registry()

    class Timeframe(str, Enum):
        """Footprint candle window durations.

        Adding a new timeframe therefore requires coordinated updates in
        three places: this enum, the backend duration-lookup table, and
        the frontend constant.
        """

        M1 = "1m"
        M3 = "3m"
        M5 = "5m"

    @Schema
    class Candle:
        timeframe: Timeframe = Field(description="window")

    parser = SchemaParser()
    return [parser.parse_schema(Candle)]


# ---------------------------------------------------------------------------
# #70 — description quoting
# ---------------------------------------------------------------------------


class TestPydanticDescriptionEscaping:
    def test_inner_quotes_dont_break_python_parse(self):
        schemas = _parse_schema_with_quoted_description()
        gen = PydanticGenerator()
        extra = gen.get_extra_files(schemas, Path("/tmp/out"))
        model_code = gen.generate_model(schemas[0])

        # Must parse as valid Python regardless of what the description
        # contains — this is the regression we're guarding against.
        ast.parse(model_code)
        for content in extra.values():
            ast.parse(content)

        # And the description text itself must round-trip: the inner
        # quotes should be escaped, not dropped.
        assert 'must equal \\"gap_detected\\"' in model_code


# ---------------------------------------------------------------------------
# #71 — enum class docstrings
# ---------------------------------------------------------------------------


class TestEnumDocstringPropagation:
    def test_pydantic_emits_class_docstring(self):
        schemas = _parse_schema_with_docstring_enum()
        gen = PydanticGenerator()
        extra = gen.get_extra_files(schemas, Path("/tmp/out"))
        enums_py = extra["_enums.py"]

        # The generated file must still be valid Python.
        ast.parse(enums_py)
        assert "Footprint candle window durations." in enums_py
        assert "coordinated updates" in enums_py

    def test_rust_emits_doc_comments(self):
        schemas = _parse_schema_with_docstring_enum()
        gen = RustGenerator()
        rust_code = gen.generate_file(schemas[0])

        assert "/// Footprint candle window durations." in rust_code
        assert "coordinated updates" in rust_code

    def test_zod_emits_jsdoc_block(self):
        schemas = _parse_schema_with_docstring_enum()
        gen = ZodGenerator()
        ts_code = gen.generate_file(schemas[0])

        assert "/**" in ts_code
        assert "Footprint candle window durations." in ts_code
        assert "coordinated updates" in ts_code

    def test_jsonschema_emits_description_field(self):
        schemas = _parse_schema_with_docstring_enum()
        gen = JsonSchemaGenerator()
        schema_json = gen.generate_file(schemas[0])

        # JsonSchemaGenerator.generate returns JSON text.
        import json

        parsed = json.loads(schema_json)
        enum_def = parsed["$defs"]["Timeframe"]
        assert "description" in enum_def
        assert "Footprint candle window durations." in enum_def["description"]

    def test_enum_without_docstring_unchanged(self):
        """Regression guard: enums with no docstring must still work."""

        _reset_registry()

        class Plain(str, Enum):
            A = "a"
            B = "b"

        @Schema
        class Holder:
            p: Plain = Field(description="plain")

        parser = SchemaParser()
        schemas = [parser.parse_schema(Holder)]

        PydanticGenerator().get_extra_files(schemas, Path("/tmp/out"))
        RustGenerator().generate_file(schemas[0])
        ZodGenerator().generate_file(schemas[0])
        JsonSchemaGenerator().generate_file(schemas[0])

        # If any generator regressed to assume docstring exists this
        # would have raised by now.
