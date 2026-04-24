"""Tests for field-tag constant emission (#82)"""

from pathlib import Path

import pytest

from schema_gen import Field, Schema
from schema_gen.core.schema import SchemaRegistry
from schema_gen.generators.rust_generator import RustGenerator
from schema_gen.generators.zod_generator import ZodGenerator
from schema_gen.parsers.schema_parser import SchemaParser


class TestFieldTagParsing:
    def setup_method(self):
        SchemaRegistry._schemas.clear()

    def test_tags_propagated_to_usr_field(self):
        @Schema
        class MyDTO:
            id: int
            feature_a: str | None = Field(None, tags=["toggleable"])
            feature_b: str | None = Field(None, tags=["toggleable", "deprecated"])

        parser = SchemaParser()
        schema = parser.parse_schema(MyDTO)

        id_field = schema.get_field("id")
        assert id_field.tags == []

        fa_field = schema.get_field("feature_a")
        assert fa_field.tags == ["toggleable"]

        fb_field = schema.get_field("feature_b")
        assert fb_field.tags == ["toggleable", "deprecated"]

    def test_get_tagged_fields(self):
        @Schema
        class MyDTO:
            id: int
            feature_a: str | None = Field(None, tags=["toggleable"])
            feature_b: str | None = Field(None, tags=["toggleable"])
            legacy: str | None = Field(None, tags=["deprecated"])

        parser = SchemaParser()
        schema = parser.parse_schema(MyDTO)
        tag_groups = schema.get_tagged_fields()

        assert tag_groups == {
            "deprecated": ["legacy"],
            "toggleable": ["feature_a", "feature_b"],
        }

    def test_get_tagged_fields_empty(self):
        @Schema
        class Plain:
            id: int
            name: str

        parser = SchemaParser()
        schema = parser.parse_schema(Plain)
        assert schema.get_tagged_fields() == {}

    def test_invalid_tag_name_rejected(self):
        @Schema
        class BadTag:
            x: str = Field(tags=["kebab-case"])

        parser = SchemaParser()
        with pytest.raises(ValueError, match="invalid tag 'kebab-case'"):
            parser.parse_schema(BadTag)

    def test_invalid_tag_numeric_start_rejected(self):
        @Schema
        class BadTag2:
            x: str = Field(tags=["2fa"])

        parser = SchemaParser()
        with pytest.raises(ValueError, match="invalid tag '2fa'"):
            parser.parse_schema(BadTag2)

    def test_valid_tag_with_underscores(self):
        @Schema
        class GoodTag:
            x: str = Field(tags=["my_long_tag_name"])

        parser = SchemaParser()
        schema = parser.parse_schema(GoodTag)
        assert schema.get_field("x").tags == ["my_long_tag_name"]

    def test_multi_tag_field(self):
        @Schema
        class Multi:
            x: str = Field(tags=["toggleable", "premium", "deprecated"])

        parser = SchemaParser()
        schema = parser.parse_schema(Multi)
        tag_groups = schema.get_tagged_fields()

        assert "toggleable" in tag_groups
        assert "premium" in tag_groups
        assert "deprecated" in tag_groups
        for group in tag_groups.values():
            assert group == ["x"]

    def test_duplicate_tags_deduplicated(self):
        @Schema
        class Dupes:
            x: str = Field(tags=["toggleable", "toggleable", "premium", "toggleable"])

        parser = SchemaParser()
        schema = parser.parse_schema(Dupes)
        assert schema.get_field("x").tags == ["toggleable", "premium"]

    def test_non_string_tag_rejected(self):
        @Schema
        class BadType:
            x: str = Field(tags=[123])

        parser = SchemaParser()
        with pytest.raises(ValueError, match="each tag must be a string"):
            parser.parse_schema(BadType)


