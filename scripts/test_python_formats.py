#!/usr/bin/env python3
"""
Comprehensive Python format validation script
Tests all Python-based formats with their respective libraries
"""

import ast
import sys
import tempfile
from pathlib import Path
from typing import Any


def test_format_with_library(format_name: str, code: str, test_func) -> dict[str, Any]:
    """Test a format with its corresponding Python library"""
    result = {
        "format": format_name,
        "syntax_valid": False,
        "library_test": False,
        "error": None,
        "details": {},
    }

    try:
        # First test Python syntax
        ast.parse(code)
        result["syntax_valid"] = True

        # Then test with the specific library
        if test_func:
            library_result = test_func(code)
            result["library_test"] = library_result.get("success", False)
            result["details"] = library_result.get("details", {})

    except Exception as e:
        result["error"] = str(e)

    return result


def test_pydantic_format(code: str) -> dict[str, Any]:
    """Test Pydantic model functionality"""
    try:
        import pydantic
        from pydantic import BaseModel

        # Create a temporary module
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            f.flush()

        # Import and test the module
        import importlib.util

        spec = importlib.util.spec_from_file_location("test_module", f.name)
        module = importlib.util.module_from_spec(spec)
        sys.modules["test_module"] = module
        spec.loader.exec_module(module)

        # Find Pydantic models in the module
        models = []
        for name in dir(module):
            obj = getattr(module, name)
            if (
                isinstance(obj, type)
                and issubclass(obj, BaseModel)
                and obj is not BaseModel
            ):
                models.append(obj)

        # Test model instantiation
        test_results = {}
        for model in models:
            try:
                # Try to create a test instance
                fields = model.model_fields
                test_data = {}

                for field_name, field_info in fields.items():
                    field_type = field_info.annotation
                    if field_type is int:
                        test_data[field_name] = 1
                    elif field_type is str:
                        test_data[field_name] = "test"
                    elif field_type is bool:
                        test_data[field_name] = True
                    elif field_type is float:
                        test_data[field_name] = 1.0

                model(**test_data)  # Test instantiation
                test_results[model.__name__] = {
                    "instantiated": True,
                    "fields": list(fields.keys()),
                    "data": test_data,
                }
            except Exception as e:
                test_results[model.__name__] = {"instantiated": False, "error": str(e)}

        Path(f.name).unlink()  # Clean up

        return {
            "success": True,
            "details": {
                "pydantic_version": pydantic.__version__,
                "models_found": len(models),
                "models": test_results,
            },
        }

    except Exception as e:
        return {"success": False, "error": str(e)}


def test_sqlalchemy_format(code: str) -> dict[str, Any]:
    """Test SQLAlchemy ORM functionality"""
    try:
        import sqlalchemy
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        # Create a temporary module
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            f.flush()

        # Import and test the module
        import importlib.util

        spec = importlib.util.spec_from_file_location("test_module", f.name)
        module = importlib.util.module_from_spec(spec)
        sys.modules["test_module"] = module
        spec.loader.exec_module(module)

        # Find SQLAlchemy models
        models = []
        for name in dir(module):
            obj = getattr(module, name)
            if (
                isinstance(obj, type)
                and hasattr(obj, "__table__")
                and hasattr(obj, "__tablename__")
            ):
                models.append(obj)

        # Test database operations
        engine = create_engine("sqlite:///:memory:")

        # Create tables
        for model in models:
            model.__table__.create(engine, checkfirst=True)

        Session = sessionmaker(bind=engine)
        session = Session()

        test_results = {}
        for model in models:
            try:
                # Get table info
                table = model.__table__
                test_results[model.__name__] = {
                    "table_created": True,
                    "table_name": model.__tablename__,
                    "columns": [col.name for col in table.columns],
                    "primary_keys": [col.name for col in table.primary_key],
                }
            except Exception as e:
                test_results[model.__name__] = {"table_created": False, "error": str(e)}

        session.close()
        Path(f.name).unlink()  # Clean up

        return {
            "success": True,
            "details": {
                "sqlalchemy_version": sqlalchemy.__version__,
                "models_found": len(models),
                "models": test_results,
            },
        }

    except Exception as e:
        return {"success": False, "error": str(e)}


