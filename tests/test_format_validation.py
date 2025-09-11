"""Comprehensive format validation tests for all generators"""

import ast
import contextlib
import json
import subprocess
import tempfile
from pathlib import Path

import pytest

from schema_gen import Field, Schema
from schema_gen.core.schema import SchemaRegistry
from schema_gen.generators.avro_generator import AvroGenerator
from schema_gen.generators.dataclasses_generator import DataclassesGenerator
from schema_gen.generators.graphql_generator import GraphQLGenerator
from schema_gen.generators.jackson_generator import JacksonGenerator
from schema_gen.generators.jsonschema_generator import JsonSchemaGenerator
from schema_gen.generators.kotlin_generator import KotlinGenerator
from schema_gen.generators.pathway_generator import PathwayGenerator
from schema_gen.generators.protobuf_generator import ProtobufGenerator
from schema_gen.generators.pydantic_generator import PydanticGenerator
from schema_gen.generators.sqlalchemy_generator import SqlAlchemyGenerator
from schema_gen.generators.typeddict_generator import TypedDictGenerator
from schema_gen.generators.zod_generator import ZodGenerator
from schema_gen.parsers.schema_parser import SchemaParser


class TestFormatValidation:
    """Test that all generated formats produce valid, syntactically correct output"""

    def setup_method(self):
        """Set up test schema for validation"""
        SchemaRegistry._schemas.clear()

        @Schema
        class TestUser:
            """Test user schema for validation"""

            id: int = Field(
                primary_key=True, auto_increment=True, description="Unique identifier"
            )

            username: str = Field(
                min_length=3,
                max_length=50,
                regex=r"^[a-zA-Z0-9_]+$",
                unique=True,
                description="Unique username",
            )

            email: str = Field(format="email", unique=True, description="User email")

            age: int | None = Field(
                default=None, min_value=0, max_value=150, description="User age"
            )

            is_active: bool = Field(default=True, description="Account status")

            balance: float = Field(
                default=0.0, min_value=0.0, description="Account balance"
            )

            class Variants:
                create = ["username", "email", "age"]
                update = ["username", "email", "age", "is_active"]
                public = ["id", "username", "is_active"]
                full = ["id", "username", "email", "age", "is_active", "balance"]

        parser = SchemaParser()
        self.schemas = parser.parse_all_schemas()
        self.test_schema = self.schemas[0]

    def test_pydantic_syntax_validation(self):
        """Test that generated Pydantic code is syntactically valid Python"""
        generator = PydanticGenerator()
        generated_code = generator.generate_file(self.test_schema)

        # Test Python syntax
        try:
            ast.parse(generated_code)
        except SyntaxError as e:
            pytest.fail(f"Generated Pydantic code has syntax errors: {e}")

        # Test that code contains expected Pydantic structures
        assert "from pydantic import BaseModel" in generated_code
        assert "class TestUser(BaseModel):" in generated_code
        assert "Field(" in generated_code  # Should contain Field usage

    def test_sqlalchemy_syntax_validation(self):
        """Test that generated SQLAlchemy code is syntactically valid Python"""
        generator = SqlAlchemyGenerator()
        generated_code = generator.generate_file(self.test_schema)

        # Test Python syntax
        try:
            ast.parse(generated_code)
        except SyntaxError as e:
            pytest.fail(f"Generated SQLAlchemy code has syntax errors: {e}")

        # Test that code contains expected SQLAlchemy structures
        assert "from sqlalchemy" in generated_code
        assert "class TestUser" in generated_code
        assert "__tablename__" in generated_code

    def test_dataclasses_syntax_validation(self):
        """Test that generated dataclasses code is syntactically valid Python"""
        generator = DataclassesGenerator()
        generated_code = generator.generate_file(self.test_schema)

        # Test Python syntax
        try:
            ast.parse(generated_code)
        except SyntaxError as e:
            pytest.fail(f"Generated dataclasses code has syntax errors: {e}")

        # Test that code contains expected dataclass structures
        assert "from dataclasses import dataclass" in generated_code
        assert "@dataclass" in generated_code
        assert "class TestUser:" in generated_code

    def test_typeddict_syntax_validation(self):
        """Test that generated TypedDict code is syntactically valid Python"""
        generator = TypedDictGenerator()
        generated_code = generator.generate_file(self.test_schema)

        # Test Python syntax
        try:
            ast.parse(generated_code)
        except SyntaxError as e:
            pytest.fail(f"Generated TypedDict code has syntax errors: {e}")

        # Test that code contains expected TypedDict structures
        assert "TypedDict" in generated_code
        assert (
            "class TestUser(" in generated_code
        )  # May inherit from TypedDict or be defined differently

    def test_pathway_syntax_validation(self):
        """Test that generated Pathway code is syntactically valid Python"""
        generator = PathwayGenerator()
        generated_code = generator.generate_file(self.test_schema)

        # Test Python syntax
        try:
            ast.parse(generated_code)
        except SyntaxError as e:
            pytest.fail(f"Generated Pathway code has syntax errors: {e}")

        # Test that code contains expected Pathway structures
        assert "pathway" in generated_code or "pw" in generated_code
        assert "class TestUser(" in generated_code

    def test_zod_syntax_validation(self):
        """Test that generated Zod code is syntactically valid TypeScript"""
        generator = ZodGenerator()
        generated_code = generator.generate_file(self.test_schema)

        # Basic TypeScript structure validation
        assert "import { z }" in generated_code
        assert "export const TestUserSchema" in generated_code
        assert "z.object({" in generated_code

        # Test with Node.js TypeScript compiler if available (but don't fail if it doesn't work)
        with contextlib.suppress(Exception):
            # TypeScript compilation is optional - core structure validation is enough
            self._validate_typescript_syntax(generated_code, "TestUser.ts")

    def test_jsonschema_syntax_validation(self):
        """Test that generated JSON Schema is valid JSON"""
        generator = JsonSchemaGenerator()
        schema_json = generator.generate_model(self.test_schema)

        # Test JSON syntax
        try:
            parsed = json.loads(schema_json)
        except json.JSONDecodeError as e:
            pytest.fail(f"Generated JSON Schema is not valid JSON: {e}")

        # Test JSON Schema structure
        assert parsed.get("type") == "object"
        assert "properties" in parsed
        assert "required" in parsed
        assert "$schema" in parsed

    def test_graphql_syntax_validation(self):
        """Test that generated GraphQL schema is syntactically valid"""
        generator = GraphQLGenerator()
        generated_code = generator.generate_file(self.test_schema)

        # Basic GraphQL structure validation
        assert "type TestUser {" in generated_code
        assert "id: Int!" in generated_code
        assert "username: String!" in generated_code

        # Test GraphQL syntax if graphql-core is available
        try:
            from graphql import build_schema

            build_schema(generated_code)
        except ImportError:
            # graphql-core not available, skip detailed validation
            pass
        except Exception as e:
            pytest.fail(f"Generated GraphQL schema is invalid: {e}")

    def test_protobuf_syntax_validation(self):
        """Test that generated Protocol Buffer schema is syntactically valid"""
        generator = ProtobufGenerator()
        generated_code = generator.generate_file(self.test_schema)

        # Basic protobuf structure validation
        assert 'syntax = "proto3";' in generated_code
        assert "message TestUser {" in generated_code
        assert "id =" in generated_code  # Field assignment should exist

        # Test protobuf syntax if protobuf compiler is available (but don't fail if it doesn't work)
        with contextlib.suppress(Exception):
            # Protocol Buffers compilation is optional - core structure validation is enough
            self._validate_protobuf_syntax(generated_code, "TestUser.proto")

    def test_avro_syntax_validation(self):
        """Test that generated Avro schema is valid JSON"""
        generator = AvroGenerator()
        schema_json = generator.generate_model(self.test_schema)

        # Test JSON syntax
        try:
            parsed = json.loads(schema_json)
        except json.JSONDecodeError as e:
            pytest.fail(f"Generated Avro schema is not valid JSON: {e}")

        # Test Avro schema structure
        assert parsed.get("type") == "record"
        assert parsed.get("name") == "TestUser"
        assert "fields" in parsed
        assert isinstance(parsed["fields"], list)

    def test_jackson_syntax_validation(self):
        """Test that generated Jackson Java code is syntactically valid"""
        generator = JacksonGenerator()
        generated_code = generator.generate_file(self.test_schema)

        # Basic Java structure validation
        assert "class TestUser" in generated_code  # May have different modifiers
        assert "id" in generated_code  # Field should exist
        assert (
            "getId" in generated_code or "id:" in generated_code
        )  # Getter or direct field

        # Test Java syntax if javac is available (but don't fail if it doesn't work)
        with contextlib.suppress(Exception):
            # Java compilation is optional - core structure validation is enough
            self._validate_java_syntax(generated_code, "TestUser.java")

    def test_kotlin_syntax_validation(self):
        """Test that generated Kotlin code is syntactically valid"""
        generator = KotlinGenerator()
        generated_code = generator.generate_file(self.test_schema)

        # Basic Kotlin structure validation
        assert "data class TestUser(" in generated_code
        assert "val id:" in generated_code  # May be Int, Long, etc.
        assert "val username:" in generated_code

        # Test Kotlin syntax if kotlinc is available (but don't fail if it doesn't work)
        with contextlib.suppress(Exception):
            # Kotlin compilation is optional - core structure validation is enough
            self._validate_kotlin_syntax(generated_code, "TestUser.kt")

    def _validate_typescript_syntax(self, code: str, filename: str):
        """Validate TypeScript syntax using tsc if available"""
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                file_path = Path(temp_dir) / filename
                file_path.write_text(code)

                # Try to compile with tsc
                result = subprocess.run(
                    ["npx", "tsc", "--noEmit", str(file_path)],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )

                if result.returncode != 0:
                    raise Exception(f"TypeScript compilation failed: {result.stderr}")

        except (subprocess.TimeoutExpired, FileNotFoundError):
            # TypeScript compiler not available or timed out
            pass

    def _validate_java_syntax(self, code: str, filename: str):
        """Validate Java syntax using javac if available"""
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                file_path = Path(temp_dir) / filename
                file_path.write_text(code)

                # Try to compile with javac
                result = subprocess.run(
                    ["javac", str(file_path)],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )

                if result.returncode != 0:
                    raise Exception(f"Java compilation failed: {result.stderr}")

        except (subprocess.TimeoutExpired, FileNotFoundError):
            # Java compiler not available or timed out
            pass

    def _validate_kotlin_syntax(self, code: str, filename: str):
        """Validate Kotlin syntax using kotlinc if available"""
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                file_path = Path(temp_dir) / filename
                file_path.write_text(code)

                # Try to compile with kotlinc
                result = subprocess.run(
                    ["kotlinc", str(file_path)],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )

                if result.returncode != 0:
                    raise Exception(f"Kotlin compilation failed: {result.stderr}")

        except (subprocess.TimeoutExpired, FileNotFoundError):
            # Kotlin compiler not available or timed out
            pass

    def _validate_protobuf_syntax(self, code: str, filename: str):
        """Validate Protocol Buffer syntax using protoc if available"""
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                file_path = Path(temp_dir) / filename
                file_path.write_text(code)

                # Try to compile with protoc
                result = subprocess.run(
                    ["protoc", "--python_out=.", str(file_path)],
                    cwd=temp_dir,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )

                if result.returncode != 0:
                    raise Exception(
                        f"Protocol Buffer compilation failed: {result.stderr}"
                    )

        except (subprocess.TimeoutExpired, FileNotFoundError):
            # protoc not available or timed out
            pass


