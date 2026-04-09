"""Core generation engine for schema_gen"""

import importlib.util
import inspect
import sys
from pathlib import Path

from ..generators.registry import GENERATOR_REGISTRY
from ..parsers.schema_parser import SchemaParser
from .config import Config


class SchemaImportError(Exception):
    """Raised when a schema file cannot be imported"""


class SchemaGenerationEngine:
    """Main engine that orchestrates schema generation"""

    def __init__(self, config: Config):
        self.config = config
        self.parser = SchemaParser()

        # Initialize generators based on config targets using the registry
        self.generators = {}
        invalid_targets = [t for t in config.targets if t not in GENERATOR_REGISTRY]
        if invalid_targets:
            available = sorted(GENERATOR_REGISTRY.keys())
            raise ValueError(
                f"Unknown target(s): {invalid_targets}. Available targets: {available}"
            )
        for target in config.targets:
            generator_cls = GENERATOR_REGISTRY[target]
            # Pass config only to generators whose __init__ accepts it. Most
            # generators currently take no constructor args; PydanticGenerator
            # is the first to honor per-target config (Config.pydantic).
            try:
                init_params = inspect.signature(generator_cls.__init__).parameters
            except (TypeError, ValueError):
                init_params = {}
            if "config" in init_params:
                instance = generator_cls(config=self.config)
            else:
                instance = generator_cls()
                # Still attach config so generators that read self.config
                # (set by BaseGenerator) work even when their own __init__
                # doesn't forward it.
                instance.config = self.config
            self.generators[target] = instance

    def load_schemas_from_directory(self, input_dir: str = None):
        """Load all schema files from input directory

        Args:
            input_dir: Directory to scan for schema files. Uses config default if None.
        """
        schema_dir = Path(input_dir or self.config.input_dir)

        if not schema_dir.exists():
            raise FileNotFoundError(f"Schema directory not found: {schema_dir}")

        # Find all Python files in the schema directory
        schema_files = list(schema_dir.rglob("*.py"))

        if not schema_files:
            raise ValueError(f"No Python files found in {schema_dir}")

        # Import each schema file to trigger @Schema registration
        for schema_file in schema_files:
            if schema_file.name.startswith("__"):
                continue  # Skip __init__.py, etc.

            try:
                self._import_schema_file(schema_file)
            except Exception as e:
                raise SchemaImportError(
                    f"Failed to import schema file {schema_file}: {e}"
                ) from e

    def generate_all(self, targets: list[str] = None, output_dir: str = None):
        """Generate all schemas for specified targets

        Args:
            targets: List of target generators to run. Uses config default if None.
            output_dir: Output directory. Uses config default if None.
        """
        targets = targets or self.config.targets
        output_dir = Path(output_dir or self.config.output_dir)

        # Parse all registered schemas
        schemas = self.parser.parse_all_schemas()

        if not schemas:
            raise ValueError(
                "No schemas found. Make sure your schema files are imported and use @Schema decorator."
            )

        print(f"Found {len(schemas)} schema(s): {', '.join(s.name for s in schemas)}")

        # Generate for each target
        for target in targets:
            if target not in self.generators:
                raise ValueError(
                    f"Generator for '{target}' not found. "
                    f"Available: {sorted(self.generators.keys())}"
                )

            self._generate_target(target, schemas, output_dir)

    def _import_schema_file(self, schema_file: Path):
        """Import a Python schema file to register its schemas"""
        module_name = schema_file.stem
        spec = importlib.util.spec_from_file_location(module_name, schema_file)
        module = importlib.util.module_from_spec(spec)

        # Add to sys.modules so imports work correctly
        sys.modules[module_name] = module
        spec.loader.exec_module(module)

    def _generate_target(self, target: str, schemas, output_dir: Path):
        """Generate files for a specific target using generator metadata.

        Uses file_extension, generates_index_file, generate_index(),
        get_schema_filename(), and get_extra_files() from the generator
        itself to determine file structure, eliminating per-target branching.

        Args:
            target: Target generator name (e.g., 'pydantic')
            schemas: List of USRSchema objects
            output_dir: Base output directory
        """
        generator = self.generators[target]
        target_dir = output_dir / target
        target_dir.mkdir(parents=True, exist_ok=True)

        print(f"\nGenerating {target} models...")

        # 1. Write extra files (e.g. _base.py for SQLAlchemy)
        extra_files = generator.get_extra_files(schemas, target_dir)
        for filename, content in extra_files.items():
            extra_path = target_dir / filename
            with open(extra_path, "w") as f:
                f.write(content)
            print(f"  \u2713 {filename}")

        # 2. Write per-schema files
        for schema in schemas:
            schema_filename = generator.get_schema_filename(schema)
            schema_file = target_dir / schema_filename

            file_content = generator.generate_file(schema)

            with open(schema_file, "w") as f:
                f.write(file_content)

            print(f"  \u2713 {schema_filename}")

        # 3. Write index file if the generator produces one
        if generator.generates_index_file:
            index_content = generator.generate_index(schemas, target_dir)
            if index_content is not None:
                # Generator owns its index filename (lib.rs for Rust,
                # index.ts for Zod, __init__.py for Python targets, ...).
                index_filename = getattr(generator, "index_filename", "__init__.py")

                index_path = target_dir / index_filename
                with open(index_path, "w") as f:
                    f.write(index_content)

                print(f"  \u2713 {index_filename}")

        print(f"  Generated {len(schemas)} schema file(s) in {target_dir}")


def create_generation_engine(
    config_path: str = ".schema-gen.config.py",
) -> SchemaGenerationEngine:
    """Create a generation engine with configuration

    Args:
        config_path: Path to configuration file

    Returns:
        Configured SchemaGenerationEngine
    """
    config = Config.from_file(config_path)
    return SchemaGenerationEngine(config)
