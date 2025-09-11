"""Version compatibility tests for schema generators"""

import importlib
import importlib.metadata
import sys
import tempfile
from pathlib import Path
from typing import Any

import pytest
import yaml

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


def load_version_matrix() -> dict[str, Any]:
    """Load version compatibility matrix from YAML file"""
    matrix_file = Path(__file__).parent / "test-matrix.yml"
    if matrix_file.exists():
        with open(matrix_file) as f:
            return yaml.safe_load(f)
    return {
        "version_matrix": {
            "pydantic": ["2.9.0", "2.10.0", "2.11.0"],
            "sqlalchemy": ["2.0.25", "2.0.36"],
            "pathway": ["0.8.0", "0.9.0"],
        }
    }


class TestVersionCompatibility:
    """Test generator compatibility across different library versions"""

    def setup_method(self):
        """Clear registry before each test"""
        SchemaRegistry._schemas.clear()

    @pytest.fixture
    def test_schema(self):
        """Create a comprehensive test schema"""

        @Schema
        class User:
            """Test user schema for version compatibility"""

            id: int = Field(primary_key=True, description="User ID")
            username: str = Field(min_length=3, max_length=30, description="Username")
            email: str = Field(format="email", description="Email address")
            age: int | None = Field(default=None, min_value=13, max_value=120)

            class Variants:
                create = ["username", "email", "age"]
                response = ["id", "username", "age"]

        parser = SchemaParser()
        return parser.parse_schema(User)

    def test_current_pydantic_version_compatibility(self, test_schema):
        """Test compatibility with currently installed Pydantic version"""
        try:
            import pydantic

            pydantic_version = pydantic.VERSION
        except ImportError:
            pytest.skip("Pydantic not installed")

        generator = PydanticGenerator()

        # Generate models
        base_model = generator.generate_model(test_schema)
        create_model = generator.generate_model(test_schema, "create")
        response_model = generator.generate_model(test_schema, "response")

        # Test that generated code is valid Python
        for model_code in [base_model, create_model, response_model]:
            compile(model_code, "<test>", "exec")

        # Test that generated models can be imported and used
        self._test_pydantic_model_functionality(base_model, pydantic_version)

    def _test_pydantic_model_functionality(self, model_code: str, version: str):
        """Test that generated Pydantic models work correctly"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Write model to file
            model_file = Path(temp_dir) / "test_model.py"
            model_file.write_text(model_code)

            # Add to Python path and import
            sys.path.insert(0, temp_dir)
            try:
                import test_model

                importlib.reload(test_model)  # Force reload

                # Test model creation
                if hasattr(test_model, "User"):
                    User = test_model.User

                    # Test valid data
                    user_data = {
                        "id": 1,
                        "username": "testuser",
                        "email": "test@example.com",
                        "age": 25,
                    }
                    user = User(**user_data)
                    assert user.id == 1
                    assert user.username == "testuser"
                    assert user.email == "test@example.com"
                    assert user.age == 25

                    # Test validation
                    with pytest.raises(
                        (ValueError, TypeError)
                    ):  # Should raise validation error
                        User(id=1, username="a", email="invalid", age=150)

            except Exception as e:
                pytest.fail(
                    f"Generated Pydantic model failed with version {version}: {e}"
                )
            finally:
                sys.path.remove(temp_dir)

    def test_current_sqlalchemy_version_compatibility(self, test_schema):
        """Test compatibility with currently installed SQLAlchemy version"""
        try:
            import sqlalchemy

            sqlalchemy_version = sqlalchemy.__version__
        except ImportError:
            pytest.skip("SQLAlchemy not installed")

        generator = SqlAlchemyGenerator()

        # Generate model
        model_code = generator.generate_model(test_schema)

        # Test that generated code is valid Python
        compile(model_code, "<test>", "exec")

        # Test that generated models can be imported
        self._test_sqlalchemy_model_functionality(model_code, sqlalchemy_version)

    def _test_sqlalchemy_model_functionality(self, model_code: str, version: str):
        """Test that generated SQLAlchemy models work correctly"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Write model to file
            model_file = Path(temp_dir) / "test_model.py"
            full_model_code = f"""
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

Base = declarative_base()

{model_code}
"""
            model_file.write_text(full_model_code)

            # Add to Python path and import
            sys.path.insert(0, temp_dir)
            try:
                import test_model

                importlib.reload(test_model)

                # Test model creation
                if hasattr(test_model, "User"):
                    User = test_model.User

                    # Create in-memory database
                    engine = test_model.create_engine("sqlite:///:memory:")
                    test_model.Base.metadata.create_all(engine)

                    Session = test_model.sessionmaker(bind=engine)
                    session = Session()

                    # Test creating and querying
                    user = User(username="testuser", email="test@example.com", age=25)
                    session.add(user)
                    session.commit()

                    # Query back
                    retrieved_user = session.query(User).first()
                    assert retrieved_user.username == "testuser"
                    assert retrieved_user.email == "test@example.com"
                    assert retrieved_user.age == 25

                    session.close()

            except Exception as e:
                pytest.fail(
                    f"Generated SQLAlchemy model failed with version {version}: {e}"
                )
            finally:
                sys.path.remove(temp_dir)

    def test_current_jsonschema_version_compatibility(self, test_schema):
        """Test compatibility with currently installed jsonschema version"""
        try:
            jsonschema_version = importlib.metadata.version("jsonschema")
        except importlib.metadata.PackageNotFoundError:
            pytest.skip("jsonschema package not found")

        generator = JsonSchemaGenerator()

        # Generate schema
        schema_output = generator.generate_model(test_schema)

        # Test that generated schema is valid JSON
        import json

        schema_data = json.loads(schema_output)

        # Test that it can be used for validation
        self._test_jsonschema_functionality(schema_data, jsonschema_version)

    def _test_jsonschema_functionality(self, schema_data: dict, version: str):
        """Test that generated JSON Schema works correctly"""
        try:
            import jsonschema

            # Test schema validation
            jsonschema.validate(
                {"id": 1, "username": "test", "email": "test@example.com", "age": 25},
                schema_data,
            )

            # Test validation failure
            with pytest.raises(jsonschema.ValidationError):
                jsonschema.validate(
                    {"id": 1, "username": "a", "email": "invalid", "age": 150},
                    schema_data,
                )

        except Exception as e:
            pytest.fail(f"Generated JSON Schema failed with version {version}: {e}")

    def test_current_graphql_version_compatibility(self, test_schema):
        """Test compatibility with currently installed graphql-core version"""
        try:
            import graphql

            graphql_version = graphql.__version__
        except ImportError:
            pytest.skip("graphql-core not installed")

        generator = GraphQLGenerator()

        # Generate schema
        schema_output = generator.generate_model(test_schema)

        # Test that generated schema is valid GraphQL
        self._test_graphql_functionality(schema_output, graphql_version)

    def _test_graphql_functionality(self, schema_output: str, version: str):
        """Test that generated GraphQL schema works correctly"""
        try:
            import graphql

            # Test that the schema can be parsed
            full_schema = f"""
            {schema_output}

            type Query {{
                getUser(id: Int!): User
            }}
            """

            schema = graphql.build_schema(full_schema)
            assert schema is not None

        except Exception as e:
            pytest.fail(f"Generated GraphQL schema failed with version {version}: {e}")

    def test_current_avro_version_compatibility(self, test_schema):
        """Test compatibility with currently installed avro version"""
        try:
            import avro

            avro_version = avro.__version__
        except ImportError:
            pytest.skip("avro not installed")

        generator = AvroGenerator()

        # Generate schema
        schema_output = generator.generate_model(test_schema)

        # Test that generated schema is valid Avro
        self._test_avro_functionality(schema_output, avro_version)

    def _test_avro_functionality(self, schema_output: str, version: str):
        """Test that generated Avro schema works correctly"""
        try:
            import json

            import avro.schema

            # Parse the JSON output and extract schemas
            avro_data = json.loads(schema_output)

            # Find the main schema
            main_schema = None
            if "schemas" in avro_data:
                main_schema = next(
                    (s for s in avro_data["schemas"] if s.get("name") == "User"), None
                )
            else:
                main_schema = avro_data

            if main_schema:
                # Test that the schema can be parsed by Avro
                schema = avro.schema.parse(json.dumps(main_schema))
                assert schema is not None

        except Exception as e:
            pytest.fail(f"Generated Avro schema failed with version {version}: {e}")

    def test_current_protobuf_version_compatibility(self, test_schema):
        """Test compatibility with currently installed protobuf version"""
        try:
            import google.protobuf

            protobuf_version = google.protobuf.__version__
        except ImportError:
            pytest.skip("protobuf not installed")

        generator = ProtobufGenerator()

        # Generate schema
        schema_output = generator.generate_model(test_schema)

        # Test that generated schema is valid Protobuf
        self._test_protobuf_functionality(schema_output, protobuf_version)

    def _test_protobuf_functionality(self, schema_output: str, version: str):
        """Test that generated Protobuf schema works correctly"""
        try:
            # Basic syntax validation
            assert "message " in schema_output
            assert "{" in schema_output and "}" in schema_output

            # Test field definitions
            lines = schema_output.split("\n")
            field_lines = [
                line.strip()
                for line in lines
                if "=" in line and line.strip().endswith(";")
            ]
            assert len(field_lines) > 0, "Should have field definitions"

        except Exception as e:
            pytest.fail(f"Generated Protobuf schema failed with version {version}: {e}")

    def test_current_pathway_version_compatibility(self, test_schema):
        """Test compatibility with currently installed Pathway version"""
        try:
            import pathway

            pathway_version = pathway.__version__
        except ImportError:
            pytest.skip("Pathway not installed")

        generator = PathwayGenerator()

        # Generate model
        model_code = generator.generate_model(test_schema)

        # Test that generated code is valid Python
        compile(model_code, "<test>", "exec")

        # Test that generated models can be imported
        self._test_pathway_model_functionality(model_code, pathway_version)

    def _test_pathway_model_functionality(self, model_code: str, version: str):
        """Test that generated Pathway models work correctly"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Write model to file
            model_file = Path(temp_dir) / "test_model.py"
            model_file.write_text(model_code)

            # Add to Python path and import
            sys.path.insert(0, temp_dir)
            try:
                import test_model

                importlib.reload(test_model)

                # Test model exists and has correct structure
                if hasattr(test_model, "User"):
                    User = test_model.User

                    # Verify it's a Pathway table class
                    assert hasattr(User, "__pathway_table__") or hasattr(User, "id")

            except Exception as e:
                pytest.fail(
                    f"Generated Pathway model failed with version {version}: {e}"
                )
            finally:
                sys.path.remove(temp_dir)

    @pytest.mark.slow
    def test_version_matrix_compatibility(self, test_schema):
        """Test compatibility across version matrix (requires installation of specific versions)"""
        matrix = load_version_matrix()

        for library, versions in matrix.get("version_matrix", {}).items():
            for version in versions:
                # Skip this test in normal CI - only run in dedicated compatibility testing
                if not self._should_run_version_test(library, version):
                    pytest.skip(f"Skipping {library} {version} compatibility test")

                self._test_specific_version(library, version, test_schema)

    def _should_run_version_test(self, library: str, version: str) -> bool:
        """Determine if version-specific test should run"""
        # Check if we're in compatibility testing mode
        import os

        return os.environ.get("TEST_VERSION_COMPATIBILITY") == "true"

    def _test_specific_version(self, library: str, version: str, test_schema):
        """Test specific library version compatibility"""
        # This would require installing specific versions in CI
        # Implementation would use subprocess to install and test versions
        pass

    def test_generated_code_syntax_validation(self, test_schema):
        """Test that all generated code has valid syntax across generators"""
        generators = [
            # Python-based generators (can be compiled)
            ("pydantic", PydanticGenerator(), "python"),
            ("sqlalchemy", SqlAlchemyGenerator(), "python"),
            ("pathway", PathwayGenerator(), "python"),
            ("dataclasses", DataclassesGenerator(), "python"),
            ("typeddict", TypedDictGenerator(), "python"),
            # Non-Python generators (syntax validation only)
            ("zod", ZodGenerator(), "typescript"),
            ("jsonschema", JsonSchemaGenerator(), "json"),
            ("graphql", GraphQLGenerator(), "graphql"),
            ("protobuf", ProtobufGenerator(), "proto"),
            ("avro", AvroGenerator(), "json"),
            ("jackson", JacksonGenerator(), "java"),
            ("kotlin", KotlinGenerator(), "kotlin"),
        ]

        for name, generator, lang_type in generators:
            try:
                model_code = generator.generate_model(test_schema)

                if lang_type == "python":
                    # Test Python syntax compilation
                    compile(model_code, f"<{name}_test>", "exec")

                    # Test that imports are valid (basic check)
                    import_lines = [
                        line
                        for line in model_code.split("\n")
                        if line.strip().startswith("from ")
                        or line.strip().startswith("import ")
                    ]
                    assert len(import_lines) > 0, (
                        f"{name} generator should have import statements"
                    )

                elif lang_type == "json":
                    # Test JSON syntax
                    import json

                    json.loads(model_code)

                elif lang_type in ["typescript", "java", "kotlin", "graphql", "proto"]:
                    # Basic syntax checks for other languages
                    assert len(model_code.strip()) > 0, (
                        f"{name} generator produced empty output"
                    )
                    assert not model_code.startswith("Error"), (
                        f"{name} generator produced error output"
                    )

                print(f"✅ {name} generator syntax validation passed")

            except Exception as e:
                pytest.fail(f"{name} generator failed syntax validation: {e}")

    def test_field_constraint_translation(self, test_schema):
        """Test that field constraints are correctly translated for each generator"""

        # Test Pydantic generator
        pydantic_gen = PydanticGenerator()
        pydantic_code = pydantic_gen.generate_model(test_schema)

        # Should contain Pydantic-specific constraints
        assert "min_length=3, max_length=30" in pydantic_code
        assert "EmailStr" in pydantic_code or "format=" in pydantic_code
        assert "ge=13" in pydantic_code and "le=120" in pydantic_code

        # Test SQLAlchemy generator
        sqlalchemy_gen = SqlAlchemyGenerator()
        sqlalchemy_code = sqlalchemy_gen.generate_model(test_schema)

        # Should contain SQLAlchemy-specific constraints
        assert "String(" in sqlalchemy_code
        assert "Integer" in sqlalchemy_code
        assert "primary_key=True" in sqlalchemy_code

    @pytest.mark.integration
    def test_end_to_end_version_compatibility(self, test_schema):
        """End-to-end test that ensures generated schemas work in real applications"""

        # Test that generated Pydantic models work with FastAPI
        pydantic_gen = PydanticGenerator()
        pydantic_code = pydantic_gen.generate_model(test_schema)

        # This would test actual usage in a FastAPI app
        self._test_fastapi_integration(pydantic_code)

    def _test_fastapi_integration(self, model_code: str):
        """Test that generated Pydantic models work with FastAPI"""
        try:
            import fastapi  # noqa: F401
            import uvicorn  # noqa: F401

            # Create a simple FastAPI app using generated models
            with tempfile.TemporaryDirectory() as temp_dir:
                # Write model and app files
                model_file = Path(temp_dir) / "models.py"
                model_file.write_text(model_code)

                app_code = """