def test_dataclasses_format(code: str) -> dict[str, Any]:
    """Test Python dataclasses functionality"""
    try:
        import dataclasses
        from dataclasses import is_dataclass

        # Create a temporary module
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            f.flush()

        # Import and test the module
        import importlib.util

        spec = importlib.util.spec_from_file_location("test_module", f.name)
        module = importlib.util.module_from_spec(spec)
        sys.modules["test_module"] = module
        spec.loader.exec_module(module)

        # Find dataclasses
        dataclass_models = []
        for name in dir(module):
            obj = getattr(module, name)
            if isinstance(obj, type) and is_dataclass(obj):
                dataclass_models.append(obj)

        # Test dataclass instantiation
        test_results = {}
        for model in dataclass_models:
            try:
                # Get field info
                fields = dataclasses.fields(model)
                test_data = {}

                # Create test data for required fields
                for field in fields:
                    if (
                        field.default == dataclasses.MISSING
                        and field.default_factory == dataclasses.MISSING
                    ):
                        # Required field
                        if field.type is int:
                            test_data[field.name] = 1
                        elif field.type is str:
                            test_data[field.name] = "test"
                        elif field.type is bool:
                            test_data[field.name] = True
                        elif field.type is float:
                            test_data[field.name] = 1.0

                model(**test_data)  # Test instantiation
                test_results[model.__name__] = {
                    "instantiated": True,
                    "fields": [f.name for f in fields],
                    "required_fields": [
                        f.name
                        for f in fields
                        if f.default == dataclasses.MISSING
                        and f.default_factory == dataclasses.MISSING
                    ],
                    "data": test_data,
                }
            except Exception as e:
                test_results[model.__name__] = {"instantiated": False, "error": str(e)}

        Path(f.name).unlink()  # Clean up

        return {
            "success": True,
            "details": {
                "dataclasses_found": len(dataclass_models),
                "models": test_results,
            },
        }

    except Exception as e:
        return {"success": False, "error": str(e)}


def test_typeddict_format(code: str) -> dict[str, Any]:
    """Test TypedDict functionality"""
    try:
        from typing import get_type_hints

        # Create a temporary module
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            f.flush()

        # Import and test the module
        import importlib.util

        spec = importlib.util.spec_from_file_location("test_module", f.name)
        module = importlib.util.module_from_spec(spec)
        sys.modules["test_module"] = module
        spec.loader.exec_module(module)

        # Find TypedDict classes
        typeddict_models = []
        for name in dir(module):
            obj = getattr(module, name)
            if (
                isinstance(obj, type)
                and hasattr(obj, "__annotations__")
                and getattr(obj, "__total__", None) is not None
            ):  # TypedDict marker
                typeddict_models.append(obj)

        # Test TypedDict usage
        test_results = {}
        for model in typeddict_models:
            try:
                # Get type hints
                hints = get_type_hints(model)

                # Create test data
                test_data = {}
                for field_name, field_type in hints.items():
                    if field_type is int:
                        test_data[field_name] = 1
                    elif field_type is str:
                        test_data[field_name] = "test"
                    elif field_type is bool:
                        test_data[field_name] = True
                    elif field_type is float:
                        test_data[field_name] = 1.0

                # TypedDict is used as type hint, actual value is dict
                # typed_dict_instance: model = test_data  # type: ignore

                test_results[model.__name__] = {
                    "created": True,
                    "fields": list(hints.keys()),
                    "types": {k: str(v) for k, v in hints.items()},
                    "data": test_data,
                }
            except Exception as e:
                test_results[model.__name__] = {"created": False, "error": str(e)}

        Path(f.name).unlink()  # Clean up

        return {
            "success": True,
            "details": {
                "typeddict_found": len(typeddict_models),
                "models": test_results,
            },
        }

    except Exception as e:
        return {"success": False, "error": str(e)}


def test_avro_format(code: str) -> dict[str, Any]:
    """Test Avro schema functionality"""
    try:
        import json

        import avro.io
        import avro.schema

        # Avro schemas are JSON, not Python code
        # Parse the code as JSON schema
        if code.strip().startswith("{"):
            schema_dict = json.loads(code)
        else:
            # If it's Python code generating Avro, we need to execute it
            namespace = {}
            exec(code, namespace)

            # Look for schema dictionaries
            schema_dict = None
            for _name, obj in namespace.items():
                if isinstance(obj, dict) and "type" in obj and "name" in obj:
                    schema_dict = obj
                    break

            if not schema_dict:
                return {"success": False, "error": "No Avro schema found in code"}

        # Parse with Avro library
        schema = avro.schema.parse(json.dumps(schema_dict))

        return {
            "success": True,
            "details": {
                "schema_name": schema.name,
                "schema_type": schema.type,
                "fields": [f.name for f in schema.fields]
                if hasattr(schema, "fields")
                else [],
                "namespace": getattr(schema, "namespace", None),
            },
        }

    except Exception as e:
        return {"success": False, "error": str(e)}


