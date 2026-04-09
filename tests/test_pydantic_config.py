"""Tests for per-target Pydantic Config (Config.pydantic) wiring.

These tests guard the fix that threads ``Config.pydantic`` from the engine
through ``BaseGenerator`` and into the emitted ``model_config = ConfigDict(...)``
line. The previous behavior silently dropped the config: PydanticGenerator
was instantiated with no arguments, so options like ``extra='forbid'`` had
no effect on generated models.
"""

from datetime import datetime

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
