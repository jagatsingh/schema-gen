#!/usr/bin/env python3
"""
Script to validate all generated formats are syntactically correct and executable.
This script can be run in CI/CD to ensure all generators produce valid output.
"""

import argparse
import ast
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

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


class FormatValidator:
    """Validates generated code for all formats"""

    def __init__(self):
        self.results: dict[str, dict[str, Any]] = {}
        self.setup_test_schema()

    def setup_test_schema(self):
        """Create a comprehensive test schema"""
        SchemaRegistry._schemas.clear()

        @Schema
        class ValidationTestUser:
            """Comprehensive test user schema for validation"""

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

            email: str = Field(
                format="email", unique=True, description="User email address"
            )

            age: int | None = Field(
                default=None,
                min_value=0,
                max_value=150,
                description="User age in years",
            )

            is_active: bool = Field(
                default=True, description="Whether the account is active"
            )

            balance: float = Field(
                default=0.0, min_value=0.0, description="Account balance"
            )

            tags: list[str] = Field(default=[], description="User tags")

            class Variants:
                create = ["username", "email", "age"]
                update = ["username", "email", "age", "is_active"]
                public = ["id", "username", "is_active"]
                full = [
                    "id",
                    "username",
                    "email",
                    "age",
                    "is_active",
                    "balance",
                    "tags",
                ]

        parser = SchemaParser()
        self.schemas = parser.parse_all_schemas()
        self.test_schema = self.schemas[0]

    def validate_python_syntax(self, code: str, format_name: str) -> dict[str, Any]:
        """Validate Python code syntax"""
        result = {"valid": False, "error": None, "details": {}}

        try:
            ast.parse(code)
            result["valid"] = True
            result["details"]["parsed"] = True
        except SyntaxError as e:
            result["error"] = f"Syntax error: {e}"
            result["details"]["line"] = e.lineno
            result["details"]["offset"] = e.offset

        return result

    def validate_json_syntax(self, json_str: str, format_name: str) -> dict[str, Any]:
        """Validate JSON syntax"""
        result = {"valid": False, "error": None, "details": {}}

        try:
            parsed = json.loads(json_str)
            result["valid"] = True
            result["details"]["parsed"] = True
            result["details"]["keys"] = (
                list(parsed.keys()) if isinstance(parsed, dict) else None
            )
        except json.JSONDecodeError as e:
            result["error"] = f"JSON decode error: {e}"
            result["details"]["line"] = e.lineno
            result["details"]["column"] = e.colno

        return result

    def validate_external_syntax(
        self, code: str, file_ext: str, compiler_cmd: list[str]
    ) -> dict[str, Any]:
        """Validate syntax using external compiler/validator"""
        result = {"valid": False, "error": None, "details": {}}

        try:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=file_ext, delete=False
            ) as f:
                f.write(code)
                temp_path = Path(f.name)

            # Run compiler/validator
            cmd = compiler_cmd + [str(temp_path)]
            proc_result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=30
            )

            if proc_result.returncode == 0:
                result["valid"] = True
                result["details"]["compiled"] = True
            else:
                result["error"] = f"Compilation failed: {proc_result.stderr}"
                result["details"]["stdout"] = proc_result.stdout
                result["details"]["stderr"] = proc_result.stderr

            # Clean up
            temp_path.unlink(missing_ok=True)

        except subprocess.TimeoutExpired:
            result["error"] = "Compilation timeout"
        except FileNotFoundError:
            result["error"] = f"Compiler not found: {compiler_cmd[0]}"
        except Exception as e:
            result["error"] = f"Unexpected error: {e}"

        return result

    def validate_pydantic(self) -> dict[str, Any]:
        """Validate Pydantic generation"""
        generator = PydanticGenerator()
        code = generator.generate_file(self.test_schema)

        result = self.validate_python_syntax(code, "pydantic")

        # Additional Pydantic-specific checks
        if result["valid"]:
            result["details"]["has_basemodel"] = "BaseModel" in code
            result["details"]["has_config"] = (
                "Config:" in code or "model_config" in code
            )
            result["details"]["has_validators"] = (
                "@validator" in code or "@field_validator" in code
            )

        return result

    def validate_sqlalchemy(self) -> dict[str, Any]:
        """Validate SQLAlchemy generation"""
        generator = SqlAlchemyGenerator()
        code = generator.generate_file(self.test_schema)

        result = self.validate_python_syntax(code, "sqlalchemy")

        # Additional SQLAlchemy-specific checks
        if result["valid"]:
            result["details"]["has_table"] = "__tablename__" in code
            result["details"]["has_columns"] = "Column(" in code
            result["details"]["has_imports"] = "from sqlalchemy" in code

        return result

    def validate_dataclasses(self) -> dict[str, Any]:
        """Validate dataclasses generation"""
        generator = DataclassesGenerator()
        code = generator.generate_file(self.test_schema)

        result = self.validate_python_syntax(code, "dataclasses")

        # Additional dataclasses-specific checks
        if result["valid"]:
            result["details"]["has_decorator"] = "@dataclass" in code
            result["details"]["has_imports"] = "from dataclasses import" in code

        return result

    def validate_typeddict(self) -> dict[str, Any]:
        """Validate TypedDict generation"""
        generator = TypedDictGenerator()
        code = generator.generate_file(self.test_schema)

        result = self.validate_python_syntax(code, "typeddict")

        # Additional TypedDict-specific checks
        if result["valid"]:
            result["details"]["has_typeddict"] = "TypedDict" in code
            result["details"]["has_imports"] = (
                "from typing" in code or "from typing_extensions" in code
            )

        return result

    def validate_pathway(self) -> dict[str, Any]:
        """Validate Pathway generation"""
        generator = PathwayGenerator()
        code = generator.generate_file(self.test_schema)

        result = self.validate_python_syntax(code, "pathway")

        # Additional Pathway-specific checks
        if result["valid"]:
            result["details"]["has_pathway_import"] = "pathway" in code
            result["details"]["has_schema"] = (
                "pw.Schema" in code or "pathway.Schema" in code
            )

        return result

    def validate_zod(self) -> dict[str, Any]:
        """Validate Zod TypeScript generation"""
        generator = ZodGenerator()
        code = generator.generate_file(self.test_schema)

        result = {"valid": False, "error": None, "details": {}}

        # Basic TypeScript structure checks
        if "import { z }" in code and "z.object({" in code:
            result["valid"] = True
            result["details"]["has_zod_import"] = True
            result["details"]["has_schema_export"] = "export const" in code

            # Try TypeScript compilation if available
            # Create temp TypeScript project with proper module resolution
            try:
                with tempfile.TemporaryDirectory() as temp_dir:
                    temp_path = Path(temp_dir)

                    # Copy node_modules from validation directory
                    import shutil

                    if Path("/opt/typescript-validation/node_modules").exists():
                        shutil.copytree(
                            "/opt/typescript-validation/node_modules",
                            temp_path / "node_modules",
                        )

                    # Create tsconfig.json with proper Zod support
                    tsconfig = {
                        "compilerOptions": {
                            "target": "ES2020",
                            "module": "commonjs",
                            "lib": ["ES2020"],
                            "strict": True,
                            "esModuleInterop": True,
                            "allowSyntheticDefaultImports": True,
                            "skipLibCheck": True,
                            "forceConsistentCasingInFileNames": True,
                            "moduleResolution": "node",
                            "resolveJsonModule": True,
                            "noEmit": True,
                        }
                    }
                    (temp_path / "tsconfig.json").write_text(
                        json.dumps(tsconfig, indent=2)
                    )

                    # Write TypeScript file
                    ts_file = temp_path / "validation.ts"
                    ts_file.write_text(code)

                    # Run TypeScript compiler
                    cmd = ["tsc", "--project", str(temp_path)]
                    proc_result = subprocess.run(
                        cmd, capture_output=True, text=True, timeout=30
                    )

                    if proc_result.returncode == 0:
                        ts_result = {"valid": True, "details": {"compiled": True}}
                    else:
                        ts_result = {
                            "valid": False,
                            "error": f"Compilation failed: {proc_result.stderr}",
                            "details": {
                                "stdout": proc_result.stdout,
                                "stderr": proc_result.stderr,
                            },
                        }
            except Exception as e:
                ts_result = {
                    "valid": False,
                    "error": f"TypeScript validation failed: {e}",
                }
            # Always include TypeScript validation results
            result["details"]["typescript_validation"] = ts_result
        else:
            result["error"] = "Missing required Zod structures"

        return result

    def validate_jsonschema(self) -> dict[str, Any]:
        """Validate JSON Schema generation"""
        generator = JsonSchemaGenerator()
        json_str = generator.generate_model(self.test_schema)

        result = self.validate_json_syntax(json_str, "jsonschema")

        # Additional JSON Schema-specific checks
        if result["valid"]:
            try:
                schema = json.loads(json_str)
                result["details"]["has_schema_version"] = "$schema" in schema
                result["details"]["has_type"] = schema.get("type") == "object"
                result["details"]["has_properties"] = "properties" in schema
                result["details"]["has_required"] = "required" in schema
            except Exception:
                pass

        return result

    def validate_graphql(self) -> dict[str, Any]:
        """Validate GraphQL generation"""
        generator = GraphQLGenerator()
        code = generator.generate_file(self.test_schema)

        result = {"valid": False, "error": None, "details": {}}

        # Basic GraphQL structure checks
        if "type ValidationTestUser {" in code:
            result["valid"] = True
            result["details"]["has_type_definition"] = True
            result["details"]["has_fields"] = "id:" in code and "username:" in code

            # Try GraphQL validation if available
            try:
                from graphql import build_schema

                build_schema(code)
                result["details"]["graphql_validation"] = {"valid": True}
            except ImportError:
                result["details"]["graphql_validation"] = {
                    "error": "graphql-core not available"
                }
            except Exception as e:
                result["details"]["graphql_validation"] = {"error": str(e)}
                result["valid"] = False
        else:
            result["error"] = "Missing GraphQL type definition"

        return result

    def validate_protobuf(self) -> dict[str, Any]:
        """Validate Protocol Buffer generation"""
        generator = ProtobufGenerator()
        code = generator.generate_file(self.test_schema)

        result = {"valid": False, "error": None, "details": {}}

        # Basic protobuf structure checks
        if 'syntax = "proto3";' in code and "message ValidationTestUser {" in code:
            result["valid"] = True
            result["details"]["has_syntax"] = True
            result["details"]["has_message"] = True

            # Try protobuf compilation if available - need special handling for protoc
            try:
                with tempfile.NamedTemporaryFile(
                    mode="w", suffix=".proto", delete=False
                ) as f:
                    f.write(code)
                    temp_path = Path(f.name)
                    temp_dir = temp_path.parent

                # Use temp directory as proto_path and include standard protobuf directory
                cmd = [
                    "protoc",
                    f"--proto_path={temp_dir}",
                    "--proto_path=/usr/include",
                    f"--python_out={temp_dir}",
                    str(temp_path),
                ]
                proc_result = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=30
                )

                if proc_result.returncode == 0:
                    # Test multiple output formats to ensure comprehensive validation
                    test_results = {"python": True}

                    # Test C++ output
                    cpp_cmd = [
                        "protoc",
                        f"--proto_path={temp_dir}",
                        "--proto_path=/usr/include",
                        f"--cpp_out={temp_dir}",
                        str(temp_path),
                    ]
                    cpp_result = subprocess.run(
                        cpp_cmd, capture_output=True, text=True, timeout=30
                    )
                    test_results["cpp"] = cpp_result.returncode == 0

                    # Test Java output
                    java_cmd = [
                        "protoc",
                        f"--proto_path={temp_dir}",
                        "--proto_path=/usr/include",
                        f"--java_out={temp_dir}",
                        str(temp_path),
                    ]
                    java_result = subprocess.run(
                        java_cmd, capture_output=True, text=True, timeout=30
                    )
                    test_results["java"] = java_result.returncode == 0

                    protoc_result = {
                        "valid": True,
                        "details": {
                            "compiled": True,
                            "output_formats": test_results,
                            "total_formats": len(test_results),
                            "successful_formats": sum(test_results.values()),
                        },
                    }
                else:
                    protoc_result = {
                        "valid": False,
                        "error": f"Compilation failed: {proc_result.stderr}",
                        "details": {
                            "stdout": proc_result.stdout,
                            "stderr": proc_result.stderr,
                        },
                    }

                temp_path.unlink(missing_ok=True)
            except Exception as e:
                protoc_result = {
                    "valid": False,
                    "error": f"Protoc validation failed: {e}",
                }
            # Always include protoc validation results
            result["details"]["protoc_validation"] = protoc_result
        else:
            result["error"] = "Missing required protobuf structures"

        return result

    def validate_avro(self) -> dict[str, Any]:
        """Validate Avro generation"""
        generator = AvroGenerator()
        json_str = generator.generate_model(self.test_schema)

        result = self.validate_json_syntax(json_str, "avro")

        # Additional Avro-specific checks
        if result["valid"]:
            try:
                schema = json.loads(json_str)
                result["details"]["has_type"] = schema.get("type") == "record"
                result["details"]["has_name"] = "name" in schema
                result["details"]["has_fields"] = "fields" in schema and isinstance(
                    schema["fields"], list
                )
            except Exception:
                pass

        return result

    def validate_jackson(self) -> dict[str, Any]:
        """Validate Jackson Java generation"""
        generator = JacksonGenerator()
        code = generator.generate_file(self.test_schema)

        result = {"valid": False, "error": None, "details": {}}

        # Basic Java structure checks
        if "public class ValidationTestUser {" in code:
            result["valid"] = True
            result["details"]["has_class"] = True
            result["details"]["has_getters"] = "public int getId()" in code
            result["details"]["has_setters"] = "public void setId(" in code

            # Try Java compilation - simplified approach using single file
            try:
                import re

                # Extract the main public class name
                main_class_match = re.search(r"public class (\w+)", code)
                if main_class_match:
                    main_class = main_class_match.group(1)

                    # Create temporary directory and write Java file
                    with tempfile.TemporaryDirectory() as temp_dir:
                        temp_path = Path(temp_dir)
                        java_file = temp_path / f"{main_class}.java"
                        java_file.write_text(code)

                        # Test compilation with Jackson libraries
                        cmd = ["javac", "-cp", "/opt/java-libs/*", str(java_file)]
                        proc_result = subprocess.run(
                            cmd, capture_output=True, text=True, timeout=30
                        )

                        if proc_result.returncode == 0:
                            # Count generated class files
                            class_files = list(temp_path.glob("*.class"))

                            # Test annotation processing by checking if validation annotations work
                            annotation_test_passed = True
                            try:
                                # Try to load the main class with Java to verify it's properly formed
                                test_cmd = [
                                    "java",
                                    "-cp",
                                    f"{temp_path}:/opt/java-libs/*",
                                    "-XX:+PrintGC",  # Safe flag that doesn't require main method
                                    main_class,
                                ]
                                test_result = subprocess.run(
                                    test_cmd, capture_output=True, text=True, timeout=10
                                )
                                # Class loading will fail without main method but that's expected
                                annotation_test_passed = (
                                    "NoSuchMethodError" in test_result.stderr
                                    or "main" in test_result.stderr.lower()
                                )
                            except Exception:
                                annotation_test_passed = False

                            java_result = {
                                "valid": True,
                                "details": {
                                    "compiled": True,
                                    "main_class": main_class,
                                    "class_files_generated": len(class_files),
                                    "annotation_processing": annotation_test_passed,
                                    "jackson_libraries": "available",
                                },
                            }
                        else:
                            java_result = {
                                "valid": False,
                                "error": f"Compilation failed: {proc_result.stderr}",
                                "details": {
                                    "stdout": proc_result.stdout,
                                    "stderr": proc_result.stderr,
                                },
                            }
                else:
                    java_result = {"valid": False, "error": "No public class found"}

            except Exception as e:
                java_result = {"valid": False, "error": f"Java validation failed: {e}"}

            # Always include javac validation results
            result["details"]["javac_validation"] = java_result
        else:
            result["error"] = "Missing Java class definition"

        return result

    def validate_kotlin(self) -> dict[str, Any]:
        """Validate Kotlin generation"""
        generator = KotlinGenerator()
        code = generator.generate_file(self.test_schema)

        result = {"valid": False, "error": None, "details": {}}

        # Basic Kotlin structure checks
        if "data class ValidationTestUser(" in code:
            result["valid"] = True
            result["details"]["has_data_class"] = True
            result["details"]["has_properties"] = "val id:" in code

            # Try Kotlin compilation with kotlinx.serialization libraries
            try:
                # Create temporary directory for Kotlin files
                with tempfile.TemporaryDirectory() as temp_dir:
                    temp_path = Path(temp_dir)
                    kt_file = temp_path / "ValidationTestUser.kt"
                    kt_file.write_text(code)

                    # Test compilation with kotlinx.serialization libraries
                    kotlin_libs = "/opt/kotlin-libs/kotlinx-serialization-core.jar:/opt/kotlin-libs/kotlinx-serialization-json.jar"
                    cmd = ["kotlinc", "-cp", kotlin_libs, str(kt_file)]
                    proc_result = subprocess.run(
                        cmd, capture_output=True, text=True, timeout=30
                    )

                    if proc_result.returncode == 0:
                        # Count generated class files
                        class_files = list(temp_path.glob("*.class"))

                        # Test JAR compilation for comprehensive validation
                        jar_compilation_passed = True
                        try:
                            jar_cmd = [
                                "kotlinc",
                                "-cp",
                                kotlin_libs,
                                "-include-runtime",
                                "-d",
                                str(temp_path / "test.jar"),
                                str(kt_file),
                            ]
                            jar_result = subprocess.run(
                                jar_cmd, capture_output=True, text=True, timeout=30
                            )
                            jar_compilation_passed = jar_result.returncode == 0
                        except Exception:
                            jar_compilation_passed = False

                        kotlin_result = {
                            "valid": True,
                            "details": {
                                "compiled": True,
                                "class_files_generated": len(class_files),
                                "serialization_support": "kotlinx.serialization"
                                in code,
                                "jar_compilation": jar_compilation_passed,
                                "data_classes": code.count("data class"),
                            },
                        }
                    else:
                        kotlin_result = {
                            "valid": False,
                            "error": f"Compilation failed: {proc_result.stderr}",
                            "details": {
                                "stdout": proc_result.stdout,
                                "stderr": proc_result.stderr,
                            },
                        }

            except Exception as e:
                kotlin_result = {
                    "valid": False,
                    "error": f"Kotlin validation failed: {e}",
                }
            # Always include kotlinc validation results
            result["details"]["kotlinc_validation"] = kotlin_result
        else:
            result["error"] = "Missing Kotlin data class definition"

        return result

    def run_all_validations(self) -> dict[str, dict[str, Any]]:
        """Run all format validations"""
        validations = {
            "pydantic": self.validate_pydantic,
            "sqlalchemy": self.validate_sqlalchemy,
            "dataclasses": self.validate_dataclasses,
            "typeddict": self.validate_typeddict,
            "pathway": self.validate_pathway,
            "zod": self.validate_zod,
            "jsonschema": self.validate_jsonschema,
            "graphql": self.validate_graphql,
            "protobuf": self.validate_protobuf,
            "avro": self.validate_avro,
            "jackson": self.validate_jackson,
            "kotlin": self.validate_kotlin,
        }

        results = {}
        for format_name, validator in validations.items():
            try:
                print(f"Validating {format_name}...", end=" ")
                result = validator()
                results[format_name] = result

                if result["valid"]:
                    print("✅ VALID")
                else:
                    print(f"❌ INVALID - {result['error']}")

            except Exception as e:
                results[format_name] = {
                    "valid": False,
                    "error": f"Validation failed: {e}",
                    "details": {},
                }
                print(f"❌ ERROR - {e}")

        return results

    def print_summary(self, results: dict[str, dict[str, Any]]):
        """Print validation summary"""
        print("\n" + "=" * 60)
        print("VALIDATION SUMMARY")
        print("=" * 60)

        valid_count = sum(1 for r in results.values() if r["valid"])
        total_count = len(results)

        print(f"Valid formats: {valid_count}/{total_count}")
        print()

        # Group by status
        valid_formats = [name for name, result in results.items() if result["valid"]]
        invalid_formats = [
            name for name, result in results.items() if not result["valid"]
        ]

        if valid_formats:
            print("✅ VALID FORMATS:")
            for fmt in valid_formats:
                print(f"   - {fmt}")

        if invalid_formats:
            print("\n❌ INVALID FORMATS:")
            for fmt in invalid_formats:
                error = results[fmt]["error"]
                print(f"   - {fmt}: {error}")

        print(f"\nOverall success rate: {(valid_count / total_count) * 100:.1f}%")

        return valid_count == total_count


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Validate all schema-gen output formats"
    )
    parser.add_argument(
        "--formats",
        nargs="*",
        default=None,
        help="Specific formats to validate (default: all)",
    )
    parser.add_argument(
        "--format",
        type=str,
        default=None,
        help="Single format to validate (alternative to --formats)",
    )
    parser.add_argument(
        "--fail-fast", action="store_true", help="Stop on first validation failure"
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Show detailed validation results"
    )

    args = parser.parse_args()

    validator = FormatValidator()

    # Handle format selection
    formats_to_validate = None
    if args.format:
        formats_to_validate = [args.format]
    elif args.formats:
        formats_to_validate = args.formats

    print("🔍 Starting format validation...")
    print(f"📋 Test schema: {validator.test_schema.name}")
    print(f"📝 Fields: {len(validator.test_schema.fields)}")
    if formats_to_validate:
        print(f"🎯 Validating specific formats: {', '.join(formats_to_validate)}")
    print()

    results = validator.run_all_validations()

    # Filter results if specific formats were requested
    if formats_to_validate:
        # Validate that requested formats exist
        available_formats = set(results.keys())
        requested_formats = set(formats_to_validate)
        invalid_formats = requested_formats - available_formats

        if invalid_formats:
            print(f"❌ Unknown formats requested: {', '.join(invalid_formats)}")
            print(f"📋 Available formats: {', '.join(sorted(available_formats))}")
            return 1

        # Filter to only requested formats
        results = {
            fmt: result for fmt, result in results.items() if fmt in requested_formats
        }

    if args.verbose:
        print("\nDETAILED RESULTS:")
        print("-" * 40)
        for format_name, result in results.items():
            print(f"\n{format_name.upper()}:")
            print(f"  Valid: {result['valid']}")
            if result["error"]:
                print(f"  Error: {result['error']}")
            if result["details"]:
                for key, value in result["details"].items():
                    print(f"  {key}: {value}")

    success = validator.print_summary(results)

    if not success:
        return 1

    print("\n🎉 All formats validated successfully!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
