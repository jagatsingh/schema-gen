"""Tests verifying that Config.<target> dicts are wired through to their
respective generators (Fixes #20).

Each test focuses on a single key so failures are easy to diagnose.
"""

from __future__ import annotations

import logging

from schema_gen import Field, Schema
from schema_gen.core.config import Config
from schema_gen.core.schema import SchemaRegistry
from schema_gen.generators.jsonschema_generator import JsonSchemaGenerator
from schema_gen.generators.rust_generator import RustGenerator
from schema_gen.generators.zod_generator import ZodGenerator
from schema_gen.parsers.schema_parser import SchemaParser

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_usr_schema():
    """Return a minimal USRSchema used across all generator tests."""
    SchemaRegistry._schemas.clear()

    @Schema
    class _WiringTestModel:
        """Test schema for config wiring."""

        id: int = Field(description="primary key")
        name: str = Field(description="display name")

    return SchemaParser().parse_schema(_WiringTestModel)


# ---------------------------------------------------------------------------
# RustGenerator — Config.rust
# ---------------------------------------------------------------------------


class TestRustConfigWiring:
    """Config.rust keys flow through to RustGenerator output."""

    def test_json_schema_derive_true_by_default(self):
        gen = RustGenerator()
        schema = _make_usr_schema()
        out = gen.generate_file(schema)
        assert "JsonSchema" in out

    def test_json_schema_derive_false_suppresses_derive(self):
        config = Config(rust={"json_schema_derive": False})
        gen = RustGenerator(config=config)
        schema = _make_usr_schema()
        out = gen.generate_file(schema)
        assert "JsonSchema" not in out

    def test_deny_unknown_fields_false_suppresses_attribute(self):
        config = Config(rust={"deny_unknown_fields": False})
        gen = RustGenerator(config=config)
        schema = _make_usr_schema()
        out = gen.generate_file(schema)
        assert "deny_unknown_fields" not in out

    def test_rename_all_global_applies_to_struct(self):
        config = Config(rust={"rename_all": "camelCase"})
        gen = RustGenerator(config=config)
        schema = _make_usr_schema()
        out = gen.generate_file(schema)
        assert 'rename_all = "camelCase"' in out

    def test_per_schema_json_schema_derive_overrides_global(self):
        """Per-schema SerdeMeta takes precedence over Config.rust global."""
        config = Config(rust={"json_schema_derive": False})
        gen = RustGenerator(config=config)

        SchemaRegistry._schemas.clear()

        from schema_gen.core.usr import FieldType, USRField, USRSchema

        # Build a schema whose SerdeMeta explicitly enables json_schema_derive
        usr = USRSchema(
            name="OverrideModel",
            fields=[USRField(name="x", type=FieldType.INTEGER, python_type=int)],
            custom_code={"rust": {"json_schema_derive": True}},
        )
        out = gen.generate_file(usr)
        assert "JsonSchema" in out

    def test_unknown_key_logs_warning(self, caplog):
        config = Config(rust={"bogus_key": True})
        with caplog.at_level(logging.WARNING, logger="schema_gen"):
            RustGenerator(config=config)
        assert "Unknown Config.rust key" in caplog.text
        assert "bogus_key" in caplog.text

    def test_emit_cargo_toml_false_skips_cargo_toml(self):
        config = Config(rust={"emit_cargo_toml": False})
        gen = RustGenerator(config=config)
        schema = _make_usr_schema()
        extras = gen.get_extra_files([schema], output_dir=None)
        assert "Cargo.toml" not in extras

    def test_crate_name_in_cargo_toml(self):
        config = Config(rust={"crate_name": "my-contracts", "crate_version": "1.2.3"})
        gen = RustGenerator(config=config)
        schema = _make_usr_schema()
        extras = gen.get_extra_files([schema], output_dir=None)
        assert "my-contracts" in extras["Cargo.toml"]
        assert "1.2.3" in extras["Cargo.toml"]


# ---------------------------------------------------------------------------
# ZodGenerator — Config.zod
# ---------------------------------------------------------------------------


class TestZodConfigWiring:
    """Config.zod keys flow through to ZodGenerator output."""

    def test_strict_false_by_default(self):
        gen = ZodGenerator()
        schema = _make_usr_schema()
        out = gen.generate_file(schema)
        assert ".strict()" not in out

    def test_strict_true_appends_strict(self):
        config = Config(zod={"strict": True})
        gen = ZodGenerator(config=config)
        schema = _make_usr_schema()
        out = gen.generate_file(schema)
        assert ".strict()" in out

    def test_unknown_key_logs_warning(self, caplog):
        config = Config(zod={"bogus_key": True})
        with caplog.at_level(logging.WARNING, logger="schema_gen"):
            ZodGenerator(config=config)
        assert "Unknown Config.zod key" in caplog.text
        assert "bogus_key" in caplog.text


# ---------------------------------------------------------------------------
# JsonSchemaGenerator — Config.jsonschema
# ---------------------------------------------------------------------------


class TestJsonSchemaConfigWiring:
    """Config.jsonschema keys flow through to JsonSchemaGenerator output."""

    def test_additional_properties_false(self):
        config = Config(jsonschema={"additional_properties": False})
        gen = JsonSchemaGenerator(config=config)
        schema = _make_usr_schema()
        out = gen.generate_file(schema)
        assert '"additionalProperties": false' in out

    def test_additional_properties_true(self):
        config = Config(jsonschema={"additional_properties": True})
        gen = JsonSchemaGenerator(config=config)
        schema = _make_usr_schema()
        out = gen.generate_model(schema)
        assert '"additionalProperties": true' in out

    def test_no_additional_properties_by_default(self):
        gen = JsonSchemaGenerator()
        schema = _make_usr_schema()
        out = gen.generate_file(schema)
        # No global additional_properties → key should not be injected at schema level
        import json as _json

        data = _json.loads(out)
        assert "additionalProperties" not in data

    def test_schema_uri_override(self):
        config = Config(
            jsonschema={"schema_uri": "https://json-schema.org/draft/2019-09/schema"}
        )
        gen = JsonSchemaGenerator(config=config)
        schema = _make_usr_schema()
        out = gen.generate_model(schema)
        assert "2019-09" in out

    def test_base_url_from_config(self):
        config = Config(jsonschema={"base_url": "https://mycompany.com/schemas"})
        gen = JsonSchemaGenerator(config=config)
        schema = _make_usr_schema()
        out = gen.generate_model(schema)
        assert "mycompany.com" in out

    def test_config_base_url_overrides_constructor_arg(self):
        config = Config(jsonschema={"base_url": "https://config-url.com/schemas"})
        gen = JsonSchemaGenerator(
            base_url="https://constructor-url.com/schemas", config=config
        )
        schema = _make_usr_schema()
        out = gen.generate_model(schema)
        assert "config-url.com" in out
        assert "constructor-url.com" not in out

    def test_unknown_key_logs_warning(self, caplog):
        config = Config(jsonschema={"bogus_key": True})
        with caplog.at_level(logging.WARNING, logger="schema_gen"):
            JsonSchemaGenerator(config=config)
        assert "Unknown Config.jsonschema key" in caplog.text
        assert "bogus_key" in caplog.text
