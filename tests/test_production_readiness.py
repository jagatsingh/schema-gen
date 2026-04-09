"""Tests for production readiness fixes."""

import tempfile
import warnings
from pathlib import Path

import pytest
from click.testing import CliRunner

from schema_gen import Config, Field, Schema
from schema_gen.cli.main import main
from schema_gen.core.generator import SchemaGenerationEngine, SchemaImportError
from schema_gen.core.schema import SchemaRegistry
from schema_gen.core.usr import FieldType, USRField, USRSchema
from schema_gen.parsers.schema_parser import SchemaParser


class TestValidationInParser:
    """Task 1: Validation is wired up in the parser."""

    def setup_method(self):
        SchemaRegistry._schemas.clear()

    def test_invalid_variant_field_reference_raises(self):
        """Schema with a variant referencing a nonexistent field raises ValueError."""

        @Schema
        class BadVariant:
            name: str = Field()

            class Variants:
                minimal = ["name", "nonexistent_field"]

        parser = SchemaParser()
        with pytest.raises(ValueError, match="nonexistent_field"):
            parser.parse_schema(BadVariant)

    def test_warning_emitted_for_optional_primary_key(self):
        """Schema with an optional primary key emits a warning but does not fail."""

        @Schema
        class OptionalPK:
            id: int | None = Field(primary_key=True)
            name: str = Field()

        parser = SchemaParser()
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = parser.parse_schema(OptionalPK)

        assert result.name == "OptionalPK"
        warning_messages = [str(warning.message) for warning in w]
        assert any(
            "primary_key" in msg and "optional" in msg for msg in warning_messages
        )

    def test_parse_all_schemas_collects_errors(self):
        """parse_all_schemas collects errors from multiple schemas."""

        @Schema
        class Good:
            name: str = Field()

        @Schema
        class Bad:
            name: str = Field()

            class Variants:
                broken = ["name", "ghost_field"]

        parser = SchemaParser()
        with pytest.raises(ValueError, match="ghost_field"):
            parser.parse_all_schemas()


