"""Tests for the contract registry API."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from schema_gen.cli.main import main
from schema_gen.core.config import Config
from schema_gen.core.usr import FieldType, USREnum, USRField, USRSchema
from schema_gen.registry.index import build_registry_index

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_field(
    name: str,
    ftype: FieldType = FieldType.STRING,
    optional: bool = False,
    description: str | None = None,
    enum_name: str | None = None,
    enum_values: list | None = None,
    nested_schema: str | None = None,
    inner_type: USRField | None = None,
) -> USRField:
    return USRField(
        name=name,
        type=ftype,
        python_type=str,
        optional=optional,
        description=description,
        enum_name=enum_name,
        enum_values=enum_values or [],
        nested_schema=nested_schema,
        inner_type=inner_type,
    )


def _sample_schemas() -> list[USRSchema]:
    """Build a small set of USRSchema objects for testing."""
    action_enum = USREnum(
        name="Action",
        values=[("buy", "buy"), ("sell", "sell")],
    )

    context_schema = USRSchema(
        name="ExecutionContext",
        fields=[
            _make_field("trace_id", FieldType.STRING, description="Trace ID"),
        ],
        description="Execution context metadata",
    )

    order_schema = USRSchema(
        name="OrderRequest",
        fields=[
            _make_field(
                "request_id", FieldType.STRING, description="Unique request ID"
            ),
            _make_field(
                "action",
                FieldType.ENUM,
                enum_name="Action",
                enum_values=["buy", "sell"],
                description="Trade action",
            ),
            _make_field(
                "context",
                FieldType.NESTED_SCHEMA,
                nested_schema="ExecutionContext",
                description="Execution context",
            ),
            _make_field(
                "tags",
                FieldType.LIST,
                inner_type=_make_field("tags_item", FieldType.STRING),
                description="Tags",
            ),
            _make_field("quantity", FieldType.INTEGER, description="Quantity"),
        ],
        description="An order request",
        enums=[action_enum],
        variants={
            "create_request": ["request_id", "action", "quantity"],
            "update_request": ["request_id", "quantity"],
        },
    )

    return [order_schema, context_schema]


@pytest.fixture
def sample_schemas():
    return _sample_schemas()


@pytest.fixture
def default_config():
    return Config()


@pytest.fixture
def runner():
    return CliRunner()


# ---------------------------------------------------------------------------
# Phase 1: Index building tests
# ---------------------------------------------------------------------------


class TestBuildRegistryIndex:
    def test_basic_structure(self, sample_schemas, default_config):
        index = build_registry_index(sample_schemas, default_config)

        assert index["version"] == "1.0.0"
        assert "generated_at" in index
        assert "schema_gen_version" in index
        assert "types" in index
        assert "enums" in index

    def test_types_present(self, sample_schemas, default_config):
        index = build_registry_index(sample_schemas, default_config)

        assert "OrderRequest" in index["types"]
        assert "ExecutionContext" in index["types"]

    def test_type_fields(self, sample_schemas, default_config):
        index = build_registry_index(sample_schemas, default_config)
        order = index["types"]["OrderRequest"]

        assert "request_id" in order["fields"]
        assert order["fields"]["request_id"]["type"] == "string"
        assert order["fields"]["request_id"]["required"] is True
        assert order["fields"]["request_id"]["description"] == "Unique request ID"

    def test_enum_field_type(self, sample_schemas, default_config):
        index = build_registry_index(sample_schemas, default_config)
        order = index["types"]["OrderRequest"]

        assert order["fields"]["action"]["type"] == "Action"

    def test_nested_type_field(self, sample_schemas, default_config):
        index = build_registry_index(sample_schemas, default_config)
        order = index["types"]["OrderRequest"]

        assert order["fields"]["context"]["type"] == "ExecutionContext"

    def test_list_field_type(self, sample_schemas, default_config):
        index = build_registry_index(sample_schemas, default_config)
        order = index["types"]["OrderRequest"]

        assert order["fields"]["tags"]["type"] == "list[string]"

    def test_enums_referenced(self, sample_schemas, default_config):
        index = build_registry_index(sample_schemas, default_config)
        order = index["types"]["OrderRequest"]

        assert "Action" in order["enums_referenced"]

    def test_nested_types_referenced(self, sample_schemas, default_config):
        index = build_registry_index(sample_schemas, default_config)
        order = index["types"]["OrderRequest"]

        assert "ExecutionContext" in order["nested_types"]

    def test_variants(self, sample_schemas, default_config):
        index = build_registry_index(sample_schemas, default_config)
        order = index["types"]["OrderRequest"]

        assert "OrderRequestCreateRequest" in order["variants"]
        assert "OrderRequestUpdateRequest" in order["variants"]

    def test_enum_index(self, sample_schemas, default_config):
        index = build_registry_index(sample_schemas, default_config)

        assert "Action" in index["enums"]
        action = index["enums"]["Action"]
        assert action["values"] == [
            {"name": "buy", "value": "buy"},
            {"name": "sell", "value": "sell"},
        ]

    def test_enum_used_by(self, sample_schemas, default_config):
        index = build_registry_index(sample_schemas, default_config)

        assert "OrderRequest" in index["enums"]["Action"]["used_by"]

    def test_domain_detection_flat(self, sample_schemas, default_config):
        """Schemas without source_file metadata get domain=None."""
        index = build_registry_index(sample_schemas, default_config)

        assert index["types"]["OrderRequest"]["domain"] is None

    def test_domain_detection_subdirectory(self, default_config):
        """Schemas with source_file in a subdirectory get a domain."""
        schema = USRSchema(
            name="Trade",
            fields=[_make_field("id", FieldType.STRING)],
            metadata={"source_file": "schemas/execution/trade.py"},
        )
        config = Config(input_dir="schemas/")
        index = build_registry_index([schema], config)

        assert index["types"]["Trade"]["domain"] == "execution"

    def test_determinism(self, sample_schemas, default_config):
        """Same input produces identical output (except generated_at)."""
        index1 = build_registry_index(sample_schemas, default_config)
        index2 = build_registry_index(sample_schemas, default_config)

        # Remove timestamp for comparison
        index1.pop("generated_at")
        index2.pop("generated_at")

        assert index1 == index2

    def test_determinism_json_serialization(self, sample_schemas, default_config):
        """JSON serialization is deterministic."""
        index1 = build_registry_index(sample_schemas, default_config)
        index2 = build_registry_index(sample_schemas, default_config)

        index1.pop("generated_at")
        index2.pop("generated_at")

        json1 = json.dumps(index1, indent=2, sort_keys=True)
        json2 = json.dumps(index2, indent=2, sort_keys=True)

        assert json1 == json2

    def test_empty_schemas(self, default_config):
        index = build_registry_index([], default_config)

        assert index["types"] == {}
        assert index["enums"] == {}

    def test_optional_field(self, default_config):
        schema = USRSchema(
            name="Foo",
            fields=[_make_field("bar", FieldType.STRING, optional=True)],
        )
        index = build_registry_index([schema], default_config)

        assert index["types"]["Foo"]["fields"]["bar"]["required"] is False

    def test_kind_is_struct(self, sample_schemas, default_config):
        index = build_registry_index(sample_schemas, default_config)

        for tentry in index["types"].values():
            assert tentry["kind"] == "struct"


# ---------------------------------------------------------------------------
# Phase 2 & 3: CLI tests
# ---------------------------------------------------------------------------


def _write_registry_json(tmpdir: Path, index: dict) -> Path:
    """Write registry.json into a tmp output dir and return the path."""
    registry_path = tmpdir / "registry.json"
    registry_path.write_text(json.dumps(index, indent=2))
    return registry_path


def _write_config_file(tmpdir: Path, output_dir: str) -> Path:
    """Write a minimal config file and return its path."""
    config_path = tmpdir / ".schema-gen.config.py"
    config_path.write_text(
        f"""from schema_gen import Config