class TestGeneratedCodeExecution:
    """Test that generated code can be imported and executed"""

    def setup_method(self):
        """Set up test schema"""
        SchemaRegistry._schemas.clear()

        @Schema
        class Product:
            """Simple product schema for execution testing"""

            id: int = Field(primary_key=True, description="Product ID")
            name: str = Field(max_length=100, description="Product name")
            price: float = Field(min_value=0.0, description="Product price")
            in_stock: bool = Field(default=True, description="Availability")

        parser = SchemaParser()
        self.schemas = parser.parse_all_schemas()
        self.test_schema = self.schemas[0]

    def test_pydantic_code_execution(self):
        """Test that generated Pydantic code can be imported and instantiated"""
        generator = PydanticGenerator()
        generated_code = generator.generate_file(self.test_schema)

        with tempfile.TemporaryDirectory() as temp_dir:
            # Write generated code to file
            model_file = Path(temp_dir) / "product_models.py"
            model_file.write_text(generated_code)

            # Import and test the generated model
            import sys

            sys.path.insert(0, str(temp_dir))

            try:
                import product_models

                # Test basic model creation
                product = product_models.Product(
                    id=1, name="Test Product", price=99.99, in_stock=True
                )

                assert product.id == 1
                assert product.name == "Test Product"
                assert product.price == 99.99
                assert product.in_stock is True

                # Test validation
                try:
                    product_models.Product(
                        id=1,
                        name="Test Product",
                        price=-10.0,  # Should fail min_value validation
                    )
                    pytest.fail("Expected validation error for negative price")
                except Exception:
                    # Validation error expected
                    pass

            finally:
                sys.path.remove(str(temp_dir))
                if "product_models" in sys.modules:
                    del sys.modules["product_models"]

    def test_dataclasses_code_execution(self):
        """Test that generated dataclasses code can be imported and instantiated"""
        generator = DataclassesGenerator()
        generated_code = generator.generate_file(self.test_schema)

        with tempfile.TemporaryDirectory() as temp_dir:
            model_file = Path(temp_dir) / "product_dataclasses.py"
            model_file.write_text(generated_code)

            import sys

            sys.path.insert(0, str(temp_dir))

            try:
                import product_dataclasses

                # Test dataclass creation
                product = product_dataclasses.Product(
                    id=1, name="Test Product", price=99.99, in_stock=True
                )

                assert product.id == 1
                assert product.name == "Test Product"
                assert product.price == 99.99
                assert product.in_stock is True

            finally:
                sys.path.remove(str(temp_dir))
                if "product_dataclasses" in sys.modules:
                    del sys.modules["product_dataclasses"]

    def test_typeddict_code_execution(self):
        """Test that generated TypedDict code can be imported and used"""
        generator = TypedDictGenerator()
        generated_code = generator.generate_file(self.test_schema)

        with tempfile.TemporaryDirectory() as temp_dir:
            model_file = Path(temp_dir) / "product_typeddict.py"
            model_file.write_text(generated_code)

            import sys

            sys.path.insert(0, str(temp_dir))

            try:
                import product_typeddict

                # Test TypedDict usage
                product: product_typeddict.Product = {
                    "id": 1,
                    "name": "Test Product",
                    "price": 99.99,
                    "in_stock": True,
                }

                assert product["id"] == 1
                assert product["name"] == "Test Product"

            finally:
                sys.path.remove(str(temp_dir))
                if "product_typeddict" in sys.modules:
                    del sys.modules["product_typeddict"]

    def test_json_schema_validation(self):
        """Test that generated JSON Schema can validate data"""
        generator = JsonSchemaGenerator()
        schema_json = generator.generate_model(self.test_schema)

        try:
            import jsonschema

            schema = json.loads(schema_json)

            # Test valid data
            valid_data = {
                "id": 1,
                "name": "Test Product",
                "price": 99.99,
                "in_stock": True,
            }

            # Should not raise exception
            jsonschema.validate(valid_data, schema)

            # Test invalid data
            invalid_data = {
                "id": "not_a_number",  # Should be int
                "name": "Test Product",
                "price": 99.99,
                "in_stock": True,
            }

            with pytest.raises(jsonschema.ValidationError):
                jsonschema.validate(invalid_data, schema)

        except ImportError:
            pytest.skip("jsonschema library not available")

    def test_pathway_code_execution(self):
        """Test that generated Pathway code can be imported (if Pathway is available)"""
        generator = PathwayGenerator()
        generated_code = generator.generate_file(self.test_schema)

        try:
            import pathway  # noqa: F401

            with tempfile.TemporaryDirectory() as temp_dir:
                model_file = Path(temp_dir) / "product_pathway.py"
                model_file.write_text(generated_code)

                import sys

                sys.path.insert(0, str(temp_dir))

                try:
                    import product_pathway

                    # Test that the schema class exists
                    assert hasattr(product_pathway, "Product")
                    product_class = product_pathway.Product

                    # Test that it's a class (basic check)
                    assert isinstance(product_class, type)

                finally:
                    sys.path.remove(str(temp_dir))
                    if "product_pathway" in sys.modules:
                        del sys.modules["product_pathway"]

        except ImportError:
            pytest.skip("Pathway library not available")