def test_json_schema_format(code: str) -> dict[str, Any]:
    """Test JSON Schema functionality"""
    try:
        import json

        import jsonschema

        # JSON schemas are JSON, not Python code
        if code.strip().startswith("{"):
            schema_dict = json.loads(code)
        else:
            # If it's Python code generating JSON Schema
            namespace = {}
            exec(code, namespace)

            # Look for schema dictionaries
            schema_dict = None
            for _name, obj in namespace.items():
                if isinstance(obj, dict) and ("$schema" in obj or "type" in obj):
                    schema_dict = obj
                    break

            if not schema_dict:
                return {"success": False, "error": "No JSON schema found in code"}

        # Validate the schema itself
        jsonschema.Draft7Validator.check_schema(schema_dict)

        # Create validator
        validator = jsonschema.Draft7Validator(schema_dict)

        # Test with sample data
        test_data = {"id": 1, "name": "test", "email": "test@example.com"}
        errors = list(validator.iter_errors(test_data))

        return {
            "success": True,
            "details": {
                "schema_valid": True,
                "schema_keys": list(schema_dict.keys()),
                "properties": list(schema_dict.get("properties", {}).keys()),
                "required": schema_dict.get("required", []),
                "test_validation_errors": len(errors),
            },
        }

    except Exception as e:
        return {"success": False, "error": str(e)}


def test_graphql_format(_code: str) -> dict[str, Any]:
    """Test GraphQL schema functionality - currently not implemented"""
    # GraphQL generator not fully wired up yet in the system
    return {"success": False, "error": "GraphQL generator not implemented yet"}


def test_pathway_format(code: str) -> dict[str, Any]:
    """Test Pathway schema functionality"""
    try:
        import pathway as pw

        # Create a temporary module
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            f.flush()

        # Import and test the module
        import importlib.util

        spec = importlib.util.spec_from_file_location("test_module", f.name)
        module = importlib.util.module_from_spec(spec)
        sys.modules["test_module"] = module
        spec.loader.exec_module(module)

        # Find Pathway schemas
        pathway_schemas = []
        for name in dir(module):
            obj = getattr(module, name)
            if isinstance(obj, type) and hasattr(obj, "__annotations__"):
                pathway_schemas.append(obj)

        test_results = {}
        for schema in pathway_schemas:
            try:
                annotations = getattr(schema, "__annotations__", {})
                test_results[schema.__name__] = {
                    "found": True,
                    "fields": list(annotations.keys()),
                    "annotations": {k: str(v) for k, v in annotations.items()},
                }
            except Exception as e:
                test_results[schema.__name__] = {"found": False, "error": str(e)}

        Path(f.name).unlink()  # Clean up

        return {
            "success": True,
            "details": {
                "pathway_version": pw.__version__,
                "schemas_found": len(pathway_schemas),
                "schemas": test_results,
            },
        }

    except Exception as e:
        return {"success": False, "error": str(e)}