class TestZodTagEmission:
    def setup_method(self):
        SchemaRegistry._schemas.clear()

    def _generate(self, schema_cls):
        parser = SchemaParser()
        schema = parser.parse_schema(schema_cls)
        gen = ZodGenerator()
        return gen.generate_file(schema)

    def test_single_tag_group(self):
        @Schema
        class MyDTO:
            id: int
            feature_a: str | None = Field(None, tags=["toggleable"])
            feature_b: str | None = Field(None, tags=["toggleable"])

        output = self._generate(MyDTO)

        assert (
            "export const TOGGLEABLE_FIELDS = ['feature_a', 'feature_b'] as const;"
            in output
        )
        assert (
            "export type ToggleableField = (typeof TOGGLEABLE_FIELDS)[number];"
            in output
        )

    def test_multiple_tag_groups(self):
        @Schema
        class MyDTO:
            id: int
            feature_a: str | None = Field(None, tags=["toggleable"])
            legacy: str | None = Field(None, tags=["deprecated"])

        output = self._generate(MyDTO)

        assert "DEPRECATED_FIELDS" in output
        assert "TOGGLEABLE_FIELDS" in output
        assert "DeprecatedField" in output
        assert "ToggleableField" in output

    def test_no_tags_no_constants(self):
        @Schema
        class Plain:
            id: int
            name: str

        output = self._generate(Plain)

        assert "_FIELDS" not in output
        assert "as const" not in output

    def test_snake_case_tag_type_name(self):
        @Schema
        class MyDTO:
            x: str = Field(tags=["my_long_tag"])

        output = self._generate(MyDTO)
        assert "MY_LONG_TAG_FIELDS" in output
        assert "MyLongTagField" in output

    def test_tag_constants_not_in_index(self):
        """Tag constants are per-schema; they are NOT re-exported from the
        barrel index to avoid silent collisions when multiple schemas share
        a tag name."""

        @Schema
        class MyDTO:
            id: int
            feature_a: str | None = Field(None, tags=["toggleable"])

        parser = SchemaParser()
        schema = parser.parse_schema(MyDTO)
        gen = ZodGenerator()
        index = gen.generate_index([schema], Path("/tmp"))

        assert "TOGGLEABLE_FIELDS" not in index
        assert "ToggleableField" not in index


class TestRustTagEmission:
    def setup_method(self):
        SchemaRegistry._schemas.clear()

    def _generate(self, schema_cls):
        parser = SchemaParser()
        schema = parser.parse_schema(schema_cls)
        gen = RustGenerator()
        return gen.generate_file(schema)

    def test_single_tag_group(self):
        @Schema
        class MyDTO:
            id: int
            feature_a: str | None = Field(None, tags=["toggleable"])
            feature_b: str | None = Field(None, tags=["toggleable"])

        output = self._generate(MyDTO)

        assert (
            'pub const TOGGLEABLE_FIELDS: &[&str] = &["feature_a", "feature_b"];'
            in output
        )

    def test_multiple_tag_groups(self):
        @Schema
        class MyDTO:
            id: int
            feature_a: str | None = Field(None, tags=["toggleable"])
            legacy: str | None = Field(None, tags=["deprecated"])

        output = self._generate(MyDTO)

        assert "DEPRECATED_FIELDS" in output
        assert "TOGGLEABLE_FIELDS" in output

    def test_no_tags_no_constants(self):
        @Schema
        class Plain:
            id: int
            name: str

        output = self._generate(Plain)
        assert "_FIELDS: &[&str]" not in output

    def test_wire_name_used_for_reserved_word(self):
        @Schema
        class MyDTO:
            type: str = Field(tags=["special"])

        output = self._generate(MyDTO)

        assert 'pub const SPECIAL_FIELDS: &[&str] = &["type"];' in output
        const_line = [line for line in output.splitlines() if "SPECIAL_FIELDS" in line][
            0
        ]
        assert "r#type" not in const_line

    def test_wire_name_used_for_non_snake_case(self):
        @Schema
        class MyDTO:
            camelCase: str = Field(tags=["flagged"])

        output = self._generate(MyDTO)

        assert 'pub const FLAGGED_FIELDS: &[&str] = &["camelCase"];' in output