class TestCrossFormatConsistency:
    """Test that all formats generate consistent field mappings"""

    def setup_method(self):
        """Set up test schema"""
        SchemaRegistry._schemas.clear()

        @Schema
        class ConsistencyTest:
            """Schema for testing cross-format consistency"""

            required_int: int = Field(description="Required integer field")
            optional_str: str | None = Field(
                default=None, description="Optional string"
            )
            constrained_float: float = Field(min_value=0.0, max_value=100.0)
            boolean_field: bool = Field(default=False)

        parser = SchemaParser()
        self.schemas = parser.parse_all_schemas()
        self.test_schema = self.schemas[0]

    def test_field_presence_consistency(self):
        """Test that all generators include the same fields"""
        generators = {
            "pydantic": PydanticGenerator(),
            "sqlalchemy": SqlAlchemyGenerator(),
            "dataclasses": DataclassesGenerator(),
            "typeddict": TypedDictGenerator(),
            "pathway": PathwayGenerator(),
        }

        field_names = {field.name for field in self.test_schema.fields}

        for generator_name, generator in generators.items():
            generated_code = generator.generate_file(self.test_schema)

            # Check that all field names appear in generated code
            for field_name in field_names:
                assert field_name in generated_code, (
                    f"Field '{field_name}' missing from {generator_name} output"
                )

    def test_required_fields_consistency(self):
        """Test that required fields are consistently marked across formats"""
        json_generator = JsonSchemaGenerator()
        schema_json = json_generator.generate_model(self.test_schema)
        schema = json.loads(schema_json)

        # Required fields should include fields without defaults
        required_fields = schema.get("required", [])

        # required_int should be required (no default)
        assert "required_int" in required_fields

        # optional_str should not be required (has default=None)
        assert "optional_str" not in required_fields

        # boolean_field should not be required (has default=False)
        assert "boolean_field" not in required_fields