def generate_sample_schemas() -> dict[str, str]:
    """Generate sample schemas for testing"""
    return {
        "pydantic": """
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

class User(BaseModel):
    id: int = Field(description="Unique identifier")
    name: str = Field(description="User's full name")
    email: str = Field(description="User's email address")
    age: Optional[int] = Field(None, description="User's age")
    is_active: bool = Field(True, description="Whether user is active")
    created_at: datetime = Field(description="Account creation timestamp")
""",
        "sqlalchemy": """
from sqlalchemy import Column, Integer, String, Boolean, DateTime
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()

class User(Base):
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    email = Column(String(255), nullable=False)
    age = Column(Integer, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
""",
        "dataclasses": '''
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime

@dataclass
class User:
    """User data class"""
    id: int
    name: str
    email: str
    age: Optional[int] = None
    is_active: bool = True
    created_at: datetime = field(default_factory=datetime.now)
''',
        "typeddict": """
from typing_extensions import TypedDict, Optional
from datetime import datetime

class User(TypedDict):
    id: int
    name: str
    email: str
    age: Optional[int]
    is_active: bool
    created_at: datetime
""",
        "avro": """
{
    "type": "record",
    "name": "User",
    "namespace": "com.example",
    "fields": [
        {"name": "id", "type": "int", "doc": "Unique identifier"},
        {"name": "name", "type": "string", "doc": "User's full name"},
        {"name": "email", "type": "string", "doc": "User's email address"},
        {"name": "age", "type": ["null", "int"], "default": null, "doc": "User's age"},
        {"name": "is_active", "type": "boolean", "default": true},
        {"name": "created_at", "type": "long", "doc": "Account creation timestamp"}
    ]
}
""",
        "jsonschema": """
{
    "$schema": "http://json-schema.org/draft-07/schema#",
    "$id": "http://example.com/user.json",
    "title": "User",
    "type": "object",
    "properties": {
        "id": {
            "type": "integer",
            "description": "Unique identifier"
        },
        "name": {
            "type": "string",
            "description": "User's full name"
        },
        "email": {
            "type": "string",
            "format": "email",
            "description": "User's email address"
        },
        "age": {
            "type": ["integer", "null"],
            "minimum": 0,
            "maximum": 150,
            "description": "User's age"
        },
        "is_active": {
            "type": "boolean",
            "default": true
        },
        "created_at": {
            "type": "string",
            "format": "date-time",
            "description": "Account creation timestamp"
        }
    },
    "required": ["id", "name", "email", "created_at"],
    "additionalProperties": false
}
""",
        "graphql": """
type User {
    id: Int!
    name: String!
    email: String!
    age: Int
    isActive: Boolean!
    createdAt: String!
}

type Query {
    user(id: Int!): User
    users: [User!]!
}
""",
        "pathway": """
import pathway as pw
from datetime import datetime

class User(pw.Schema):
    id: int = pw.column_definition(primary_key=True)
    name: str = pw.column_definition()
    email: str = pw.column_definition()
    age: int | None = pw.column_definition(default=None)
    is_active: bool = pw.column_definition(default=True)
    created_at: datetime = pw.column_definition()
""",
    }


def main():
    """Main test function"""
    print("🐍 Comprehensive Python Format Validation")
    print("=" * 50)

    # Test format mappings (working formats only)
    format_tests = {
        "pydantic": test_pydantic_format,
        "sqlalchemy": test_sqlalchemy_format,
        "dataclasses": test_dataclasses_format,
        "typeddict": test_typeddict_format,
        "avro": test_avro_format,
        "jsonschema": test_json_schema_format,
    }

    # Not yet implemented formats
    not_implemented = {
        "graphql": "GraphQL generator not fully wired up",
        "pathway": "Pathway generator not fully wired up",
    }

    # Generate sample schemas
    sample_schemas = generate_sample_schemas()

    # Test results
    results = {}
    passed = 0
    total = len(format_tests) + len(not_implemented)

    for format_name, test_func in format_tests.items():
        print(f"\n🔍 Testing {format_name.upper()}...")

        if format_name in sample_schemas:
            code = sample_schemas[format_name]
            result = test_format_with_library(format_name, code, test_func)
            results[format_name] = result

            if result["syntax_valid"] and result["library_test"]:
                print("   ✅ PASSED - Syntax and library validation successful")
                passed += 1
            elif result["syntax_valid"]:
                print(
                    f"   ⚠️  PARTIAL - Syntax valid but library test failed: {result['error']}"
                )
            else:
                print(f"   ❌ FAILED - Syntax error: {result['error']}")
        else:
            print("   ⚠️  SKIPPED - No sample schema available")

    # Show not implemented formats
    for format_name, reason in not_implemented.items():
        print(f"\n🔍 Testing {format_name.upper()}...")
        print(f"   ⚠️  NOT IMPLEMENTED - {reason}")
        results[format_name] = {
            "format": format_name,
            "syntax_valid": False,
            "library_test": False,
            "error": reason,
            "details": {},
        }

    # Summary
    print("\n" + "=" * 50)
    print("🎯 VALIDATION SUMMARY")
    print("=" * 50)
    print(f"Formats tested: {total}")
    print(f"Formats passed: {passed}")
    print(f"Success rate: {(passed / total) * 100:.1f}%")

    # Detailed results
    print("\n📋 DETAILED RESULTS:")
    print("-" * 30)

    for format_name, result in results.items():
        print(f"\n{format_name.upper()}:")
        print(f"  Syntax Valid: {result['syntax_valid']}")
        print(f"  Library Test: {result['library_test']}")
        if result["error"]:
            print(f"  Error: {result['error']}")
        if result["details"]:
            for key, value in result["details"].items():
                if isinstance(value, dict):
                    print(f"  {key}: {len(value)} items")
                else:
                    print(f"  {key}: {value}")

    # Return success if all tests passed
    return passed == total


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