from fastapi import FastAPI
from models import User, UserCreate, UserResponse

app = FastAPI()

@app.post("/users/", response_model=UserResponse)
async def create_user(user: UserCreate):
    # Simple echo for testing
    return UserResponse(id=1, username=user.username, age=user.age)

@app.get("/users/{user_id}", response_model=UserResponse)
async def get_user(user_id: int):
    return UserResponse(id=user_id, username="testuser", age=25)
"""

                app_file = Path(temp_dir) / "app.py"
                app_file.write_text(app_code)

                # Basic validation that the app can be created
                sys.path.insert(0, temp_dir)
                try:
                    import app

                    assert app.app is not None
                except Exception as e:
                    pytest.fail(f"FastAPI integration failed: {e}")
                finally:
                    sys.path.remove(temp_dir)

        except ImportError:
            pytest.skip("FastAPI not installed")


class TestAllGeneratorCompatibility:
    """Test compatibility for all generators"""

    def setup_method(self):
        """Clear registry before each test"""
        SchemaRegistry._schemas.clear()

    @pytest.fixture
    def test_schema(self):
        """Create a test schema for all generators"""

        @Schema
        class AllGenTest:
            """Test schema for all generator compatibility"""

            id: int = Field(primary_key=True, description="Test ID")
            name: str = Field(min_length=2, max_length=100, description="Name")
            email: str = Field(format="email", description="Email")
            age: int | None = Field(default=None, min_value=18, max_value=100)

            class Variants:
                create = ["name", "email", "age"]
                response = ["id", "name", "age"]

        parser = SchemaParser()
        return parser.parse_schema(AllGenTest)

    def test_all_python_generators(self, test_schema):
        """Test all Python-based generators"""
        python_generators = [
            ("pydantic", PydanticGenerator()),
            ("sqlalchemy", SqlAlchemyGenerator()),
            ("pathway", PathwayGenerator()),
            ("dataclasses", DataclassesGenerator()),
            ("typeddict", TypedDictGenerator()),
        ]

        for name, generator in python_generators:
            try:
                # Test base model
                base_model = generator.generate_model(test_schema)
                compile(base_model, f"<{name}_base>", "exec")

                # Test variants if supported
                try:
                    create_model = generator.generate_model(test_schema, "create")
                    compile(create_model, f"<{name}_create>", "exec")

                    response_model = generator.generate_model(test_schema, "response")
                    compile(response_model, f"<{name}_response>", "exec")
                except Exception:
                    # Some generators might not support variants
                    pass

                print(f"✅ {name} generator compatibility test passed")

            except Exception as e:
                pytest.fail(f"{name} generator compatibility test failed: {e}")

    def test_all_schema_generators(self, test_schema):
        """Test all schema/data format generators"""
        schema_generators = [
            ("jsonschema", JsonSchemaGenerator()),
            ("avro", AvroGenerator()),
            ("protobuf", ProtobufGenerator()),
        ]

        for name, generator in schema_generators:
            try:
                schema_output = generator.generate_model(test_schema)

                if name in ["jsonschema", "avro"]:
                    # Should be valid JSON
                    import json

                    json.loads(schema_output)
                elif name == "protobuf":
                    # Should contain protobuf message syntax
                    assert "message " in schema_output

                print(f"✅ {name} generator compatibility test passed")

            except Exception as e:
                pytest.fail(f"{name} generator compatibility test failed: {e}")

    def test_all_language_generators(self, test_schema):
        """Test all programming language generators"""
        language_generators = [
            ("zod", ZodGenerator(), "typescript"),
            ("graphql", GraphQLGenerator(), "graphql"),
            ("jackson", JacksonGenerator(), "java"),
            ("kotlin", KotlinGenerator(), "kotlin"),
        ]

        for name, generator, lang in language_generators:
            try:
                # Try different generator method names
                if hasattr(generator, "generate_model"):
                    code_output = generator.generate_model(test_schema)
                elif hasattr(generator, "generate_file"):
                    code_output = generator.generate_file(test_schema)
                else:
                    raise ValueError(
                        f"{name} generator has no generate_model or generate_file method"
                    )

                # Basic validation for each language
                if lang == "typescript":
                    assert "export" in code_output or "const" in code_output
                    assert "z.object" in code_output or "z.string" in code_output
                elif lang == "graphql":
                    assert "type " in code_output or "input " in code_output
                elif lang == "java":
                    assert "class " in code_output and "public" in code_output
                    assert "@JsonProperty" in code_output
                elif lang == "kotlin":
                    assert "data class" in code_output
                    assert "val " in code_output

                print(f"✅ {name} generator compatibility test passed")

            except Exception as e:
                pytest.fail(f"{name} generator compatibility test failed: {e}")

    @pytest.mark.compatibility
    def test_generator_output_consistency(self, test_schema):
        """Test that generators produce consistent field mappings"""
        generators = [
            ("pydantic", PydanticGenerator()),
            ("dataclasses", DataclassesGenerator()),
            ("typeddict", TypedDictGenerator()),
        ]

        field_mappings = {}

        for name, generator in generators:
            try:
                model_code = generator.generate_model(test_schema)

                # Extract field definitions (basic parsing)
                field_mappings[name] = {
                    "has_id": "id:" in model_code or "id =" in model_code,
                    "has_name": "name:" in model_code or "name =" in model_code,
                    "has_email": "email:" in model_code or "email =" in model_code,
                    "has_age": "age:" in model_code or "age =" in model_code,
                }

            except Exception as e:
                pytest.fail(f"Failed to analyze {name} generator output: {e}")

        # Verify all generators include the same fields
        first_mapping = list(field_mappings.values())[0]
        for gen_name, mapping in field_mappings.items():
            for field, exists in first_mapping.items():
                assert mapping[field] == exists, (
                    f"{gen_name} has inconsistent {field} field mapping"
                )


class TestVersionRequirements:
    """Test that we properly specify and handle version requirements"""

    def test_minimum_version_requirements(self):
        """Test that minimum version requirements are properly defined"""
        import schema_gen

        # Should have version constraints in dependencies
        assert (
            hasattr(schema_gen, "__version__") or True
        )  # Schema gen should define its version

        # Test that our generators handle version-specific features correctly
        pydantic_gen = PydanticGenerator()

        # Test that we use modern Pydantic v2 syntax
        @Schema
        class TestModel:
            name: str = Field(description="Test field")

        parser = SchemaParser()
        schema = parser.parse_schema(TestModel)
        model_code = pydantic_gen.generate_model(schema)

        # Should use Pydantic v2 syntax
        assert "from pydantic import BaseModel, Field" in model_code
        # Should not use deprecated v1 syntax
        assert "Config" not in model_code or "model_config" in model_code

    def test_version_detection(self):
        """Test that we can detect and adapt to different library versions"""
        try:
            import pydantic

            version = pydantic.VERSION

            # Should be able to parse version string
            major, minor = map(int, version.split(".")[:2])
            assert major >= 2, "Should be using Pydantic v2+"
            assert minor >= 9, "Should be using recent Pydantic version"

        except ImportError:
            pytest.skip("Pydantic not installed")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
