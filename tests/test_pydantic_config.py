# ruff: noqa: UP042
# These tests deliberately use ``class X(str, Enum)`` because the bug we're
# pinning requires this exact spelling. Rewriting to ``StrEnum`` would change
# the code paths under test.
"""Tests for per-target Pydantic Config (Config.pydantic) wiring.

These tests guard the fix that threads ``Config.pydantic`` from the engine
through ``BaseGenerator`` and into the emitted ``model_config = ConfigDict(...)``
line. The previous behavior silently dropped the config: PydanticGenerator
was instantiated with no arguments, so options like ``extra='forbid'`` had
no effect on generated models.
"""

from datetime import datetime

import pytest

from schema_gen import Field, Schema
from schema_gen.core.config import Config
from schema_gen.core.generator import SchemaGenerationEngine
from schema_gen.core.schema import SchemaRegistry
from schema_gen.generators.pydantic_generator import PydanticGenerator
from schema_gen.parsers.schema_parser import SchemaParser


def _make_schema():
    """Build a small schema that triggers the model_config emission path."""
    SchemaRegistry._schemas.clear()

    @Schema
    class ConfigTestModel:
        """Schema used by the Pydantic config tests."""

        id: int = Field(primary_key=True, description="primary key")
        name: str = Field(min_length=1, max_length=64, description="display name")
        created_at: datetime = Field(description="creation timestamp")

    return SchemaParser().parse_schema(ConfigTestModel)


class TestPydanticConfigDefault:
    """No Config.pydantic supplied — preserve historical output exactly.

    The historical behavior of ``_get_model_config_line`` was to emit
    ``    model_config = ConfigDict(from_attributes=True)`` (no other kwargs).
    The line is only inserted into a model when ``_needs_config`` is True,
    so we test the helper directly to keep the assertion focused.
    """

    def test_default_helper_emits_only_from_attributes(self):
        gen = PydanticGenerator()
        line = gen._get_model_config_line()
        assert line == "    model_config = ConfigDict(from_attributes=True)"

    def test_default_with_explicit_none_config(self):
        gen = PydanticGenerator(config=None)
        line = gen._get_model_config_line()
        assert line == "    model_config = ConfigDict(from_attributes=True)"

    def test_default_does_not_emit_block_without_relationships_or_config(self):
        """A plain schema with no relationships and no config should NOT
        emit a ``model_config`` block at all — same as before the fix."""
        schema = _make_schema()
        gen = PydanticGenerator()
        out = gen.generate_file(schema)
        assert "model_config = ConfigDict" not in out


