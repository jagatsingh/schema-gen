# ruff: noqa: UP042, UP045
"""Regression tests for `inspect.cleandoc` on class docstrings.

Python preserves per-line indentation inside ``__doc__``; without
`inspect.cleandoc` (or equivalent dedent), schema-gen propagates that
source-file whitespace verbatim into JSON schema ``description``
fields, Zod TS doc-comments, Rust ``///`` lines, and Pydantic
docstrings — adding noisy leading spaces on every body line.

Covers both schema-class and enum-class paths.
"""

from enum import Enum
from pathlib import Path

from schema_gen import Field, Schema
from schema_gen.core.schema import SchemaRegistry
from schema_gen.generators.jsonschema_generator import JsonSchemaGenerator
from schema_gen.generators.pydantic_generator import PydanticGenerator
from schema_gen.generators.rust_generator import RustGenerator
from schema_gen.generators.zod_generator import ZodGenerator
from schema_gen.parsers.schema_parser import SchemaParser


def _reset_registry() -> None:
    SchemaRegistry._schemas.clear()


def test_schema_docstring_is_dedented():
    _reset_registry()

    @Schema
    class WithMultilineDoc:
        """Summary line.

        Body line one.
        Body line two.
        """

        f: int = Field(description="x")

    parser = SchemaParser()
    parsed = parser.parse_schema(WithMultilineDoc)

    # Body lines must lose the 4-space leading indent that Python
    # preserves on the raw `__doc__`.
    assert parsed.description is not None
    assert "Summary line." in parsed.description
    assert "\nBody line one.\n" in parsed.description
    assert "\n    Body line one." not in parsed.description


def test_enum_docstring_is_dedented():
    _reset_registry()

    class Mode(str, Enum):
        """Summary line.

        Body line one.
        """

        A = "a"
        B = "b"

    @Schema
    class Holder:
        m: Mode = Field(description="m")

    parser = SchemaParser()
    schemas = [parser.parse_schema(Holder)]

    enum_def = next(iter(schemas[0].enums))
    assert "Summary line." in enum_def.docstring
    assert "\nBody line one." in enum_def.docstring
    assert "\n    Body line one." not in enum_def.docstring


def test_jsonschema_description_is_dedented():
    """End-to-end: dedent applies through to the JSON Schema output."""
    _reset_registry()

    @Schema
    class WithMultilineDoc:
        """Summary line.

        Body line one.
        Body line two.
        """

        f: int = Field(description="x")

    parser = SchemaParser()
    parsed = parser.parse_schema(WithMultilineDoc)
    out = JsonSchemaGenerator().generate_file(parsed)

    import json

    schema_def = json.loads(out)["$defs"]["WithMultilineDoc"]
    desc = schema_def["description"]
    assert "Body line one." in desc
    assert "    Body line one." not in desc, (
        "JSON Schema description must not carry source-file indentation"
    )


def test_single_line_docstring_unchanged():
    """`inspect.cleandoc` on a flat single-line docstring is a no-op."""
    _reset_registry()

    @Schema
    class Flat:
        """Just one line."""

        f: int = Field(description="x")

    parser = SchemaParser()
    parsed = parser.parse_schema(Flat)
    assert parsed.description == "Just one line."


def test_no_docstring_yields_none():
    """Regression guard: schemas without a docstring keep `description=None`."""
    _reset_registry()

    @Schema
    class NoDoc:
        f: int = Field(description="x")

    parser = SchemaParser()
    parsed = parser.parse_schema(NoDoc)
    assert parsed.description is None


def test_all_generators_run_without_error_on_dedented_docstring(tmp_path: Path):
    """Smoke test: every code-emitting generator handles the dedented form."""
    _reset_registry()

    @Schema
    class Multi:
        """Summary.

        Body line.
        """

        f: int = Field(description="x")

    parser = SchemaParser()
    schemas = [parser.parse_schema(Multi)]

    # Each call below would raise on a regression that broke a generator.
    PydanticGenerator().get_extra_files(schemas, tmp_path)
    RustGenerator().generate_file(schemas[0])
    ZodGenerator().generate_file(schemas[0])
    JsonSchemaGenerator().generate_file(schemas[0])
