#!/usr/bin/env python3
"""
Version compatibility checker for schema-gen

This script helps check compatibility with different versions of target libraries.
"""

import argparse
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import yaml


def load_version_matrix() -> dict[str, Any]:
    """Load version compatibility matrix"""
    matrix_file = Path(__file__).parent.parent / "tests" / "test-matrix.yml"
    with open(matrix_file) as f:
        return yaml.safe_load(f)


def check_library_version(library: str) -> str | None:
    """Check currently installed version of a library"""
    try:
        if library == "pydantic":
            import pydantic

            return pydantic.VERSION
        elif library == "sqlalchemy":
            import sqlalchemy

            return sqlalchemy.__version__
        elif library == "pathway":
            import pathway

            return pathway.__version__
        elif library == "jsonschema":
            import jsonschema

            return jsonschema.__version__
        elif library == "graphql-core":
            import graphql

            return graphql.__version__
        elif library == "avro":
            import avro

            return avro.__version__
        elif library == "protobuf":
            import google.protobuf

            return google.protobuf.__version__
        else:
            return None
    except ImportError:
        return None


def install_version(library: str, version: str) -> bool:
    """Install specific version of a library"""
    try:
        cmd = ["uv", "pip", "install", f"{library}=={version}"]
        result = subprocess.run(cmd, capture_output=True, text=True)
        return result.returncode == 0
    except Exception:
        return False


def get_all_generators():
    """Get all available generators"""
    return {
        # Python libraries that can be version-tested
        "pydantic": (
            "PydanticGenerator",
            "from schema_gen.generators.pydantic_generator import PydanticGenerator",
        ),
        "sqlalchemy": (
            "SqlAlchemyGenerator",
            "from schema_gen.generators.sqlalchemy_generator import SqlAlchemyGenerator",
        ),
        "pathway": (
            "PathwayGenerator",
            "from schema_gen.generators.pathway_generator import PathwayGenerator",
        ),
        # Python-only generators (no external deps to test)
        "dataclasses": (
            "DataclassesGenerator",
            "from schema_gen.generators.dataclasses_generator import DataclassesGenerator",
        ),
        "typeddict": (
            "TypedDictGenerator",
            "from schema_gen.generators.typeddict_generator import TypedDictGenerator",
        ),
        # Schema generators (syntax-only testing)
        "jsonschema": (
            "JsonSchemaGenerator",
            "from schema_gen.generators.jsonschema_generator import JsonSchemaGenerator",
        ),
        "avro": (
            "AvroGenerator",
            "from schema_gen.generators.avro_generator import AvroGenerator",
        ),
        "protobuf": (
            "ProtobufGenerator",
            "from schema_gen.generators.protobuf_generator import ProtobufGenerator",
        ),
        # Language generators (syntax-only testing)
        "zod": (
            "ZodGenerator",
            "from schema_gen.generators.zod_generator import ZodGenerator",
        ),
        "graphql": (
            "GraphQLGenerator",
            "from schema_gen.generators.graphql_generator import GraphQLGenerator",
        ),
        "jackson": (
            "JacksonGenerator",
            "from schema_gen.generators.jackson_generator import JacksonGenerator",
        ),
        "kotlin": (
            "KotlinGenerator",
            "from schema_gen.generators.kotlin_generator import KotlinGenerator",
        ),
    }


