# ruff: noqa: UP042, UP045
# These tests deliberately use the legacy ``Optional[T]`` typing form and
# ``class X(str, Enum)`` enum-declaration form because the bug we're pinning
# (issue #15) was reported against exactly those spellings. Rewriting them to
# ``T | None`` / ``StrEnum`` would change the code paths under test.
"""Regression tests for issue #15.

When an enum is referenced via ``Optional[EnumType]``, ``list[EnumType]``,
``dict[str, EnumType]``, or nested combinations like ``Optional[list[EnumType]]``
the generated output (Pydantic, Zod, JSON Schema) must emit the enum with all
its members — not an empty class/schema.

Before the fix, the parser's enum-discovery pass only inspected the outer
``usr_field.python_type`` which for ``Optional[Enum]`` is the wrapper type
rather than the enum class itself, so enum member extraction silently
produced an empty list.
"""

from enum import Enum

from schema_gen import Field, Schema
from schema_gen.core.schema import SchemaRegistry
from schema_gen.generators.jsonschema_generator import JsonSchemaGenerator
from schema_gen.generators.pydantic_generator import PydanticGenerator
from schema_gen.generators.zod_generator import ZodGenerator
from schema_gen.parsers.schema_parser import SchemaParser


class TestOptionalEnumDiscovery:
    """Issue #15: enums referenced through wrapper types must emit members."""

    def setup_method(self):
        SchemaRegistry._schemas.clear()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _assert_pydantic_has_members(code: str) -> None:
        assert "class OptionType(str, Enum):" in code, code
        assert 'CE = "CE"' in code, code
        assert 'PE = "PE"' in code, code

    @staticmethod
    def _assert_zod_has_members(code: str) -> None:
        assert 'z.enum(["CE", "PE"])' in code, code
        assert "z.enum([])" not in code, code

    @staticmethod
    def _assert_jsonschema_has_members(code: str) -> None:
        assert '"CE"' in code and '"PE"' in code, code
        # No empty enum arrays.
        assert '"enum": []' not in code, code

    # ------------------------------------------------------------------
    # Core regression cases
    # ------------------------------------------------------------------

    def test_optional_enum_emits_full_members(self):
        """Optional[Enum] as the only reference must still emit full members."""

        class OptionType(str, Enum):
            CE = "CE"
            PE = "PE"

        @Schema
        class WithOptional:
            option_type: OptionType | None = Field(default=None, description="nullable")

        schema = SchemaParser().parse_schema(WithOptional)

        # USR level: the schema must report the enum with members populated.
        assert len(schema.enums) == 1
        assert schema.enums[0].name == "OptionType"
        assert schema.enums[0].values == [("CE", "CE"), ("PE", "PE")]

        # Generator level: all three targets must emit members.
        self._assert_pydantic_has_members(PydanticGenerator().generate_file(schema))
        self._assert_zod_has_members(ZodGenerator().generate_file(schema))
        self._assert_jsonschema_has_members(JsonSchemaGenerator().generate_file(schema))

    def test_str_enum_json_roundtrip(self):
        """Issue #26: str,Enum mixin must survive generation so json.dumps works."""
        import json

        class OptionType(str, Enum):
            CE = "CE"
            PE = "PE"

        @Schema
        class WithEnum:
            option_type: OptionType = Field(description="required")

        schema = SchemaParser().parse_schema(WithEnum)
        code = PydanticGenerator().generate_file(schema)

        # Execute the generated code to verify it produces a working model.
        ns: dict = {}
        exec(code, ns)  # noqa: S102
        model_cls = ns["WithEnum"]
        instance = model_cls(option_type="CE")
        dumped = instance.model_dump()
        # This is the actual bug from issue #26: json.dumps must not raise
        # TypeError on enum values when the str mixin is preserved.
        json_str = json.dumps(dumped)
        assert '"CE"' in json_str

    def test_required_enum_control_case(self):
        """Required (non-Optional) enum must continue to emit members (no regression)."""

        class OptionType(str, Enum):
            CE = "CE"
            PE = "PE"

        @Schema
        class WithRequired:
            option_type: OptionType = Field(description="required")

        schema = SchemaParser().parse_schema(WithRequired)

        assert len(schema.enums) == 1
        assert schema.enums[0].values == [("CE", "CE"), ("PE", "PE")]

        self._assert_pydantic_has_members(PydanticGenerator().generate_file(schema))
        self._assert_zod_has_members(ZodGenerator().generate_file(schema))
        self._assert_jsonschema_has_members(JsonSchemaGenerator().generate_file(schema))

    def test_list_of_enum(self):
        """list[Enum] should discover the enum via inner_type recursion."""

        class OptionType(str, Enum):
            CE = "CE"
            PE = "PE"

        @Schema
        class WithList:
            allowed: list[OptionType] = Field(default_factory=list)

        schema = SchemaParser().parse_schema(WithList)

        assert len(schema.enums) == 1
        assert schema.enums[0].values == [("CE", "CE"), ("PE", "PE")]

        self._assert_pydantic_has_members(PydanticGenerator().generate_file(schema))
        self._assert_zod_has_members(ZodGenerator().generate_file(schema))
        self._assert_jsonschema_has_members(JsonSchemaGenerator().generate_file(schema))

    def test_optional_list_of_enum(self):
        """Optional[list[Enum]] nests two wrappers; recursion must reach the enum."""

        class OptionType(str, Enum):
            CE = "CE"
            PE = "PE"

        @Schema
        class WithOptionalList:
            allowed: list[OptionType] | None = Field(default=None)

        schema = SchemaParser().parse_schema(WithOptionalList)

        assert len(schema.enums) == 1
        assert schema.enums[0].values == [("CE", "CE"), ("PE", "PE")]

        self._assert_pydantic_has_members(PydanticGenerator().generate_file(schema))
        self._assert_zod_has_members(ZodGenerator().generate_file(schema))
        self._assert_jsonschema_has_members(JsonSchemaGenerator().generate_file(schema))

    def test_required_and_optional_enum_in_same_schema(self):
        """Both Optional and required references in one schema must dedupe cleanly."""

        class OptionType(str, Enum):
            CE = "CE"
            PE = "PE"

        @Schema
        class Mixed:
            primary: OptionType = Field(description="required")
            fallback: OptionType | None = Field(default=None, description="optional")

        schema = SchemaParser().parse_schema(Mixed)

        # Exactly one entry — dedupe by name.
        assert len(schema.enums) == 1
        assert schema.enums[0].values == [("CE", "CE"), ("PE", "PE")]

        self._assert_pydantic_has_members(PydanticGenerator().generate_file(schema))
        self._assert_zod_has_members(ZodGenerator().generate_file(schema))
        self._assert_jsonschema_has_members(JsonSchemaGenerator().generate_file(schema))
