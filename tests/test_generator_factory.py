"""Test generator factory functions"""

import tempfile
from pathlib import Path

from schema_gen.core.generator import create_generation_engine


class TestGeneratorFactory:
    """Test generator factory functions"""

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.temp_path = Path(self.temp_dir)

    def test_create_generation_engine_default(self):
        """Test creating engine with default config"""
        engine = create_generation_engine("nonexistent.config.py")

        # Should create with default config
        assert engine is not None
        assert engine.config.input_dir == "schemas/"
        assert engine.config.output_dir == "generated/"
        assert engine.config.targets == ["pydantic"]

    def test_create_generation_engine_with_valid_config(self):
        """Test creating engine with valid config file"""
        # Create a valid config file
        config_file = self.temp_path / "test.config.py"
        config_file.write_text("""
from schema_gen.core.config import Config

config = Config(
    input_dir="test_schemas",
    output_dir="test_output",
    targets=["pydantic", "sqlalchemy"]
)
""")

        engine = create_generation_engine(str(config_file))

        assert engine.config.input_dir == "test_schemas"
        assert engine.config.output_dir == "test_output"
        assert engine.config.targets == ["pydantic", "sqlalchemy"]

    def test_create_generation_engine_invalid_config(self):
        """Test creating engine with invalid config file falls back to default"""
        # Create invalid config file
        config_file = self.temp_path / "invalid.config.py"
        config_file.write_text("invalid python syntax !!!!")

        engine = create_generation_engine(str(config_file))

        # Should fall back to default
        assert engine.config.input_dir == "schemas/"
        assert engine.config.output_dir == "generated/"

    def test_create_generation_engine_no_config_var(self):
        """Test creating engine from file without config variable"""
        # Create config file without 'config' variable
        config_file = self.temp_path / "no_config.config.py"
        config_file.write_text("""
some_other_var = "hello"
""")

        engine = create_generation_engine(str(config_file))

        # Should fall back to default
        assert engine.config.input_dir == "schemas/"
        assert engine.config.output_dir == "generated/"