def test_generator_with_version(library: str, version: str) -> bool:
    """Test generator compatibility with specific library version"""

    # Create test schema
    test_schema_code = """
from schema_gen import Schema, Field
from typing import Optional
from datetime import datetime

@Schema
class CompatibilityTest:
    id: int = Field(primary_key=True, description="Test ID")
    name: str = Field(min_length=2, max_length=100, description="Test name")
    email: str = Field(format="email", description="Email address")
    age: Optional[int] = Field(default=None, min_value=18, max_value=100)
    created_at: datetime = Field(auto_now_add=True)

    class Variants:
        create = ['name', 'email', 'age']
        response = ['id', 'name', 'age', 'created_at']
"""

    with tempfile.TemporaryDirectory() as temp_dir:
        # Write test schema
        schema_file = Path(temp_dir) / "test_schema.py"
        schema_file.write_text(test_schema_code)

        # Test generation
        test_script = f'''
import sys
sys.path.append("{temp_dir}")

from schema_gen.parsers.schema_parser import SchemaParser
from test_schema import CompatibilityTest

parser = SchemaParser()
schema = parser.parse_schema(CompatibilityTest)

try:
    if "{library}" == "pydantic":
        from schema_gen.generators.pydantic_generator import PydanticGenerator
        generator = PydanticGenerator()
    elif "{library}" == "sqlalchemy":
        from schema_gen.generators.sqlalchemy_generator import SqlAlchemyGenerator
        generator = SqlAlchemyGenerator()
    elif "{library}" == "pathway":
        from schema_gen.generators.pathway_generator import PathwayGenerator
        generator = PathwayGenerator()
    elif "{library}" == "jsonschema":
        from schema_gen.generators.jsonschema_generator import JsonSchemaGenerator
        generator = JsonSchemaGenerator()
    elif "{library}" == "graphql-core":
        from schema_gen.generators.graphql_generator import GraphQLGenerator
        generator = GraphQLGenerator()
    elif "{library}" == "avro":
        from schema_gen.generators.avro_generator import AvroGenerator
        generator = AvroGenerator()
    elif "{library}" == "protobuf":
        from schema_gen.generators.protobuf_generator import ProtobufGenerator
        generator = ProtobufGenerator()
    else:
        raise ValueError("Unknown library: {library}")

    # Generate and test compilation
    model_code = generator.generate_model(schema)
    create_code = generator.generate_model(schema, "create")
    response_code = generator.generate_model(schema, "response")

    # Test compilation
    compile(model_code, "<test>", "exec")
    compile(create_code, "<test>", "exec")
    compile(response_code, "<test>", "exec")

    print("SUCCESS: All models generated and compiled successfully")

except Exception as e:
    print(f"ERROR: {{e}}")
    sys.exit(1)
'''

        try:
            result = subprocess.run(
                ["python", "-c", test_script],
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode == 0 and "SUCCESS" in result.stdout:
                return True
            else:
                print(f"Test failed for {library} {version}:")
                print(f"STDOUT: {result.stdout}")
                print(f"STDERR: {result.stderr}")
                return False

        except subprocess.TimeoutExpired:
            print(f"Test timed out for {library} {version}")
            return False
        except Exception as e:
            print(f"Test execution failed for {library} {version}: {e}")
            return False


def run_compatibility_check(library: str, versions: list[str] | None = None):
    """Run compatibility check for a library"""
    matrix = load_version_matrix()

    if versions is None:
        versions = matrix.get("version_matrix", {}).get(library, [])

    if not versions:
        print(f"No versions specified for {library}")
        return

    print(f"\n🔍 Testing {library} compatibility...")
    print(f"Testing versions: {', '.join(versions)}")

    current_version = check_library_version(library)
    if current_version:
        print(f"Currently installed: {library} {current_version}")
    else:
        print(f"{library} not currently installed")

    results = {}

    for version in versions:
        print(f"\n📦 Testing {library} {version}...")

        # Install specific version
        if install_version(library, version):
            print(f"✅ Installed {library} {version}")

            # Test generator
            if test_generator_with_version(library, version):
                print(f"✅ Generator works with {library} {version}")
                results[version] = True
            else:
                print(f"❌ Generator failed with {library} {version}")
                results[version] = False
        else:
            print(f"❌ Failed to install {library} {version}")
            results[version] = False

    # Summary
    print(f"\n📊 {library} compatibility summary:")
    for version, success in results.items():
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"  {version}: {status}")

    # Restore original version if it was installed
    if current_version and current_version not in versions:
        print(f"\n🔄 Restoring {library} {current_version}...")
        install_version(library, current_version)