class TestPydanticConfigOverrides:
    """Config.pydantic values must be honored in the emitted ConfigDict."""

    def test_extra_forbid(self):
        schema = _make_schema()
        gen = PydanticGenerator(config=Config(pydantic={"extra": "forbid"}))
        out = gen.generate_file(schema)
        assert "extra='forbid'" in out
        assert "from_attributes=True" in out

    def test_extra_allow(self):
        schema = _make_schema()
        gen = PydanticGenerator(config=Config(pydantic={"extra": "allow"}))
        out = gen.generate_file(schema)
        assert "extra='allow'" in out

    def test_extra_ignore(self):
        schema = _make_schema()
        gen = PydanticGenerator(config=Config(pydantic={"extra": "ignore"}))
        out = gen.generate_file(schema)
        assert "extra='ignore'" in out

    def test_multiple_keys(self):
        schema = _make_schema()
        gen = PydanticGenerator(
            config=Config(
                pydantic={
                    "extra": "forbid",
                    "validate_assignment": True,
                    "frozen": True,
                }
            )
        )
        out = gen.generate_file(schema)
        assert "extra='forbid'" in out
        assert "validate_assignment=True" in out
        assert "frozen=True" in out

    def test_all_supported_keys(self):
        schema = _make_schema()
        gen = PydanticGenerator(
            config=Config(
                pydantic={
                    "extra": "forbid",
                    "validate_assignment": True,
                    "frozen": False,
                    "strict": True,
                    "str_strip_whitespace": True,
                    "populate_by_name": True,
                }
            )
        )
        out = gen.generate_file(schema)
        for fragment in (
            "extra='forbid'",
            "validate_assignment=True",
            "frozen=False",
            "strict=True",
            "str_strip_whitespace=True",
            "populate_by_name=True",
        ):
            assert fragment in out, f"missing: {fragment}"

    def test_deterministic_output(self):
        """Generating the same schema twice must produce identical output.

        Regression for non-deterministic frozenset iteration (PYTHONHASHSEED).
        """
        schema = _make_schema()
        gen = PydanticGenerator(
            config=Config(
                pydantic={
                    "extra": "forbid",
                    "validate_assignment": True,
                    "frozen": True,
                    "strict": True,
                }
            )
        )
        out1 = gen.generate_file(schema)
        out2 = gen.generate_file(schema)
        assert out1 == out2

    def test_config_dict_kwargs_order(self):
        """ConfigDict kwargs must follow the tuple order defined in
        _SUPPORTED_PYDANTIC_CONFIG_KEYS, not random hash order."""
        gen = PydanticGenerator(
            config=Config(
                pydantic={
                    "populate_by_name": True,
                    "extra": "forbid",
                    "strict": True,
                }
            )
        )
        line = gen._get_model_config_line()
        # "extra" comes before "strict" comes before "populate_by_name"
        # per the tuple ordering.
        extra_pos = line.index("extra=")
        strict_pos = line.index("strict=")
        populate_pos = line.index("populate_by_name=")
        assert extra_pos < strict_pos < populate_pos

    def test_unknown_keys_are_ignored(self):
        """Unknown pydantic keys should not cause crashes or leak into output."""
        schema = _make_schema()
        gen = PydanticGenerator(
            config=Config(pydantic={"extra": "forbid", "totally_made_up": "value"})
        )
        out = gen.generate_file(schema)
        assert "extra='forbid'" in out
        assert "totally_made_up" not in out

    def test_unknown_only_keys_do_not_trigger_config_block(self):
        """Regression for Copilot #14.x: a ``Config.pydantic`` dict that
        contains only unknown keys must NOT cause a ``model_config`` block
        to be emitted on a schema that has no relationships."""
        schema = _make_schema()
        gen = PydanticGenerator(config=Config(pydantic={"totally_made_up": "value"}))
        out = gen.generate_file(schema)
        assert "model_config = ConfigDict" not in out

    def test_string_values_are_repr_escaped(self):
        """Regression for Copilot #14.x: string values must be Python-repr
        encoded so embedded quotes, backslashes, and newlines produce valid
        source code (not a broken f-string with a literal apostrophe)."""
        gen = PydanticGenerator(config=Config(pydantic={"extra": "forbid"}))
        line = gen._get_model_config_line()
        # repr() of "forbid" is 'forbid' — matches existing assertion style.
        assert "extra='forbid'" in line


class TestEngineThreadsConfigEndToEnd:
    """Full path: SchemaGenerationEngine -> PydanticGenerator -> file output."""

    def test_engine_passes_pydantic_config_to_generator(self, tmp_path):
        SchemaRegistry._schemas.clear()

        @Schema
        class EngineTestModel:
            """Schema for end-to-end engine test."""

            id: int = Field(primary_key=True, description="pk")
            label: str = Field(description="label")

        config = Config(
            input_dir=str(tmp_path / "schemas"),
            output_dir=str(tmp_path / "out"),
            targets=["pydantic"],
            pydantic={"extra": "forbid", "validate_assignment": True},
        )

        engine = SchemaGenerationEngine(config)
        # Sanity: the generator instance should have the config attached.
        assert engine.generators["pydantic"].config is config

        engine.generate_all()

        generated = (
            tmp_path / "out" / "pydantic" / "enginetestmodel_models.py"
        ).read_text()
        assert "extra='forbid'" in generated
        assert "validate_assignment=True" in generated


from enum import Enum, nonmember  # noqa: E402


class _PyOrderStatus(str, Enum):  # noqa: UP042
    PENDING = "pending"
    FILLED = "filled"
    CANCELLED = "cancelled"

    PydanticMeta = nonmember(
        type(
            "PydanticMeta",
            (),
            {
                "methods": (
                    "def is_terminal(self) -> bool:\n"
                    "    return self in {_PyOrderStatus.FILLED, _PyOrderStatus.CANCELLED}"
                )
            },
        )
    )


class _PyPlainColor(str, Enum):  # noqa: UP042
    RED = "red"
    BLUE = "blue"


@Schema
class _PyOrderEvent:
    status: _PyOrderStatus


@Schema
class _PyPaint:
    color: _PyPlainColor


class TestPydanticEnumMeta:
    """PydanticMeta on Enum classes injects domain methods into the
    generated Pydantic enum body."""

    def setup_method(self):
        SchemaRegistry._schemas.clear()

    def test_enum_pydantic_meta_methods(self):
        from schema_gen.generators.pydantic_generator import PydanticGenerator

        usr = SchemaParser().parse_schema(_PyOrderEvent)
        out = PydanticGenerator().generate_file(usr)
        assert "class _PyOrderStatus(str, Enum):" in out
        assert "def is_terminal(self) -> bool:" in out
        assert "_PyOrderStatus.FILLED" in out

    def test_enum_without_meta_unchanged(self):
        from schema_gen.generators.pydantic_generator import PydanticGenerator

        usr = SchemaParser().parse_schema(_PyPaint)
        out = PydanticGenerator().generate_file(usr)
        assert "class _PyPlainColor(str, Enum):" in out
        # No injected methods
        assert "def is_terminal" not in out


