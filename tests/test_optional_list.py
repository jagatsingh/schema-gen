"""Regression tests for issue #64: Optional[list[T]] double-nesting bug.

Optional[list[str]] was generating Vec<Vec<String>> / z.array(z.array(z.string()))
instead of Option<Vec<String>> / z.array(z.string()).optional().
"""

from schema_gen import Field, Schema
from schema_gen.core.schema import SchemaRegistry
from schema_gen.core.usr import FieldType
from schema_gen.generators.jsonschema_generator import JsonSchemaGenerator
from schema_gen.generators.pydantic_generator import PydanticGenerator
from schema_gen.generators.rust_generator import RustGenerator
from schema_gen.generators.zod_generator import ZodGenerator
from schema_gen.parsers.schema_parser import SchemaParser


class TestOptionalListNesting:
    """Issue #64: Optional[list[T]] must NOT produce double-nested arrays."""

    def setup_method(self):
        SchemaRegistry._schemas.clear()

    def _make_schema(self):
        @Schema
        class Container:
            tags: list[str] | None = Field(default=None, description="optional list")
            names: list[str] = Field(default_factory=list, description="required list")

        return SchemaParser().parse_schema(Container)

    def test_usr_field_structure(self):
        schema = self._make_schema()
        tags = schema.get_field("tags")
        assert tags.type == FieldType.LIST
        assert tags.optional is True
        assert tags.inner_type is not None
        assert tags.inner_type.type == FieldType.STRING
        # Must NOT have a nested LIST inner_type
        assert tags.inner_type.inner_type is None

    def test_zod_no_double_array(self):
        schema = self._make_schema()
        zod = ZodGenerator().generate_file(schema)
        assert "z.array(z.string()).optional()" in zod
        assert "z.array(z.array(" not in zod

    def test_rust_no_double_vec(self):
        schema = self._make_schema()
        rust = RustGenerator().generate_file(schema)
        assert "Option<Vec<String>>" in rust
        assert "Vec<Vec<" not in rust

    def test_jsonschema_no_double_items(self):
        schema = self._make_schema()
        js = JsonSchemaGenerator().generate_model(schema)
        # The items should be {"type": "string"}, not {"type": "array", ...}
        assert '"type": "string"' in js
        # Should not have nested array items
        assert '"items": {\n        "type": "array"' not in js

    def test_pydantic_optional_list(self):
        schema = self._make_schema()
        py = PydanticGenerator().generate_file(schema)
        assert "Optional[list[str]]" in py
        # Must not generate Optional[str] (lost the list wrapper)
        assert "tags: Optional[str]" not in py

    def test_optional_set_no_double_nesting(self):
        """Same fix should apply to Optional[set[T]]."""

        @Schema
        class WithSet:
            items: set[int] | None = Field(default=None, description="optional set")

        schema = SchemaParser().parse_schema(WithSet)
        field = schema.get_field("items")
        assert field.type == FieldType.SET
        assert field.optional is True
        assert field.inner_type.type == FieldType.INTEGER

    def test_optional_dict_no_double_nesting(self):
        """Same fix should apply to Optional[dict[str, T]]."""

        @Schema
        class WithDict:
            meta: dict[str, str] | None = Field(
                default=None, description="optional dict"
            )

        schema = SchemaParser().parse_schema(WithDict)
        field = schema.get_field("meta")
        assert field.type == FieldType.DICT
        assert field.optional is True
        assert field.inner_type.type == FieldType.STRING