config = Config(
    input_dir="schemas/",
    output_dir="{output_dir}",
    targets=["pydantic"],
)
"""
    )
    return config_path


class TestCLIList:
    def test_list_types(self, runner, sample_schemas, default_config):
        index = build_registry_index(sample_schemas, default_config)

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "generated"
            output_dir.mkdir()
            _write_registry_json(output_dir, index)
            config_path = _write_config_file(Path(tmpdir), str(output_dir))

            result = runner.invoke(main, ["registry", "list", "-c", str(config_path)])

            assert result.exit_code == 0
            assert "OrderRequest" in result.output
            assert "ExecutionContext" in result.output

    def test_list_empty_registry(self, runner):
        index = {
            "version": "1.0.0",
            "generated_at": "2026-01-01T00:00:00Z",
            "schema_gen_version": "0.2.0",
            "types": {},
            "enums": {},
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "generated"
            output_dir.mkdir()
            _write_registry_json(output_dir, index)
            config_path = _write_config_file(Path(tmpdir), str(output_dir))

            result = runner.invoke(main, ["registry", "list", "-c", str(config_path)])

            assert result.exit_code == 0
            assert "No types found" in result.output


class TestCLIShow:
    def test_show_type(self, runner, sample_schemas, default_config):
        index = build_registry_index(sample_schemas, default_config)

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "generated"
            output_dir.mkdir()
            _write_registry_json(output_dir, index)
            config_path = _write_config_file(Path(tmpdir), str(output_dir))

            result = runner.invoke(
                main,
                ["registry", "show", "OrderRequest", "-c", str(config_path)],
            )

            assert result.exit_code == 0
            assert "OrderRequest" in result.output
            assert "request_id" in result.output
            assert "action" in result.output
            assert "Enums referenced: Action" in result.output
            assert "Nested types: ExecutionContext" in result.output

    def test_show_missing_type(self, runner, sample_schemas, default_config):
        index = build_registry_index(sample_schemas, default_config)

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "generated"
            output_dir.mkdir()
            _write_registry_json(output_dir, index)
            config_path = _write_config_file(Path(tmpdir), str(output_dir))

            result = runner.invoke(
                main,
                ["registry", "show", "NonExistent", "-c", str(config_path)],
            )

            assert result.exit_code != 0
            assert "not found" in result.output

    def test_show_enum(self, runner, sample_schemas, default_config):
        index = build_registry_index(sample_schemas, default_config)

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "generated"
            output_dir.mkdir()
            _write_registry_json(output_dir, index)
            config_path = _write_config_file(Path(tmpdir), str(output_dir))

            result = runner.invoke(
                main,
                ["registry", "show", "Action", "-c", str(config_path)],
            )

            assert result.exit_code == 0
            assert "Enum: Action" in result.output
            assert "buy" in result.output
            assert "sell" in result.output


class TestCLIRefs:
    def test_refs_enum(self, runner, sample_schemas, default_config):
        index = build_registry_index(sample_schemas, default_config)

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "generated"
            output_dir.mkdir()
            _write_registry_json(output_dir, index)
            config_path = _write_config_file(Path(tmpdir), str(output_dir))

            result = runner.invoke(
                main,
                ["registry", "refs", "Action", "-c", str(config_path)],
            )

            assert result.exit_code == 0
            assert "OrderRequest" in result.output

    def test_refs_nested_type(self, runner, sample_schemas, default_config):
        index = build_registry_index(sample_schemas, default_config)

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "generated"
            output_dir.mkdir()
            _write_registry_json(output_dir, index)
            config_path = _write_config_file(Path(tmpdir), str(output_dir))

            result = runner.invoke(
                main,
                ["registry", "refs", "ExecutionContext", "-c", str(config_path)],
            )

            assert result.exit_code == 0
            assert "OrderRequest" in result.output

    def test_refs_no_references(self, runner, sample_schemas, default_config):
        index = build_registry_index(sample_schemas, default_config)

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "generated"
            output_dir.mkdir()
            _write_registry_json(output_dir, index)
            config_path = _write_config_file(Path(tmpdir), str(output_dir))

            result = runner.invoke(
                main,
                ["registry", "refs", "OrderRequest", "-c", str(config_path)],
            )

            assert result.exit_code == 0
            assert "No types reference" in result.output


class TestCLISearch:
    def test_search_type_name(self, runner, sample_schemas, default_config):
        index = build_registry_index(sample_schemas, default_config)

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "generated"
            output_dir.mkdir()
            _write_registry_json(output_dir, index)
            config_path = _write_config_file(Path(tmpdir), str(output_dir))

            result = runner.invoke(
                main,
                ["registry", "search", "Order", "-c", str(config_path)],
            )

            assert result.exit_code == 0
            assert "OrderRequest" in result.output

    def test_search_field_name(self, runner, sample_schemas, default_config):
        index = build_registry_index(sample_schemas, default_config)

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "generated"
            output_dir.mkdir()
            _write_registry_json(output_dir, index)
            config_path = _write_config_file(Path(tmpdir), str(output_dir))

            result = runner.invoke(
                main,
                ["registry", "search", "request_id", "-c", str(config_path)],
            )

            assert result.exit_code == 0
            assert "request_id" in result.output

    def test_search_no_results(self, runner, sample_schemas, default_config):
        index = build_registry_index(sample_schemas, default_config)

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "generated"
            output_dir.mkdir()
            _write_registry_json(output_dir, index)
            config_path = _write_config_file(Path(tmpdir), str(output_dir))

            result = runner.invoke(
                main,
                ["registry", "search", "zzzzzzz", "-c", str(config_path)],
            )

            assert result.exit_code == 0
            assert "No results" in result.output

    def test_search_enum(self, runner, sample_schemas, default_config):
        index = build_registry_index(sample_schemas, default_config)

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "generated"
            output_dir.mkdir()
            _write_registry_json(output_dir, index)
            config_path = _write_config_file(Path(tmpdir), str(output_dir))

            result = runner.invoke(
                main,
                ["registry", "search", "Action", "-c", str(config_path)],
            )

            assert result.exit_code == 0
            assert "[enum] Action" in result.output


class TestCLIValidate:
    def test_validate_valid_json(self, runner):
        """Validate a JSON file against a JSON Schema (mocked schema)."""
        json_schema = {
            "$defs": {
                "TestType": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "age": {"type": "integer"},
                    },
                    "required": ["name"],
                }
            }
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "generated"
            jsonschema_dir = output_dir / "jsonschema"
            jsonschema_dir.mkdir(parents=True)

            # Write the JSON schema file
            schema_file = jsonschema_dir / "testtype.json"
            schema_file.write_text(json.dumps(json_schema))

            # Write the data file to validate
            data_file = Path(tmpdir) / "data.json"
            data_file.write_text(json.dumps({"name": "Alice", "age": 30}))

            # Write config
            config_path = _write_config_file(Path(tmpdir), str(output_dir))

            result = runner.invoke(
                main,
                [
                    "registry",
                    "validate",
                    str(data_file),
                    "--type",
                    "TestType",
                    "-c",
                    str(config_path),
                ],
            )

            assert result.exit_code == 0
            assert "Validation passed" in result.output

    def test_validate_invalid_json(self, runner):
        """Validate a JSON file that does not conform to the schema."""
        json_schema = {
            "$defs": {
                "TestType": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                    },
                    "required": ["name"],
                }
            }
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "generated"
            jsonschema_dir = output_dir / "jsonschema"
            jsonschema_dir.mkdir(parents=True)

            schema_file = jsonschema_dir / "testtype.json"
            schema_file.write_text(json.dumps(json_schema))

            # Data missing required field
            data_file = Path(tmpdir) / "data.json"
            data_file.write_text(json.dumps({"age": 30}))

            config_path = _write_config_file(Path(tmpdir), str(output_dir))

            result = runner.invoke(
                main,
                [
                    "registry",
                    "validate",
                    str(data_file),
                    "--type",
                    "TestType",
                    "-c",
                    str(config_path),
                ],
            )

            assert result.exit_code != 0
            assert "Validation failed" in result.output

    def test_validate_missing_schema(self, runner):
        """Error when JSON Schema file does not exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "generated"
            output_dir.mkdir()

            data_file = Path(tmpdir) / "data.json"
            data_file.write_text(json.dumps({"name": "Alice"}))

            config_path = _write_config_file(Path(tmpdir), str(output_dir))

            result = runner.invoke(
                main,
                [
                    "registry",
                    "validate",
                    str(data_file),
                    "--type",
                    "Missing",
                    "-c",
                    str(config_path),
                ],
            )

            assert result.exit_code != 0
            assert "not found" in result.output


