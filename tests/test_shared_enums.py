# ruff: noqa: UP042, UP045
"""Tests for issue #43: shared enums extracted to _enums.py.

When multiple @Schema classes reference the same enum, the Pydantic generator
must declare the enum once in ``_enums.py`` and import it in each per-schema
module — not duplicate the class in every file.
"""

from enum import Enum
from pathlib import Path

from schema_gen import Field, Schema
from schema_gen.core.schema import SchemaRegistry
from schema_gen.generators.pydantic_generator import PydanticGenerator
from schema_gen.parsers.schema_parser import SchemaParser


class TestSharedEnums:
    """Issue #43: shared enums must live in _enums.py, not duplicated."""

    def setup_method(self):
        SchemaRegistry._schemas.clear()

    def _make_schemas(self):
        """Create two schemas that share the same enum."""

        class OptionType(str, Enum):
            CE = "CE"
            PE = "PE"

        @Schema
        class OrderRequest:
            option_type: OptionType = Field(description="option type")

        @Schema
        class PositionLeg:
            option_type: OptionType = Field(description="leg option type")

        parser = SchemaParser()
        return [parser.parse_schema(OrderRequest), parser.parse_schema(PositionLeg)]

    def test_get_extra_files_emits_enums_py(self):
        """get_extra_files() should produce _enums.py with all enums."""
        schemas = self._make_schemas()
        gen = PydanticGenerator()
        extra = gen.get_extra_files(schemas, Path("/tmp/out"))

        assert "_enums.py" in extra
        content = extra["_enums.py"]

        # Enum is declared exactly once in _enums.py
        assert "class OptionType(str, Enum):" in content
        assert content.count("class OptionType") == 1
        assert 'CE = "CE"' in content
        assert 'PE = "PE"' in content

    def test_per_schema_file_imports_enum(self):
        """Per-schema files must import from ._enums, not declare inline."""
        schemas = self._make_schemas()
        gen = PydanticGenerator()

        # Simulate the generation pipeline: extra files first, then per-schema
        gen.get_extra_files(schemas, Path("/tmp/out"))

        for schema in schemas:
            code = gen.generate_file(schema)
            # Must import from _enums
            assert "from ._enums import OptionType" in code, (
                f"Schema {schema.name} should import OptionType from _enums"
            )
            # Must NOT declare the enum class inline
            assert "class OptionType" not in code, (
                f"Schema {schema.name} should not declare OptionType inline"
            )
            # Must NOT import Enum (no inline enums)
            assert "from enum import Enum" not in code, (
                f"Schema {schema.name} should not import Enum stdlib"
            )

    def test_index_re_exports_enums(self):
        """__init__.py must re-export enums from _enums module."""
        schemas = self._make_schemas()
        gen = PydanticGenerator()
        gen.get_extra_files(schemas, Path("/tmp/out"))

        index = gen.generate_index(schemas, Path("/tmp/out"))
        assert index is not None

        # Enum imported from _enums, not from per-schema modules
        assert "from ._enums import OptionType" in index
        assert '"OptionType"' in index

    def test_single_schema_still_inlines_enum(self):
        """When generate_file() is called without get_extra_files(), enum is inlined."""

        class OptionType(str, Enum):
            CE = "CE"
            PE = "PE"

        @Schema
        class Solo:
            option_type: OptionType = Field(description="type")

        schema = SchemaParser().parse_schema(Solo)
        gen = PydanticGenerator()
        # Do NOT call get_extra_files — simulates direct single-schema usage
        code = gen.generate_file(schema)

        # Should inline the enum
        assert "class OptionType(str, Enum):" in code
        assert 'CE = "CE"' in code

    def test_enum_dedup_across_schemas(self):
        """Same enum name appearing in multiple schemas produces one entry."""
        schemas = self._make_schemas()
        gen = PydanticGenerator()
        extra = gen.get_extra_files(schemas, Path("/tmp/out"))
        content = extra["_enums.py"]

        # Only one class definition
        assert content.count("class OptionType") == 1

    def test_no_enums_no_extra_file(self):
        """Schemas with no enums should not produce _enums.py."""

        @Schema
        class Plain:
            name: str = Field(description="name")

        schema = SchemaParser().parse_schema(Plain)
        gen = PydanticGenerator()
        extra = gen.get_extra_files([schema], Path("/tmp/out"))
        assert extra == {}
