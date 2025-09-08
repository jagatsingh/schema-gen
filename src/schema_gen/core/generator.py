"""Core generation engine for schema_gen"""

import os
import sys
import importlib.util
from pathlib import Path
from typing import List, Dict, Any

from .config import Config
from .schema import SchemaRegistry
from ..parsers.schema_parser import SchemaParser
from ..generators.pydantic_generator import PydanticGenerator
from ..generators.sqlalchemy_generator import SqlAlchemyGenerator
from ..generators.zod_generator import ZodGenerator
from ..generators.pathway_generator import PathwayGenerator
from ..generators.dataclasses_generator import DataclassesGenerator
from ..generators.typeddict_generator import TypedDictGenerator
from ..generators.jsonschema_generator import JsonSchemaGenerator
from ..generators.graphql_generator import GraphQLGenerator
from ..generators.protobuf_generator import ProtobufGenerator
from ..generators.avro_generator import AvroGenerator
from ..generators.jackson_generator import JacksonGenerator
from ..generators.kotlin_generator import KotlinGenerator


class SchemaGenerationEngine:
    """Main engine that orchestrates schema generation"""

    def __init__(self, config: Config):
        self.config = config
        self.parser = SchemaParser()

        # Initialize generators based on config targets
        self.generators = {}
        if "pydantic" in config.targets:
            self.generators["pydantic"] = PydanticGenerator()
        if "sqlalchemy" in config.targets:
            self.generators["sqlalchemy"] = SqlAlchemyGenerator()
        if "zod" in config.targets:
            self.generators["zod"] = ZodGenerator()
        if "pathway" in config.targets:
            self.generators["pathway"] = PathwayGenerator()
        if "dataclasses" in config.targets:
            self.generators["dataclasses"] = DataclassesGenerator()
        if "typeddict" in config.targets:
            self.generators["typeddict"] = TypedDictGenerator()
        if "jsonschema" in config.targets:
            self.generators["jsonschema"] = JsonSchemaGenerator()
        if "graphql" in config.targets:
            self.generators["graphql"] = GraphQLGenerator()
        if "protobuf" in config.targets:
            self.generators["protobuf"] = ProtobufGenerator()
        if "avro" in config.targets:
            self.generators["avro"] = AvroGenerator()
        if "jackson" in config.targets:
            self.generators["jackson"] = JacksonGenerator()
        if "kotlin" in config.targets:
            self.generators["kotlin"] = KotlinGenerator()

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
                print(f"Warning: Failed to import {schema_file}: {e}")

    def generate_all(self, targets: List[str] = None, output_dir: str = None):
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
                print(f"Warning: Generator for '{target}' not implemented yet")
                continue

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
        """Generate files for a specific target

        Args:
            target: Target generator name (e.g., 'pydantic')
            schemas: List of USRSchema objects
            output_dir: Base output directory
        """
        generator = self.generators[target]
        target_dir = output_dir / target
        target_dir.mkdir(parents=True, exist_ok=True)

        print(f"\nGenerating {target} models...")

        if target == "pydantic":
            self._generate_pydantic_files(generator, schemas, target_dir)
        elif target == "sqlalchemy":
            self._generate_sqlalchemy_files(generator, schemas, target_dir)
        elif target == "zod":
            self._generate_zod_files(generator, schemas, target_dir)
        elif target == "pathway":
            self._generate_python_files(generator, schemas, target_dir, "pathway")
        elif target == "dataclasses":
            self._generate_python_files(generator, schemas, target_dir, "dataclasses")
        elif target == "typeddict":
            self._generate_python_files(generator, schemas, target_dir, "typeddict")
        elif target == "jsonschema":
            self._generate_json_files(generator, schemas, target_dir)
        elif target == "graphql":
            self._generate_graphql_files(generator, schemas, target_dir)
        elif target == "protobuf":
            self._generate_protobuf_files(generator, schemas, target_dir)
        elif target == "avro":
            self._generate_avro_files(generator, schemas, target_dir)
        elif target == "jackson":
            self._generate_jackson_files(generator, schemas, target_dir)
        elif target == "kotlin":
            self._generate_kotlin_files(generator, schemas, target_dir)

    def _generate_pydantic_files(
        self, generator: PydanticGenerator, schemas, output_dir: Path
    ):
        """Generate Pydantic model files"""

        # Create __init__.py for the pydantic package
        init_file = output_dir / "__init__.py"
        init_imports = []

        for schema in schemas:
            # Create a file for this schema's models
            schema_file = output_dir / f"{schema.name.lower()}_models.py"

            # Generate complete file with all variants
            file_content = generator.generate_file(schema)

            # Write to file
            with open(schema_file, "w") as f:
                f.write(file_content)

            print(f"  ✓ {schema_file.name}")

            # Collect imports for __init__.py
            base_class = schema.name
            variant_classes = [
                generator._variant_to_class_name(schema.name, v)
                for v in schema.variants.keys()
            ]
            all_classes = [base_class] + variant_classes

            init_imports.append(
                f"from .{schema.name.lower()}_models import {', '.join(all_classes)}"
            )

        # Write __init__.py
        with open(init_file, "w") as f:
            f.write('"""Generated Pydantic models"""\n\n')
            for import_line in init_imports:
                f.write(import_line + "\n")
            f.write("\n__all__ = [\n")
            for schema in schemas:
                base_class = schema.name
                variant_classes = [
                    generator._variant_to_class_name(schema.name, v)
                    for v in schema.variants.keys()
                ]
                all_classes = [f'"{c}"' for c in [base_class] + variant_classes]
                f.write(f'    {", ".join(all_classes)},\n')
            f.write("]\n")

        print(f"  ✓ __init__.py")
        print(f"  Generated {len(schemas)} schema file(s) in {output_dir}")

    def _generate_sqlalchemy_files(self, generator, schemas, output_dir: Path):
        """Generate SQLAlchemy model files"""

        # Create __init__.py for the sqlalchemy package
        init_file = output_dir / "__init__.py"
        init_imports = []

        for schema in schemas:
            # Create a file for this schema's models
            schema_file = output_dir / f"{schema.name.lower()}_models.py"

            # Generate complete file
            file_content = generator.generate_file(schema)

            # Write to file
            with open(schema_file, "w") as f:
                f.write(file_content)

            print(f"  ✓ {schema_file.name}")

            # Collect imports for __init__.py
            init_imports.append(
                f"from .{schema.name.lower()}_models import {schema.name}"
            )

        # Write __init__.py
        with open(init_file, "w") as f:
            f.write('"""Generated SQLAlchemy models"""\n\n')
            for import_line in init_imports:
                f.write(import_line + "\n")
            f.write("\n__all__ = [\n")
            for schema in schemas:
                f.write(f'    "{schema.name}",\n')
            f.write("]\n")

        print(f"  ✓ __init__.py")
        print(f"  Generated {len(schemas)} schema file(s) in {output_dir}")

    def _generate_zod_files(self, generator, schemas, output_dir: Path):
        """Generate Zod schema files (TypeScript)"""

        # Create index.ts for the zod package
        index_file = output_dir / "index.ts"
        exports = []

        for schema in schemas:
            # Create a TypeScript file for this schema's models
            schema_file = output_dir / f"{schema.name.lower()}.ts"

            # Generate complete file with all variants
            file_content = generator.generate_file(schema)

            # Write to file
            with open(schema_file, "w") as f:
                f.write(file_content)

            print(f"  ✓ {schema_file.name}")

            # Collect exports for index.ts
            base_export = f"{schema.name}Schema, {schema.name}"
            variant_exports = [
                f"{generator._variant_to_schema_name(schema.name, v)}Schema, {generator._variant_to_schema_name(schema.name, v)}"
                for v in schema.variants.keys()
            ]
            all_exports = [base_export] + variant_exports

            exports.append(
                f"export {{ {', '.join(all_exports)} }} from './{schema.name.lower()}';"
            )

        # Write index.ts
        with open(index_file, "w") as f:
            f.write("/**\n")
            f.write(" * Generated Zod schemas\n")
            f.write(" * Auto-generated by schema-gen\n")
            f.write(" */\n\n")
            for export_line in exports:
                f.write(export_line + "\n")

        print(f"  ✓ index.ts")
        print(f"  Generated {len(schemas)} schema file(s) in {output_dir}")

    def _generate_python_files(
        self, generator, schemas, output_dir: Path, target_name: str
    ):
        """Generate Python files for dataclasses, typeddict, or pathway"""

        # Create __init__.py
        init_file = output_dir / "__init__.py"
        init_imports = []

        for schema in schemas:
            # Create a file for this schema
            schema_file = output_dir / f"{schema.name.lower()}_models.py"

            # Generate complete file
            file_content = generator.generate_file(schema)

            # Write to file
            with open(schema_file, "w") as f:
                f.write(file_content)

            print(f"  ✓ {schema_file.name}")

            # Collect imports for __init__.py
            base_class = schema.name
            variant_classes = [
                generator._variant_to_class_name(schema.name, v)
                for v in schema.variants.keys()
            ]
            all_classes = [base_class] + variant_classes

            init_imports.append(
                f"from .{schema.name.lower()}_models import {', '.join(all_classes)}"
            )

        # Write __init__.py
        with open(init_file, "w") as f:
            f.write(f'"""Generated {target_name.title()} models"""\n\n')
            for import_line in init_imports:
                f.write(import_line + "\n")
            f.write("\n__all__ = [\n")
            for schema in schemas:
                base_class = schema.name
                variant_classes = [
                    generator._variant_to_class_name(schema.name, v)
                    for v in schema.variants.keys()
                ]
                all_classes = [f'"{c}"' for c in [base_class] + variant_classes]
                f.write(f'    {", ".join(all_classes)},\n')
            f.write("]\n")

        print(f"  ✓ __init__.py")
        print(f"  Generated {len(schemas)} schema file(s) in {output_dir}")

    def _generate_json_files(self, generator, schemas, output_dir: Path):
        """Generate JSON Schema files"""

        for schema in schemas:
            # Create a JSON file for this schema
            schema_file = output_dir / f"{schema.name.lower()}.json"

            # Generate complete JSON schema
            file_content = generator.generate_file(schema)

            # Write to file
            with open(schema_file, "w") as f:
                f.write(file_content)

            print(f"  ✓ {schema_file.name}")

        print(f"  Generated {len(schemas)} JSON schema file(s) in {output_dir}")

    def _generate_graphql_files(self, generator, schemas, output_dir: Path):
        """Generate GraphQL schema files"""

        for schema in schemas:
            # Create a GraphQL file for this schema
            schema_file = output_dir / f"{schema.name.lower()}.graphql"

            # Generate complete GraphQL schema
            file_content = generator.generate_file(schema)

            # Write to file
            with open(schema_file, "w") as f:
                f.write(file_content)

            print(f"  ✓ {schema_file.name}")

        print(f"  Generated {len(schemas)} GraphQL schema file(s) in {output_dir}")

    def _generate_protobuf_files(self, generator, schemas, output_dir: Path):
        """Generate Protobuf schema files"""

        for schema in schemas:
            # Create a .proto file for this schema
            schema_file = output_dir / f"{schema.name.lower()}.proto"

            # Generate complete Protobuf schema
            file_content = generator.generate_file(schema)

            # Write to file
            with open(schema_file, "w") as f:
                f.write(file_content)

            print(f"  ✓ {schema_file.name}")

        print(f"  Generated {len(schemas)} Protobuf schema file(s) in {output_dir}")

    def _generate_avro_files(self, generator, schemas, output_dir: Path):
        """Generate Avro schema files"""

        for schema in schemas:
            # Create an .avsc file for this schema
            schema_file = output_dir / f"{schema.name.lower()}.avsc"

            # Generate complete Avro schema
            file_content = generator.generate_file(schema)

            # Write to file
            with open(schema_file, "w") as f:
                f.write(file_content)

            print(f"  ✓ {schema_file.name}")

        print(f"  Generated {len(schemas)} Avro schema file(s) in {output_dir}")

    def _generate_jackson_files(self, generator, schemas, output_dir: Path):
        """Generate Jackson Java class files"""

        for schema in schemas:
            # Create a .java file for this schema
            schema_file = output_dir / f"{schema.name}.java"

            # Generate complete Java class with Jackson annotations
            file_content = generator.generate_file(schema)

            # Write to file
            with open(schema_file, "w") as f:
                f.write(file_content)

            print(f"  ✓ {schema_file.name}")

        print(f"  Generated {len(schemas)} Jackson Java file(s) in {output_dir}")

    def _generate_kotlin_files(self, generator, schemas, output_dir: Path):
        """Generate Kotlin data class files"""

        for schema in schemas:
            # Create a .kt file for this schema
            schema_file = output_dir / f"{schema.name}.kt"

            # Generate complete Kotlin data classes
            file_content = generator.generate_file(schema)

            # Write to file
            with open(schema_file, "w") as f:
                f.write(file_content)

            print(f"  ✓ {schema_file.name}")

        print(f"  Generated {len(schemas)} Kotlin data class file(s) in {output_dir}")


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