class TestCLICompat:
    def test_compat_no_changes(self, runner):
        """No compatibility issues when schemas are identical."""
        json_schema = {
            "$defs": {
                "Foo": {
                    "type": "object",
                    "properties": {"name": {"type": "string"}},
                    "required": ["name"],
                }
            }
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "generated"
            jsonschema_dir = output_dir / "jsonschema"
            jsonschema_dir.mkdir(parents=True)

            schema_file = jsonschema_dir / "foo.json"
            schema_file.write_text(json.dumps(json_schema))

            config_path = _write_config_file(Path(tmpdir), str(output_dir))

            # Mock baseline loading to return same schema
            with (
                patch(
                    "schema_gen.cli.main.load_baseline",
                    return_value={"foo.json": json_schema},
                ),
                patch(
                    "schema_gen.cli.main.load_current",
                    return_value={"foo.json": json_schema},
                ),
            ):
                result = runner.invoke(
                    main,
                    [
                        "registry",
                        "compat",
                        "--type",
                        "Foo",
                        "--against",
                        ".git#branch=main",
                        "-c",
                        str(config_path),
                    ],
                )

                assert result.exit_code == 0
                assert "No compatibility issues" in result.output

    def test_compat_breaking_change(self, runner):
        """Detect breaking changes when a field is deleted."""
        old_schema = {
            "$defs": {
                "Foo": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "email": {"type": "string"},
                    },
                    "required": ["name", "email"],
                }
            }
        }
        new_schema = {
            "$defs": {
                "Foo": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                    },
                    "required": ["name"],
                }
            }
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "generated"
            jsonschema_dir = output_dir / "jsonschema"
            jsonschema_dir.mkdir(parents=True)

            schema_file = jsonschema_dir / "foo.json"
            schema_file.write_text(json.dumps(new_schema))

            config_path = _write_config_file(Path(tmpdir), str(output_dir))

            with (
                patch(
                    "schema_gen.cli.main.load_baseline",
                    return_value={"foo.json": old_schema},
                ),
                patch(
                    "schema_gen.cli.main.load_current",
                    return_value={"foo.json": new_schema},
                ),
            ):
                result = runner.invoke(
                    main,
                    [
                        "registry",
                        "compat",
                        "--type",
                        "Foo",
                        "--against",
                        ".git#branch=main",
                        "-c",
                        str(config_path),
                    ],
                )

                assert result.exit_code != 0
                assert "Compatibility issues" in result.output