def test_all_generators():
    """Test all generators with current installed versions"""
    print("🚀 Testing all generators...")

    generators = get_all_generators()
    results = {}

    # Create test schema
    test_schema_code = """
from schema_gen import Schema, Field
from typing import Optional
from datetime import datetime

@Schema
class AllGeneratorTest:
    id: int = Field(primary_key=True, description="Test ID")
    name: str = Field(min_length=2, max_length=100, description="Test name")
    email: str = Field(format="email", description="Email address")
    age: Optional[int] = Field(default=None, min_value=18, max_value=100)
    created_at: datetime = Field(auto_now_add=True)

    class Variants:
        create = ['name', 'email', 'age']
        response = ['id', 'name', 'age', 'created_at']
"""

    with tempfile.TemporaryDirectory() as temp_dir:
        # Write test schema
        schema_file = Path(temp_dir) / "test_schema.py"
        schema_file.write_text(test_schema_code)

        for gen_name, (class_name, import_stmt) in generators.items():
            print(f"\n📦 Testing {gen_name} generator...")

            test_script = f'''
import sys
sys.path.append("{temp_dir}")

from schema_gen.parsers.schema_parser import SchemaParser
from test_schema import AllGeneratorTest

parser = SchemaParser()
schema = parser.parse_schema(AllGeneratorTest)

try:
    {import_stmt}
    generator = {class_name}()

    # Generate base model - try different method names
    if hasattr(generator, 'generate_model'):
        model_code = generator.generate_model(schema)

        # Test variants if supported
        try:
            create_code = generator.generate_model(schema, "create")
            response_code = generator.generate_model(schema, "response")
            variant_count = 3  # base + create + response
        except Exception:
            variant_count = 1  # only base model
    elif hasattr(generator, 'generate_file'):
        model_code = generator.generate_file(schema)
        variant_count = 1  # file generators typically include all variants in one file
    else:
        raise ValueError(f"Generator has no generate_model or generate_file method")

    # Basic validation
    if len(model_code.strip()) == 0:
        raise ValueError("Generated empty code")

    # Library-specific validation
    if gen_name in ["pydantic", "sqlalchemy", "pathway"]:
        # Python generators - compile test
        compile(model_code, "<test>", "exec")
    elif gen_name in ["jsonschema", "avro"]:
        # JSON generators - JSON parse test
        import json
        json.loads(model_code)

        # For jsonschema, test actual validation
        if gen_name == "jsonschema":
            import jsonschema
            schema_data = json.loads(model_code)
            # Test basic validation works
            test_data = {{"id": 1, "name": "test", "email": "test@example.com"}}
            jsonschema.validate(test_data, schema_data)

        # For avro, test schema parsing
        elif gen_name == "avro":
            import avro.schema
            import json
            avro_data = json.loads(model_code)
            if "schemas" in avro_data:
                main_schema = next((s for s in avro_data["schemas"] if s.get("name")), None)
                if main_schema:
                    avro.schema.parse(json.dumps(main_schema))

    elif gen_name == "graphql":
        # GraphQL generators - basic syntax check
        if not ("type " in model_code or "input " in model_code):
            raise ValueError("Missing GraphQL type/input definition")

    elif gen_name == "protobuf":
        # Proto generators - basic message syntax check
        if "message " not in model_code:
            raise ValueError("Missing protobuf message definition")

    print(f"SUCCESS: {{variant_count}} variant(s) generated and validated")

except Exception as e:
    print(f"ERROR: {{e}}")
    sys.exit(1)
'''

            try:
                result = subprocess.run(
                    ["python", "-c", test_script],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )

                if result.returncode == 0 and "SUCCESS" in result.stdout:
                    print(f"✅ {gen_name} generator test passed")
                    # Extract variant count from output
                    variant_info = [
                        line
                        for line in result.stdout.split("\n")
                        if "variant(s) generated" in line
                    ]
                    if variant_info:
                        print(f"   {variant_info[0].split('SUCCESS: ')[1]}")
                    results[gen_name] = True
                else:
                    print(f"❌ {gen_name} generator test failed")
                    if result.stdout:
                        print(f"   STDOUT: {result.stdout}")
                    if result.stderr:
                        print(f"   STDERR: {result.stderr}")
                    results[gen_name] = False

            except subprocess.TimeoutExpired:
                print(f"❌ {gen_name} generator test timed out")
                results[gen_name] = False
            except Exception as e:
                print(f"❌ {gen_name} generator test execution failed: {e}")
                results[gen_name] = False

    # Summary
    print("\n📊 All generators test summary:")
    passed = sum(1 for success in results.values() if success)
    total = len(results)

    for gen_name, success in results.items():
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"  {gen_name:12}: {status}")

    print(f"\nResult: {passed}/{total} generators passed")
    return results


def run_full_compatibility_matrix():
    """Run compatibility check for all libraries in the matrix"""
    matrix = load_version_matrix()

    print("🚀 Running full compatibility matrix...")

    # First test all generators with current versions
    print("\n" + "=" * 50)
    print("PHASE 1: Testing all generators")
    print("=" * 50)
    test_all_generators()

    # Then test version compatibility for libraries with version deps
    print("\n" + "=" * 50)
    print("PHASE 2: Testing version compatibility")
    print("=" * 50)

    version_testable = [
        "pydantic",
        "sqlalchemy",
        "pathway",
        "jsonschema",
        "graphql-core",
        "avro",
        "protobuf",
    ]
    for library in version_testable:
        if library in matrix.get("version_matrix", {}):
            versions = matrix["version_matrix"][library]
            try:
                run_compatibility_check(library, versions)
            except KeyboardInterrupt:
                print(f"\n⚠️  Interrupted during {library} testing")
                break
            except Exception as e:
                print(f"\n❌ Error testing {library}: {e}")
                continue

    print("\n🏁 Full compatibility testing completed!")


def main():
    parser = argparse.ArgumentParser(
        description="Check version compatibility for schema-gen generators"
    )
    parser.add_argument(
        "--library",
        choices=[
            "pydantic",
            "sqlalchemy",
            "pathway",
            "jsonschema",
            "graphql-core",
            "avro",
            "protobuf",
            "all",
            "all-generators",
        ],
        default="all",
        help="Library to test (default: all)",
    )
    parser.add_argument(
        "--versions", nargs="+", help="Specific versions to test (overrides matrix)"
    )
    parser.add_argument(
        "--current-only",
        action="store_true",
        help="Only test currently installed versions",
    )

    args = parser.parse_args()

    if args.current_only:
        # Test only currently installed versions
        for lib in [
            "pydantic",
            "sqlalchemy",
            "pathway",
            "jsonschema",
            "graphql-core",
            "avro",
            "protobuf",
        ]:
            version = check_library_version(lib)
            if version:
                print(f"\n🔍 Testing current {lib} version {version}...")
                if test_generator_with_version(lib, version):
                    print(f"✅ Current {lib} {version} is compatible")
                else:
                    print(f"❌ Current {lib} {version} has compatibility issues")

    elif args.library == "all":
        run_full_compatibility_matrix()
    elif args.library == "all-generators":
        test_all_generators()
    else:
        run_compatibility_check(args.library, args.versions)


if __name__ == "__main__":
    main()
