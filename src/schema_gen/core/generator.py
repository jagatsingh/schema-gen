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


class SchemaGenerationEngine:
    """Main engine that orchestrates schema generation"""
    
    def __init__(self, config: Config):
        self.config = config
        self.parser = SchemaParser()
        
        # Initialize generators based on config targets
        self.generators = {}
        if "pydantic" in config.targets:
            self.generators["pydantic"] = PydanticGenerator()
        # TODO: Add other generators as they're implemented
        
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
            if schema_file.name.startswith('__'):
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
            raise ValueError("No schemas found. Make sure your schema files are imported and use @Schema decorator.")
        
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
        # TODO: Add other target handlers
    
    def _generate_pydantic_files(self, generator: PydanticGenerator, schemas, output_dir: Path):
        """Generate Pydantic model files"""
        
        # Create __init__.py for the pydantic package
        init_file = output_dir / "__init__.py"
        init_imports = []
        
        for schema in schemas:
            # Generate all variants for this schema
            variants = generator.generate_all_variants(schema)
            
            # Create a file for this schema's models
            schema_file = output_dir / f"{schema.name.lower()}_models.py"
            
            # Write all variants to the file
            with open(schema_file, 'w') as f:
                # Write base model first
                f.write(variants['base'])
                f.write('\n\n')
                
                # Write variant models
                for variant_name, variant_code in variants.items():
                    if variant_name != 'base':
                        f.write(variant_code)
                        f.write('\n\n')
            
            print(f"  ✓ {schema_file.name}")
            
            # Collect imports for __init__.py
            base_class = schema.name
            variant_classes = [generator._variant_to_class_name(schema.name, v) 
                             for v in schema.variants.keys()]
            all_classes = [base_class] + variant_classes
            
            init_imports.append(f"from .{schema.name.lower()}_models import {', '.join(all_classes)}")
        
        # Write __init__.py
        with open(init_file, 'w') as f:
            f.write('"""Generated Pydantic models"""\n\n')
            for import_line in init_imports:
                f.write(import_line + '\n')
            f.write('\n__all__ = [\n')
            for schema in schemas:
                base_class = schema.name
                variant_classes = [generator._variant_to_class_name(schema.name, v) 
                                 for v in schema.variants.keys()]
                all_classes = [f'"{c}"' for c in [base_class] + variant_classes]
                f.write(f'    {", ".join(all_classes)},\n')
            f.write(']\n')
        
        print(f"  ✓ __init__.py")
        print(f"  Generated {len(schemas)} schema file(s) in {output_dir}")


def create_generation_engine(config_path: str = ".schema-gen.config.py") -> SchemaGenerationEngine:
    """Create a generation engine with configuration
    
    Args:
        config_path: Path to configuration file
        
    Returns:
        Configured SchemaGenerationEngine
    """
    config = Config.from_file(config_path)
    return SchemaGenerationEngine(config)