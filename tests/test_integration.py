"""Integration tests for end-to-end schema generation"""

import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from schema_gen import Field, Schema
from schema_gen.core.config import Config
from schema_gen.core.generator import SchemaGenerationEngine
from schema_gen.core.schema import SchemaRegistry
from schema_gen.generators.pydantic_generator import PydanticGenerator
from schema_gen.parsers.schema_parser import SchemaParser


class TestEndToEndGeneration:
    """Test complete schema generation workflow"""

    def setup_method(self):
        """Clear registry before each test"""
        SchemaRegistry._schemas.clear()

    def test_complete_pydantic_generation_workflow(self):
        """Test the complete workflow from schema definition to Pydantic generation"""

        # 1. Define a comprehensive schema
        @Schema
        class User:
            """Complete user schema for testing"""

            id: int = Field(
                primary_key=True,
                auto_increment=True,
                description="Unique user identifier",
            )

            username: str = Field(
                min_length=3,
                max_length=30,
                regex=r"^[a-zA-Z0-9_]+$",
                unique=True,
                description="Unique username",
            )

            email: str = Field(
                format="email", unique=True, description="User email address"
            )

            age: int | None = Field(
                default=None, min_value=13, max_value=120, description="User age"
            )

            created_at: datetime = Field(
                auto_now_add=True, description="Account creation timestamp"
            )

            class Variants:
                create_request = ["username", "email", "age"]
                public_response = ["id", "username", "age"]
                full_response = ["id", "username", "email", "age", "created_at"]

        # 2. Parse schema to USR
        parser = SchemaParser()
        usr_schema = parser.parse_schema(User)

        assert usr_schema.name == "User"
        assert len(usr_schema.fields) == 5
        assert len(usr_schema.variants) == 3

        # 3. Generate Pydantic models
        generator = PydanticGenerator()

        # Generate base model
        base_model = generator.generate_model(usr_schema)
        assert "class User(BaseModel):" in base_model
        assert "username: str = Field(..., min_length=3, max_length=30" in base_model
        assert "email: EmailStr = Field" in base_model
        assert "age: Optional[int] = Field(default=None, ge=13, le=120" in base_model

        # Generate variant models
        create_model = generator.generate_model(usr_schema, "create_request")
        assert "class UserCreateRequest(BaseModel):" in create_model
        assert "id: int" not in create_model  # Should be excluded
        assert "created_at: datetime" not in create_model  # Should be excluded

        public_model = generator.generate_model(usr_schema, "public_response")
        assert "class UserPublicResponse(BaseModel):" in public_model
        assert "email" not in public_model  # Should be excluded

        # Generate all variants
        all_variants = generator.generate_all_variants(usr_schema)
        assert len(all_variants) == 4  # base + 3 variants

        # 4. Verify generated models are valid Python code
        # This would fail if there were syntax errors
        for variant_name, model_code in all_variants.items():
            assert "AUTO-GENERATED FILE" in model_code
            assert "from pydantic import BaseModel" in model_code
            compile(model_code, f"<{variant_name}>", "exec")

    def test_schema_generation_engine_with_config(self):
        """Test the complete generation engine with configuration"""

        # Create a temporary directory for testing
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create configuration
            config = Config(
                input_dir=str(temp_path / "schemas"),
                output_dir=str(temp_path / "generated"),
                targets=["pydantic"],
            )

            # Create schema directory and file
            schema_dir = temp_path / "schemas"
            schema_dir.mkdir()

            schema_file = schema_dir / "test_schema.py"
            schema_content = '''
from schema_gen import Schema, Field
from typing import Optional

@Schema
class TestModel:
    """Test model for generation engine"""
    name: str = Field(description="Model name")
    value: Optional[int] = Field(default=None, min_value=0)

    class Variants:
        create = ['name', 'value']
        response = ['name', 'value']
'''
            schema_file.write_text(schema_content)

            # Create generation engine
            engine = SchemaGenerationEngine(config)

            # Load schemas and generate
            engine.load_schemas_from_directory()
            engine.generate_all()

            # Verify output files exist
            output_dir = temp_path / "generated" / "pydantic"
            assert output_dir.exists()
            assert (output_dir / "testmodel_models.py").exists()
            assert (output_dir / "__init__.py").exists()

            # Verify generated content
            models_file = output_dir / "testmodel_models.py"
            generated_content = models_file.read_text()

            assert "class TestModel(BaseModel):" in generated_content
            assert "class TestModelCreate(BaseModel):" in generated_content
            assert "class TestModelResponse(BaseModel):" in generated_content
            assert "AUTO-GENERATED FILE" in generated_content

    def test_complex_schema_with_relationships(self):
        """Test schema with complex relationships and types"""

        @Schema
        class SimpleRelationship:
            id: int = Field(primary_key=True)
            name: str = Field()
            # Test simple relationship field
            related_items: list[str] = Field(
                relationship="one_to_many", back_populates="parent"
            )

        parser = SchemaParser()
        generator = PydanticGenerator()

        # Parse schema
        schema = parser.parse_schema(SimpleRelationship)

        # Generate model
        model = generator.generate_model(schema)

        # Verify relationship handling
        assert "related_items: List[str]" in model
        assert "class Config:" in model  # Should have config for relationships
        assert "from_attributes = True" in model

    def test_field_constraints_and_formats(self):
        """Test various field constraints and format handling"""

        @Schema
        class ValidationTest:
            # String constraints
            short_text: str = Field(min_length=1, max_length=10)
            pattern_text: str = Field(regex=r"^[A-Z]+$")
            email_field: str = Field(format="email")

            # Numeric constraints
            positive_int: int = Field(min_value=1)
            ranged_float: float = Field(min_value=0.0, max_value=100.0)

            # Special configurations
            pydantic_specific: str = Field(
                pydantic={"alias": "specialField", "example": "test"}
            )

        parser = SchemaParser()
        generator = PydanticGenerator()

        schema = parser.parse_schema(ValidationTest)
        model_code = generator.generate_model(schema)

        # Verify constraint translation
        assert "min_length=1, max_length=10" in model_code
        assert 'regex=r"^[A-Z]+$"' in model_code
        assert "EmailStr" in model_code
        assert "ge=1" in model_code  # min_value becomes ge (greater or equal)
        assert "ge=0.0, le=100.0" in model_code
        assert 'alias="specialField"' in model_code
        assert 'example="test"' in model_code

    def test_variant_field_inclusion_exclusion(self):
        """Test variant field inclusion and exclusion logic"""

        @Schema
        class VariantTest:
            field1: str = Field()
            field2: str = Field()
            field3: str = Field()
            field4: str = Field()

            class Variants:
                include_some = ["field1", "field2"]
                include_others = ["field3", "field4"]

        parser = SchemaParser()
        generator = PydanticGenerator()

        schema = parser.parse_schema(VariantTest)

        # Test variant field selection
        include_some_fields = schema.get_variant_fields("include_some")
        assert len(include_some_fields) == 2
        field_names = [f.name for f in include_some_fields]
        assert "field1" in field_names
        assert "field2" in field_names
        assert "field3" not in field_names
        assert "field4" not in field_names

        # Generate variant model
        variant_model = generator.generate_model(schema, "include_some")
        assert "field1: str" in variant_model
        assert "field2: str" in variant_model
        assert "field3: str" not in variant_model
        assert "field4: str" not in variant_model


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
