"""Basic CLI tests to increase coverage"""

from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from schema_gen.cli.main import main


class TestCLIBasic:
    """Basic CLI command tests"""

    def setup_method(self):
        self.runner = CliRunner()

    def test_main_help(self):
        """Test main command shows help"""
        result = self.runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "Schema Gen" in result.output

    def test_main_version(self):
        """Test main command shows version"""
        result = self.runner.invoke(main, ["--version"])
        assert result.exit_code == 0

    @patch("schema_gen.cli.main.create_generation_engine")
    def test_generate_command(self, mock_create_engine):
        """Test generate command basic functionality"""
        mock_engine = MagicMock()
        mock_engine.config.output_dir = "generated"
        mock_create_engine.return_value = mock_engine

        result = self.runner.invoke(main, ["generate"])

        assert "🚀 Generating schemas..." in result.output
        mock_create_engine.assert_called_once()
        mock_engine.load_schemas_from_directory.assert_called_once()
        mock_engine.generate_all.assert_called_once()

    @patch("schema_gen.cli.main.create_generation_engine")
    def test_generate_command_failure(self, mock_create_engine):
        """Test generate command handles failure"""
        mock_create_engine.side_effect = Exception("Test error")

        result = self.runner.invoke(main, ["generate"])

        assert result.exit_code == 1
        assert "❌ Generation failed: Test error" in result.output

    def test_init_command(self):
        """Test init command creates basic structure"""
        with self.runner.isolated_filesystem():
            result = self.runner.invoke(main, ["init"])

            assert result.exit_code == 0
            assert "🏗️  Initializing schema-gen project..." in result.output
            assert "✅ Project initialized!" in result.output

    @patch("schema_gen.cli.main.create_generation_engine")
    def test_validate_command_no_output_dir(self, mock_create_engine):
        """Test validate command when output dir doesn't exist"""
        mock_engine = MagicMock()
        mock_engine.config.output_dir = "/nonexistent/path"
        mock_create_engine.return_value = mock_engine

        result = self.runner.invoke(main, ["validate"])

        assert result.exit_code != 0
        assert "Output directory does not exist!" in result.output