class TestConfigErrorHandling:
    """Task 2: Config errors are no longer silently swallowed."""

    def test_missing_config_returns_defaults(self):
        """No config file returns default config (unchanged behavior)."""
        config = Config.from_file("/nonexistent/path/.schema-gen.config.py")
        assert config.targets == ["pydantic"]

    def test_config_with_syntax_error_raises(self):
        """Config file with syntax error raises SyntaxError."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("config = Config(\n")  # unclosed paren
            f.flush()
            with pytest.raises(SyntaxError, match=f.name):
                Config.from_file(f.name)

    def test_config_without_config_variable_raises(self):
        """Config file without 'config' variable raises ValueError."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("x = 42\n")
            f.flush()
            with pytest.raises(ValueError, match="must define a 'config' variable"):
                Config.from_file(f.name)

    def test_config_with_import_error_raises(self):
        """Config file with ImportError re-raises with file path."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("import nonexistent_module_xyz\n")
            f.flush()
            with pytest.raises(ModuleNotFoundError):
                Config.from_file(f.name)


class TestInvalidTargetsAndVariants:
    """Task 3: Invalid targets and missing variants fail loudly."""

    def setup_method(self):
        SchemaRegistry._schemas.clear()

    def test_invalid_target_name_raises(self):
        """Config with unknown target raises ValueError."""
        config = Config(targets=["nonexistent_target"])
        with pytest.raises(ValueError, match="nonexistent_target"):
            SchemaGenerationEngine(config)

    def test_generate_all_with_unknown_target_raises(self):
        """Passing an unknown target to generate_all raises ValueError."""

        @Schema
        class Dummy:
            name: str = Field()

        config = Config(targets=["pydantic"])
        engine = SchemaGenerationEngine(config)
        engine.load_schemas_from_directory = lambda *a, **kw: None  # skip

        with pytest.raises(ValueError, match="not_real"):
            engine.generate_all(targets=["not_real"])

    def test_missing_variant_raises_key_error(self):
        """get_variant_fields with nonexistent variant raises KeyError."""
        schema = USRSchema(
            name="Test",
            fields=[USRField(name="id", type=FieldType.INTEGER, python_type=int)],
            variants={"existing": ["id"]},
        )
        with pytest.raises(KeyError, match="nonexistent"):
            schema.get_variant_fields("nonexistent")

    def test_existing_variant_still_works(self):
        """get_variant_fields still works for valid variants."""
        field = USRField(name="id", type=FieldType.INTEGER, python_type=int)
        schema = USRSchema(
            name="Test",
            fields=[field],
            variants={"minimal": ["id"]},
        )
        result = schema.get_variant_fields("minimal")
        assert len(result) == 1
        assert result[0].name == "id"


class TestSchemaImportError:
    """Task 4: Schema import errors are raised, not swallowed."""

    def setup_method(self):
        SchemaRegistry._schemas.clear()

    def test_broken_schema_file_raises(self):
        """A schema file with a syntax error raises SchemaImportError."""
        with tempfile.TemporaryDirectory() as tmpdir:
            schema_file = Path(tmpdir) / "broken.py"
            schema_file.write_text("def broken(\n")  # syntax error

            config = Config(input_dir=tmpdir, targets=["pydantic"])
            engine = SchemaGenerationEngine(config)

            with pytest.raises(SchemaImportError, match="broken.py"):
                engine.load_schemas_from_directory()


class TestValidateCommand:
    """Task 5: validate command does real content comparison."""

    def setup_method(self):
        SchemaRegistry._schemas.clear()
        self.runner = CliRunner()

    def test_validate_up_to_date(self):
        """Generate then validate passes."""
        with self.runner.isolated_filesystem():
            # Init project
            self.runner.invoke(main, ["init"])

            # Generate
            result = self.runner.invoke(main, ["generate"])
            assert result.exit_code == 0, result.output

            # Validate
            SchemaRegistry._schemas.clear()
            result = self.runner.invoke(main, ["validate"])
            assert result.exit_code == 0, result.output
            assert "up-to-date" in result.output

    def test_validate_stale_files(self):
        """Modifying a generated file makes validate fail."""
        with self.runner.isolated_filesystem():
            # Init and generate
            self.runner.invoke(main, ["init"])
            result = self.runner.invoke(main, ["generate"])
            assert result.exit_code == 0, result.output

            # Tamper with a generated file
            gen_dir = Path("generated/pydantic")
            py_files = list(gen_dir.glob("*_models.py"))
            assert py_files, "Expected generated model files"
            py_files[0].write_text("# tampered\n")

            # Validate should fail
            SchemaRegistry._schemas.clear()
            result = self.runner.invoke(main, ["validate"])
            assert result.exit_code != 0, result.output
            assert "OUT-OF-DATE" in result.output

    def test_validate_missing_target_dir(self):
        """Validate fails when target directory is missing."""
        with self.runner.isolated_filesystem():
            # Init and generate
            self.runner.invoke(main, ["init"])
            result = self.runner.invoke(main, ["generate"])
            assert result.exit_code == 0, result.output

            # Remove target dir
            import shutil

            shutil.rmtree("generated/pydantic")

            # Validate should fail
            SchemaRegistry._schemas.clear()
            result = self.runner.invoke(main, ["validate"])
            assert result.exit_code != 0, result.output

    def test_validate_no_output_dir(self):
        """Validate fails when output directory doesn't exist."""
        with self.runner.isolated_filesystem():
            self.runner.invoke(main, ["init"])

            # Don't generate - just validate
            result = self.runner.invoke(main, ["validate"])
            assert result.exit_code != 0


class TestPreCommitConfig:
    """Task 6: Pre-commit validate hook is exported for downstream consumers.

    schema-gen is the *tool*; it has no ``schemas/`` directory of its own to
    validate. The schema-gen-validate hook is therefore intentionally NOT
    enabled in the schema-gen repo's own ``.pre-commit-config.yaml``. What we
    do guarantee is that the hook *definition* is present in
    ``.pre-commit-hooks.yaml`` so downstream projects can opt in via
    ``repo: https://github.com/jagatsingh/schema-gen``.
    """

    def test_pre_commit_hooks_yaml_exports_validate_hook(self):
        """The exported hook definition for downstream consumers exists."""
        hooks_path = Path(__file__).parent.parent / ".pre-commit-hooks.yaml"
        content = hooks_path.read_text()
        assert "schema-gen-validate" in content
        # Find the entry and make sure it's an active list item, not a comment.
        for line in content.splitlines():
            stripped = line.strip()
            if "id: schema-gen-validate" in stripped:
                assert not stripped.startswith("#"), (
                    "exported schema-gen-validate hook is commented out"
                )
                return
        raise AssertionError(
            "schema-gen-validate hook id not found in .pre-commit-hooks.yaml"
        )