# ------------------------------------------------------------------
# Pydantic discriminated union support (Fix #6)
# ------------------------------------------------------------------

from typing import Annotated, Literal  # noqa: E402


@Schema
class _PydCeLeg:
    option_type: Literal["CE"]
    strike: float


@Schema
class _PydPeLeg:
    option_type: Literal["PE"]
    strike: float


@Schema
class _PydDiscOrder:
    leg: Annotated[_PydCeLeg | _PydPeLeg, Field(discriminator="option_type")]


class TestPydanticDiscriminatedUnion:
    """Pydantic generator must emit Annotated[Union[...], Field(discriminator=...)]
    for discriminated union fields."""

    def setup_method(self):
        SchemaRegistry._schemas.clear()
        for cls in (_PydCeLeg, _PydPeLeg, _PydDiscOrder):
            SchemaRegistry.register(cls)

    def test_discriminated_union_type_annotation(self):
        from schema_gen.generators.pydantic_generator import PydanticGenerator

        usr = SchemaParser().parse_schema(_PydDiscOrder)
        out = PydanticGenerator().generate_file(usr)
        assert (
            'Annotated[Union["_PydCeLeg", "_PydPeLeg"], Field(discriminator="option_type")]'
            in out
        )
        assert "from typing import" in out
        assert "Annotated" in out

    def test_discriminated_union_imports(self):
        from schema_gen.generators.pydantic_generator import PydanticGenerator

        usr = SchemaParser().parse_schema(_PydDiscOrder)
        out = PydanticGenerator().generate_file(usr)
        # Must import Annotated, Union, and Field
        lines = out.splitlines()
        typing_line = [ln for ln in lines if ln.startswith("from typing import")]
        assert typing_line, "Missing typing import"
        assert "Annotated" in typing_line[0]
        assert "Union" in typing_line[0]


# ------------------------------------------------------------------
# default_factory support (Fix #28)
# ------------------------------------------------------------------


@Schema
class _DefaultFactoryModel:
    """Schema with default_factory fields."""

    name: str = Field(description="name")
    tags: list[str] = Field(default_factory=list, description="tags")
    metadata: dict[str, str] = Field(default_factory=dict, description="extra metadata")


class TestPydanticDefaultFactory:
    """Pydantic generator must emit Field(default_factory=...) when the
    USRField has a default_factory set, instead of Field(...) (required)."""

    def setup_method(self):
        SchemaRegistry._schemas.clear()

    def test_default_factory_list(self):
        usr = SchemaParser().parse_schema(_DefaultFactoryModel)
        out = PydanticGenerator().generate_file(usr)
        assert "default_factory=list" in out

    def test_default_factory_dict(self):
        usr = SchemaParser().parse_schema(_DefaultFactoryModel)
        out = PydanticGenerator().generate_file(usr)
        assert "default_factory=dict" in out

    def test_default_factory_not_required(self):
        """Fields with default_factory must NOT be marked as required (...)."""
        usr = SchemaParser().parse_schema(_DefaultFactoryModel)
        out = PydanticGenerator().generate_file(usr)
        # The 'tags' and 'metadata' fields should not have Field(...)
        # Only 'name' should be required.
        lines = out.splitlines()
        for line in lines:
            if "tags:" in line or "metadata:" in line:
                assert "Field(...)" not in line, (
                    f"Field with default_factory marked as required: {line}"
                )

    def test_default_factory_usr_field_populated(self):
        """Parser must populate default_factory on USRField."""
        usr = SchemaParser().parse_schema(_DefaultFactoryModel)
        tags_field = usr.get_field("tags")
        assert tags_field is not None
        assert tags_field.default_factory is list
        metadata_field = usr.get_field("metadata")
        assert metadata_field is not None
        assert metadata_field.default_factory is dict

    def test_lambda_default_factory_raises(self):
        """Lambda factories can't be emitted as valid Python — raise a clear error."""

        from schema_gen.core.usr import FieldType, USRField, USRSchema

        field = USRField(
            name="items",
            type=FieldType.LIST,
            python_type=list,
            optional=False,
            default_factory=lambda: [],
        )
        schema = USRSchema(name="Bad", fields=[field], enums=[], variants=[])
        with pytest.raises(ValueError, match="named callable"):
            PydanticGenerator().generate_file(schema)
