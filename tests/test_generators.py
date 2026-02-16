"""Comprehensive tests for all schema generators"""

import json
from datetime import datetime

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


class TestAllGenerators:
    """Test all generators with a comprehensive schema"""

    def setup_method(self):
        """Clear registry before each test"""
        SchemaRegistry._schemas.clear()

    @pytest.fixture
    def comprehensive_schema(self):
        """Create a comprehensive test schema"""

        @Schema
        class TestUser:
            """Comprehensive user schema for generator testing"""

            id: int = Field(primary_key=True, description="Unique identifier")

            name: str = Field(
                min_length=2, max_length=100, description="User's full name"
            )

            email: str = Field(format="email", description="User's email address")

            age: int | None = Field(
                default=None, min_value=13, max_value=120, description="User's age"
            )

            created_at: datetime = Field(description="Account creation timestamp")

            class Variants:
                create_request = ["name", "email", "age"]
                public_response = ["id", "name", "age", "created_at"]
                update_request = ["name", "email", "age"]

        parser = SchemaParser()
        return parser.parse_schema(TestUser)

    def test_pydantic_generator(self, comprehensive_schema):
        """Test Pydantic generator"""
        generator = PydanticGenerator()

        # Test file generation
        file_content = generator.generate_file(comprehensive_schema)

        # Verify content
        assert "class TestUser(BaseModel):" in file_content
        assert "class TestUserCreateRequest(BaseModel):" in file_content
        assert "class TestUserPublicResponse(BaseModel):" in file_content
        assert "class TestUserUpdateRequest(BaseModel):" in file_content
        assert "from pydantic import BaseModel, ConfigDict, Field" in file_content
        assert "EmailStr" in file_content
        assert "min_length=2, max_length=100" in file_content

        # Verify it compiles as valid Python
        compile(file_content, "<test>", "exec")

    def test_sqlalchemy_generator(self, comprehensive_schema):
        """Test SQLAlchemy generator"""
        generator = SqlAlchemyGenerator()

        file_content = generator.generate_file(comprehensive_schema)

        # Verify content
        assert "class TestUser(Base):" in file_content
        assert "from sqlalchemy.orm import" in file_content
        assert '__tablename__ = "test_user"' in file_content
        assert "mapped_column(" in file_content
        assert "Mapped[int]" in file_content
        assert "primary_key=True" in file_content

        # Verify it compiles as valid Python
        compile(file_content, "<test>", "exec")

    def test_zod_generator(self, comprehensive_schema):
        """Test Zod generator"""
        generator = ZodGenerator()

        file_content = generator.generate_file(comprehensive_schema)

        # Verify content
        assert "export const TestUserSchema = z.object({" in file_content
        assert "export const TestUserCreateRequestSchema = z.object({" in file_content
        assert "import { z } from 'zod';" in file_content
        assert ".email()" in file_content
        assert ".min(2).max(100)" in file_content
        assert ".min(13).max(120)" in file_content
        assert "export type TestUser = z.infer<typeof TestUserSchema>;" in file_content

    def test_pathway_generator(self, comprehensive_schema):
        """Test Pathway generator"""
        generator = PathwayGenerator()

        file_content = generator.generate_file(comprehensive_schema)

        # Verify content
        assert "class TestUser(pw.Table):" in file_content
        assert "class TestUserCreateRequest(pw.Table):" in file_content
        assert "import pathway as pw" in file_content
        assert "id: pw.ColumnExpression  # int" in file_content
        assert "name: pw.ColumnExpression  # str" in file_content

        # Verify it compiles as valid Python
        compile(file_content, "<test>", "exec")

    def test_dataclasses_generator(self, comprehensive_schema):
        """Test Dataclasses generator"""
        generator = DataclassesGenerator()

        file_content = generator.generate_file(comprehensive_schema)

        # Verify content
        assert "@dataclass" in file_content
        assert "class TestUser:" in file_content
        assert "class TestUserCreateRequest:" in file_content
        assert "from dataclasses import dataclass" in file_content
        assert "import datetime" in file_content
        assert "id: int" in file_content
        assert "age: int = None" in file_content

        # Verify it compiles as valid Python
        compile(file_content, "<test>", "exec")

    def test_typeddict_generator(self, comprehensive_schema):
        """Test TypedDict generator"""
        generator = TypedDictGenerator()

        file_content = generator.generate_file(comprehensive_schema)

        # Verify content
        assert "class TestUser(TypedDict):" in file_content
        assert "class TestUserCreateRequest(TypedDict):" in file_content
        assert "from typing_extensions import TypedDict, NotRequired" in file_content
        assert "id: int" in file_content
        assert "age: NotRequired[int]" in file_content

        # Verify it compiles as valid Python
        compile(file_content, "<test>", "exec")

    def test_jsonschema_generator(self, comprehensive_schema):
        """Test JSON Schema generator"""
        generator = JsonSchemaGenerator()

        file_content = generator.generate_file(comprehensive_schema)

        # Verify it's valid JSON
        schema_data = json.loads(file_content)

        # Verify structure
        assert schema_data["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert "TestUser" in schema_data["$defs"]
        assert "TestUserCreateRequest" in schema_data["$defs"]

        # Verify default base URL in $id
        assert schema_data["$id"] == "https://example.com/schemas/testuser.json"

        # Verify field constraints
        user_schema = schema_data["$defs"]["TestUser"]
        assert user_schema["properties"]["name"]["minLength"] == 2
        assert user_schema["properties"]["name"]["maxLength"] == 100
        assert user_schema["properties"]["email"]["format"] == "email"
        assert user_schema["properties"]["age"]["minimum"] == 13
        assert user_schema["properties"]["age"]["maximum"] == 120

    def test_jsonschema_generator_custom_base_url(self, comprehensive_schema):
        """Test JSON Schema generator with custom base URL"""
        generator = JsonSchemaGenerator(base_url="https://api.myapp.io/schemas")

        file_content = generator.generate_file(comprehensive_schema)
        schema_data = json.loads(file_content)

        assert schema_data["$id"] == "https://api.myapp.io/schemas/testuser.json"

    def test_jsonschema_generator_schema_level_override(self, comprehensive_schema):
        """Test JSON Schema generator with schema-level base URL override"""
        generator = JsonSchemaGenerator(base_url="https://default.example.com/schemas")

        # Set schema-level override via metadata
        comprehensive_schema.metadata["jsonschema"] = {
            "base_url": "https://override.example.com/schemas"
        }

        file_content = generator.generate_file(comprehensive_schema)
        schema_data = json.loads(file_content)

        assert (
            schema_data["$id"] == "https://override.example.com/schemas/testuser.json"
        )

    def test_graphql_generator(self, comprehensive_schema):
        """Test GraphQL generator"""
        generator = GraphQLGenerator()

        file_content = generator.generate_file(comprehensive_schema)

        # Verify content
        assert "type TestUser {" in file_content
        assert "input TestUserCreateRequestInput {" in file_content
        assert "input TestUserInput {" in file_content
        assert "scalar DateTime" in file_content
        assert "id: Int!" in file_content
        assert "name: String!" in file_content
        assert "email: String!" in file_content
        assert "age: Int" in file_content
        assert "created_at: DateTime!" in file_content

    def test_protobuf_generator(self, comprehensive_schema):
        """Test Protobuf generator"""
        generator = ProtobufGenerator()

        file_content = generator.generate_file(comprehensive_schema)

        # Verify content
        assert 'syntax = "proto3";' in file_content
        assert "package testuser;" in file_content
        assert "message TestUser {" in file_content
        assert "message TestUserCreateRequest {" in file_content
        assert "service TestUserService {" in file_content
        assert 'import "google/protobuf/timestamp.proto";' in file_content
        assert "int64 id = 1;" in file_content
        assert "string name = 2;" in file_content
        assert "optional uint32 age = " in file_content
        assert "google.protobuf.Timestamp created_at = " in file_content

    def test_avro_generator(self, comprehensive_schema):
        """Test Avro generator"""
        generator = AvroGenerator()

        file_content = generator.generate_file(comprehensive_schema)

        # Verify it's valid JSON
        avro_data = json.loads(file_content)

        # Verify structure
        assert "_meta" in avro_data
        assert avro_data["_meta"]["generator"] == "schema-gen Avro generator"
        assert "schemas" in avro_data

        # Find the main schema
        main_schema = next(s for s in avro_data["schemas"] if s["name"] == "TestUser")
        assert main_schema["type"] == "record"
        assert main_schema["namespace"] == "com.example.testuser"

        # Verify field types
        fields_by_name = {f["name"]: f for f in main_schema["fields"]}
        assert fields_by_name["id"]["type"] == "long"
        assert fields_by_name["name"]["type"] == "string"
        assert fields_by_name["email"]["type"] == "string"
        assert fields_by_name["age"]["type"] == ["null", "int"]
        assert fields_by_name["created_at"]["type"]["logicalType"] == "timestamp-millis"

        # Verify null comes FIRST in optional field unions (Avro convention)
        age_type = fields_by_name["age"]["type"]
        assert isinstance(age_type, list), "Optional field should produce a union type"
        assert age_type[0] == "null", (
            "null must be the first element in an optional union"
        )

        # Verify optional field with default=None gets null default
        assert fields_by_name["age"]["default"] is None

    def test_avro_null_ordering_in_optional_unions(self, comprehensive_schema):
        """Test that Avro generator always places null first in optional unions"""
        from schema_gen.core.usr import FieldType, USRField, USRSchema

        generator = AvroGenerator()

        # Create a schema with an optional union field to test null reordering
        union_inner_1 = USRField(
            name="opt_union_0", type=FieldType.STRING, python_type=str
        )
        union_inner_2 = USRField(
            name="opt_union_1", type=FieldType.INTEGER, python_type=int
        )
        optional_union_field = USRField(
            name="flexible",
            type=FieldType.UNION,
            python_type=str,
            optional=True,
            union_types=[union_inner_1, union_inner_2],
        )
        test_schema = USRSchema(
            name="NullOrderTest",
            fields=[optional_union_field],
            description="Test null ordering",
        )

        file_content = generator.generate_file(test_schema)
        avro_data = json.loads(file_content)
        main_schema = avro_data["schemas"][0]
        flexible_field = main_schema["fields"][0]

        # null must come first in the union
        assert flexible_field["type"][0] == "null", (
            f"null must be first in optional union, got: {flexible_field['type']}"
        )

    def test_jackson_generator(self, comprehensive_schema):
        """Test Jackson generator"""
        generator = JacksonGenerator()

        file_content = generator.generate_file(comprehensive_schema)

        # Verify default package name appears in output
        assert "package com.example.models;" in file_content
        assert "public class TestUser {" in file_content
        # Variant classes should be package-private (not public) to allow multiple classes in one file
        assert "class TestUserCreateRequest {" in file_content
        assert '@JsonProperty("id")' in file_content
        assert '@JsonProperty("name")' in file_content
        assert "@NotNull" in file_content
        assert "@Size(min = 2, max = 100)" in file_content
        assert "@Email" in file_content
        assert "@Min(value = 13)" in file_content
        assert "@Max(120)" in file_content
        assert "private int id;" in file_content
        assert "private String name;" in file_content
        assert "private Integer age;" in file_content
        assert "private Instant created_at;" in file_content
        assert "public int getId() {" in file_content
        assert "public void setId(int id) {" in file_content

    def test_jackson_generator_custom_package(self, comprehensive_schema):
        """Test Jackson generator with custom default_package"""
        generator = JacksonGenerator(default_package="org.myapp.dto")

        file_content = generator.generate_file(comprehensive_schema)
        assert "package org.myapp.dto;" in file_content

    def test_jackson_generator_schema_level_package(self, comprehensive_schema):
        """Test Jackson generator with schema-level package override"""
        generator = JacksonGenerator(default_package="org.myapp.dto")

        # Set schema-level override via target_config
        comprehensive_schema.target_config["jackson"] = {
            "package": "com.override.models"
        }

        file_content = generator.generate_file(comprehensive_schema)
        assert "package com.override.models;" in file_content

    def test_kotlin_generator(self, comprehensive_schema):
        """Test Kotlin generator"""
        generator = KotlinGenerator()

        file_content = generator.generate_file(comprehensive_schema)

        # Verify default package name appears in output
        assert "package com.example.models" in file_content
        assert "data class TestUser(" in file_content
        assert "data class TestUserCreateRequest(" in file_content
        assert "@Serializable" in file_content
        assert "import kotlinx.serialization.Serializable" in file_content
        assert "import kotlinx.serialization.SerialName" in file_content
        assert "import kotlinx.datetime.Instant" in file_content
        assert "val id: Long" in file_content
        assert "val name: String" in file_content
        assert "val age: Int? = null" in file_content
        assert "val createdAt: Instant" in file_content
        assert '@SerialName("created_at")' in file_content

    def test_kotlin_generator_custom_package(self, comprehensive_schema):
        """Test Kotlin generator with custom default_package"""
        generator = KotlinGenerator(default_package="org.myapp.dto")

        file_content = generator.generate_file(comprehensive_schema)
        assert "package org.myapp.dto" in file_content

    def test_kotlin_generator_schema_level_package(self, comprehensive_schema):
        """Test Kotlin generator with schema-level package override"""
        generator = KotlinGenerator(default_package="org.myapp.dto")

        # Set schema-level override via target_config
        comprehensive_schema.target_config["kotlin"] = {
            "package": "com.override.models"
        }

        file_content = generator.generate_file(comprehensive_schema)
        assert "package com.override.models" in file_content


class TestGeneratorEdgeCases:
    """Test edge cases and error handling"""

    def setup_method(self):
        """Clear registry before each test"""
        SchemaRegistry._schemas.clear()

    def test_empty_schema(self):
        """Test generators with empty schema"""

        @Schema
        class EmptySchema:
            """Empty schema for testing"""

            pass

        parser = SchemaParser()
        schema = parser.parse_schema(EmptySchema)

        generators = [
            PydanticGenerator(),
            DataclassesGenerator(),
            TypedDictGenerator(),
            JsonSchemaGenerator(),
            KotlinGenerator(),
        ]

        for generator in generators:
            file_content = generator.generate_file(schema)
            assert "EmptySchema" in file_content
            # Should generate valid content even for empty schemas

    def test_schema_with_complex_types(self):
        """Test generators with complex field types"""

        @Schema
        class ComplexSchema:
            """Schema with complex types"""

            string_list: list[str] = Field(description="List of strings")
            optional_list: list[int] | None = Field(
                default=None, description="Optional list of integers"
            )

        parser = SchemaParser()
        schema = parser.parse_schema(ComplexSchema)

        # Test a few generators that should handle complex types
        pydantic_gen = PydanticGenerator()
        pydantic_result = pydantic_gen.generate_file(schema)
        assert "list[str]" in pydantic_result
        assert "Optional[list[int]]" in pydantic_result

        kotlin_gen = KotlinGenerator()
        kotlin_result = kotlin_gen.generate_file(schema)
        assert "List<String>" in kotlin_result
        assert "List<Long>" in kotlin_result


class TestLiteralSupport:
    """Test literal type handling in Zod generator"""

    def setup_method(self):
        """Clear registry before each test"""
        SchemaRegistry._schemas.clear()

    def test_zod_single_literal_string(self):
        """Test Zod generator produces z.literal() for single string literal"""
        from typing import Literal

        @Schema
        class SingleLiteralSchema:
            """Schema with single literal value"""

            status: Literal["active"] = Field(description="Always active")

        parser = SchemaParser()
        schema = parser.parse_schema(SingleLiteralSchema)
        generator = ZodGenerator()
        file_content = generator.generate_file(schema)

        assert 'z.literal("active")' in file_content
        assert "z.enum" not in file_content

    def test_zod_multi_literal_strings(self):
        """Test Zod generator produces z.union of z.literal for multiple string literals"""
        from typing import Literal

        SchemaRegistry._schemas.clear()

        @Schema
        class MultiLiteralSchema:
            """Schema with multiple literal values"""

            color: Literal["red", "green", "blue"] = Field(description="Color choice")

        parser = SchemaParser()
        schema = parser.parse_schema(MultiLiteralSchema)
        generator = ZodGenerator()
        file_content = generator.generate_file(schema)

        assert (
            'z.union([z.literal("red"), z.literal("green"), z.literal("blue")])'
            in file_content
        )
        assert "z.enum" not in file_content

    def test_zod_literal_integer(self):
        """Test Zod generator handles integer literal values without quotes"""
        from typing import Literal

        SchemaRegistry._schemas.clear()

        @Schema
        class IntLiteralSchema:
            """Schema with integer literal"""

            code: Literal[42] = Field(description="The answer")

        parser = SchemaParser()
        schema = parser.parse_schema(IntLiteralSchema)
        generator = ZodGenerator()
        file_content = generator.generate_file(schema)

        assert "z.literal(42)" in file_content
        assert "z.enum" not in file_content

    def test_zod_multi_literal_mixed(self):
        """Test Zod generator handles mixed literal types"""
        from typing import Literal

        SchemaRegistry._schemas.clear()

        @Schema
        class MixedLiteralSchema:
            """Schema with mixed literal values"""

            value: Literal["auto", 0, 1] = Field(description="Mixed values")

        parser = SchemaParser()
        schema = parser.parse_schema(MixedLiteralSchema)
        generator = ZodGenerator()
        file_content = generator.generate_file(schema)

        assert (
            'z.union([z.literal("auto"), z.literal(0), z.literal(1)])' in file_content
        )
        assert "z.enum" not in file_content


class TestEnumSupport:
    """Test enum support across all affected generators"""

    def setup_method(self):
        """Clear registry before each test"""
        SchemaRegistry._schemas.clear()

    @pytest.fixture
    def enum_schema(self):
        """Create a test schema with Enum fields"""
        from enum import Enum as PyEnum

        class Priority(PyEnum):
            LOW = "low"
            MEDIUM = "medium"
            HIGH = "high"

        @Schema
        class TaskItem:
            """A task with priority"""

            id: int = Field(primary_key=True, description="Unique identifier")
            title: str = Field(min_length=1, max_length=200, description="Task title")
            priority: Priority = Field(
                default=Priority.MEDIUM, description="Task priority"
            )

        parser = SchemaParser()
        return parser.parse_schema(TaskItem)

    def test_enum_detected_in_usr(self, enum_schema):
        """Test that enums are correctly detected in USR"""
        from schema_gen.core.usr import FieldType

        # Check the priority field
        priority_field = enum_schema.get_field("priority")
        assert priority_field is not None
        assert priority_field.type == FieldType.ENUM
        assert priority_field.enum_name == "Priority"
        assert priority_field.enum_values == ["low", "medium", "high"]

        # Check enums list on schema
        assert len(enum_schema.enums) == 1
        assert enum_schema.enums[0].name == "Priority"
        assert enum_schema.enums[0].values == [
            ("LOW", "low"),
            ("MEDIUM", "medium"),
            ("HIGH", "high"),
        ]

    def test_pydantic_enum_generation(self, enum_schema):
        """Test Pydantic generator produces valid enum output"""
        generator = PydanticGenerator()
        file_content = generator.generate_file(enum_schema)

        # Should contain the enum class definition
        assert "class Priority(Enum):" in file_content
        assert 'LOW = "low"' in file_content
        assert 'MEDIUM = "medium"' in file_content
        assert 'HIGH = "high"' in file_content

        # Should import Enum
        assert "from enum import Enum" in file_content

        # Priority field should reference the enum
        assert "priority: Priority" in file_content

        # Default should reference enum member
        assert "default=Priority.MEDIUM" in file_content

        # Should compile as valid Python
        compile(file_content, "<test>", "exec")

    def test_sqlalchemy_enum_generation(self, enum_schema):
        """Test SQLAlchemy generator handles enum fields"""
        generator = SqlAlchemyGenerator()
        file_content = generator.generate_file(enum_schema)

        # Should use String column type for enum fields
        assert "String(" in file_content

        # Default should be the enum value string
        assert 'default="medium"' in file_content

        # Should import Base from _base
        assert "from ._base import Base" in file_content

        # Should NOT contain inline Base = declarative_base()
        assert "Base = declarative_base()" not in file_content

        # Should compile as valid Python
        compile(file_content, "<test>", "exec")

    def test_sqlalchemy_auto_now(self):
        """Test SQLAlchemy generator handles auto_now correctly"""
        SchemaRegistry._schemas.clear()

        @Schema
        class TimestampModel:
            """Model with timestamps"""

            id: int = Field(primary_key=True)
            created_at: datetime = Field(auto_now_add=True)
            updated_at: datetime = Field(auto_now=True)

        parser = SchemaParser()
        schema = parser.parse_schema(TimestampModel)
        generator = SqlAlchemyGenerator()
        file_content = generator.generate_file(schema)

        # auto_now should produce server_default AND onupdate
        assert "onupdate=func.now()" in file_content
        assert "server_default=func.now()" in file_content

    def test_zod_enum_generation(self, enum_schema):
        """Test Zod generator produces valid enum output"""
        generator = ZodGenerator()
        file_content = generator.generate_file(enum_schema)

        # Should contain z.enum() definition
        assert 'PrioritySchema = z.enum(["low", "medium", "high"])' in file_content

        # Should have TypeScript type
        assert "export type Priority = z.infer<typeof PrioritySchema>;" in file_content

        # Priority field should reference the enum schema
        assert "PrioritySchema" in file_content

        # Default should be the string value
        assert '.default("medium")' in file_content

    def test_jsonschema_enum_generation(self, enum_schema):
        """Test JSON Schema generator produces valid enum output"""
        generator = JsonSchemaGenerator()
        file_content = generator.generate_file(enum_schema)

        schema_data = json.loads(file_content)

        # Should have Priority in $defs
        assert "Priority" in schema_data["$defs"]
        priority_def = schema_data["$defs"]["Priority"]
        assert priority_def["type"] == "string"
        assert priority_def["enum"] == ["low", "medium", "high"]

        # Priority field in TaskItem should reference $defs/Priority
        task_schema = schema_data["$defs"]["TaskItem"]
        assert task_schema["properties"]["priority"]["$ref"] == "#/$defs/Priority"

    def test_pydantic_regex_uses_pattern(self):
        """Test that Pydantic generator uses 'pattern' not 'regex'"""
        SchemaRegistry._schemas.clear()

        @Schema
        class PatternModel:
            """Model with regex pattern"""

            code: str = Field(regex=r"^[A-Z]{3}$")

        parser = SchemaParser()
        schema = parser.parse_schema(PatternModel)
        generator = PydanticGenerator()
        file_content = generator.generate_file(schema)

        assert "pattern=" in file_content
        assert "regex=" not in file_content


class TestSetFrozensetSupport:
    """Test set and frozenset type handling across generators"""

    def setup_method(self):
        """Clear registry before each test"""
        SchemaRegistry._schemas.clear()

    @pytest.fixture
    def set_schema(self):
        """Create a test schema with set and frozenset fields"""

        @Schema
        class TaggedItem:
            """Item with set-based fields"""

            id: int = Field(primary_key=True, description="Unique identifier")
            tags: set[str] = Field(description="Unique tags")
            frozen_tags: frozenset[int] = Field(description="Immutable tag IDs")

        parser = SchemaParser()
        return parser.parse_schema(TaggedItem)

    def test_usr_field_types(self, set_schema):
        """Test that set and frozenset are correctly detected in USR"""
        from schema_gen.core.usr import FieldType

        tags_field = set_schema.get_field("tags")
        assert tags_field is not None
        assert tags_field.type == FieldType.SET
        assert tags_field.inner_type is not None
        assert tags_field.inner_type.type == FieldType.STRING

        frozen_tags_field = set_schema.get_field("frozen_tags")
        assert frozen_tags_field is not None
        assert frozen_tags_field.type == FieldType.FROZENSET
        assert frozen_tags_field.inner_type is not None
        assert frozen_tags_field.inner_type.type == FieldType.INTEGER

    def test_pydantic_set_frozenset(self, set_schema):
        """Test Pydantic generator produces set[str] and frozenset[int]"""
        generator = PydanticGenerator()
        file_content = generator.generate_file(set_schema)

        assert "set[str]" in file_content
        assert "frozenset[int]" in file_content
        compile(file_content, "<test>", "exec")

    def test_jsonschema_set_frozenset(self, set_schema):
        """Test JSON Schema generator produces array with uniqueItems for sets"""
        generator = JsonSchemaGenerator()
        file_content = generator.generate_file(set_schema)

        schema_data = json.loads(file_content)
        tagged_item = schema_data["$defs"]["TaggedItem"]

        # Both set and frozenset should produce array with uniqueItems: true
        tags_prop = tagged_item["properties"]["tags"]
        assert tags_prop["type"] == "array"
        assert tags_prop["uniqueItems"] is True
        assert tags_prop["items"]["type"] == "string"

        frozen_tags_prop = tagged_item["properties"]["frozen_tags"]
        assert frozen_tags_prop["type"] == "array"
        assert frozen_tags_prop["uniqueItems"] is True
        assert frozen_tags_prop["items"]["type"] == "integer"

    def test_jackson_set_frozenset(self, set_schema):
        """Test Jackson generator produces Set<String> for set fields"""
        generator = JacksonGenerator()
        file_content = generator.generate_file(set_schema)

        assert "Set<String>" in file_content
        assert "Set<Integer>" in file_content
        assert "import java.util.Set;" in file_content

    def test_kotlin_set_frozenset(self, set_schema):
        """Test Kotlin generator produces Set<String> for set fields"""
        generator = KotlinGenerator()
        file_content = generator.generate_file(set_schema)

        assert "Set<String>" in file_content
        assert "Set<Long>" in file_content

    def test_dataclasses_set_frozenset(self, set_schema):
        """Test Dataclasses generator produces set[str] and frozenset[int]"""
        generator = DataclassesGenerator()
        file_content = generator.generate_file(set_schema)

        assert "set[str]" in file_content
        assert "frozenset[int]" in file_content
        compile(file_content, "<test>", "exec")

    def test_typeddict_set_frozenset(self, set_schema):
        """Test TypedDict generator produces set[str] and frozenset[int]"""
        generator = TypedDictGenerator()
        file_content = generator.generate_file(set_schema)

        assert "set[str]" in file_content
        assert "frozenset[int]" in file_content
        compile(file_content, "<test>", "exec")


class TestAnnotatedSupport:
    """Test typing.Annotated metadata extraction in TypeMapper"""

    def setup_method(self):
        """Clear registry before each test"""
        SchemaRegistry._schemas.clear()

    def test_annotated_string_description(self):
        """Test that a string annotation is captured as field description"""
        from typing import Annotated

        @Schema
        class AnnotatedDescSchema:
            """Schema with Annotated string metadata"""

            name: Annotated[str, "User's full name"] = Field(min_length=1)

        parser = SchemaParser()
        schema = parser.parse_schema(AnnotatedDescSchema)

        name_field = schema.get_field("name")
        assert name_field is not None
        assert name_field.description == "User's full name"
        # Base type should be correctly resolved to STRING
        from schema_gen.core.usr import FieldType

        assert name_field.type == FieldType.STRING
        # Field() constraint should still be applied
        assert name_field.min_length == 1

    def test_annotated_dict_metadata(self):
        """Test that a dict annotation is merged into field metadata"""
        from typing import Annotated

        @Schema
        class AnnotatedDictSchema:
            """Schema with Annotated dict metadata"""

            score: Annotated[int, {"source": "api", "deprecated": False}] = Field(
                min_value=0
            )

        parser = SchemaParser()
        schema = parser.parse_schema(AnnotatedDictSchema)

        score_field = schema.get_field("score")
        assert score_field is not None
        from schema_gen.core.usr import FieldType

        assert score_field.type == FieldType.INTEGER
        assert score_field.metadata["source"] == "api"
        assert score_field.metadata["deprecated"] is False
        # Field() constraint should still be applied
        assert score_field.min_value == 0

    def test_annotated_base_type_resolution(self):
        """Test that base types are correctly resolved through Annotated"""
        from typing import Annotated

        @Schema
        class AnnotatedTypesSchema:
            """Schema with various Annotated base types"""

            name: Annotated[str, "a name"] = Field()
            age: Annotated[int, "an age"] = Field()
            active: Annotated[bool, "is active"] = Field()
            tags: Annotated[list[str], "tag list"] = Field()

        parser = SchemaParser()
        schema = parser.parse_schema(AnnotatedTypesSchema)

        from schema_gen.core.usr import FieldType

        assert schema.get_field("name").type == FieldType.STRING
        assert schema.get_field("age").type == FieldType.INTEGER
        assert schema.get_field("active").type == FieldType.BOOLEAN
        assert schema.get_field("tags").type == FieldType.LIST
        # list[str] inner type should still be resolved
        assert schema.get_field("tags").inner_type is not None
        assert schema.get_field("tags").inner_type.type == FieldType.STRING

    def test_annotated_field_info_description_takes_precedence(self):
        """Test that Field(description=...) takes precedence over Annotated string"""
        from typing import Annotated

        @Schema
        class AnnotatedPrecedenceSchema:
            """Schema testing description precedence"""

            name: Annotated[str, "Annotated description"] = Field(
                description="Field description"
            )

        parser = SchemaParser()
        schema = parser.parse_schema(AnnotatedPrecedenceSchema)

        name_field = schema.get_field("name")
        assert name_field is not None
        # Field(description=...) should win over Annotated string
        assert name_field.description == "Field description"

    def test_annotated_combined_string_and_dict(self):
        """Test Annotated with both string and dict metadata"""
        from typing import Annotated

        @Schema
        class AnnotatedCombinedSchema:
            """Schema with combined Annotated metadata"""

            email: Annotated[str, "User email", {"format": "email"}] = Field()

        parser = SchemaParser()
        schema = parser.parse_schema(AnnotatedCombinedSchema)

        email_field = schema.get_field("email")
        assert email_field is not None
        assert email_field.description == "User email"
        assert email_field.metadata["format"] == "email"

    def test_annotated_with_optional(self):
        """Test Annotated wrapping an Optional type"""
        from typing import Annotated

        @Schema
        class AnnotatedOptionalSchema:
            """Schema with Annotated Optional field"""

            nickname: Annotated[str | None, "Optional nickname"] = Field(default=None)

        parser = SchemaParser()
        schema = parser.parse_schema(AnnotatedOptionalSchema)

        nick_field = schema.get_field("nickname")
        assert nick_field is not None
        assert nick_field.optional is True
        assert nick_field.description == "Optional nickname"

    def test_annotated_constraint_object(self):
        """Test that constraint objects in Annotated are extracted"""
        from typing import Annotated

        class MinMax:
            """Simple constraint descriptor"""

            def __init__(self, ge=None, le=None):
                self.ge = ge
                self.le = le

        @Schema
        class AnnotatedConstraintSchema:
            """Schema with constraint object in Annotated"""

            score: Annotated[int, MinMax(ge=0, le=100)] = Field()

        parser = SchemaParser()
        schema = parser.parse_schema(AnnotatedConstraintSchema)

        score_field = schema.get_field("score")
        assert score_field is not None
        assert score_field.min_value == 0
        assert score_field.max_value == 100

    def test_annotated_field_constraints_take_precedence_over_annotated_object(self):
        """Test that Field() constraints take precedence over Annotated constraint objects"""
        from typing import Annotated

        class MinMax:
            """Simple constraint descriptor"""

            def __init__(self, ge=None, le=None):
                self.ge = ge
                self.le = le

        @Schema
        class AnnotatedFieldPrecedenceSchema:
            """Schema where Field() constraints should win"""

            score: Annotated[int, MinMax(ge=0, le=100)] = Field(min_value=10)

        parser = SchemaParser()
        schema = parser.parse_schema(AnnotatedFieldPrecedenceSchema)

        score_field = schema.get_field("score")
        assert score_field is not None
        # Field(min_value=10) should take precedence over MinMax(ge=0)
        assert score_field.min_value == 10
        # max_value should come from MinMax since Field() didn't set it
        assert score_field.max_value == 100

    def test_annotated_generates_valid_pydantic(self):
        """Test that Annotated schemas generate valid Pydantic output"""
        from typing import Annotated

        @Schema
        class AnnotatedPydanticSchema:
            """Schema for Pydantic generation test"""

            name: Annotated[str, "User's full name"] = Field(
                min_length=1, max_length=100
            )
            score: Annotated[int, {"source": "api"}] = Field(min_value=0)

        parser = SchemaParser()
        schema = parser.parse_schema(AnnotatedPydanticSchema)

        generator = PydanticGenerator()
        file_content = generator.generate_file(schema)

        # Should contain the class
        assert "class AnnotatedPydanticSchema(BaseModel):" in file_content
        # Constraints should be present
        assert "min_length=1" in file_content
        assert "max_length=100" in file_content
        # Should compile as valid Python
        compile(file_content, "<test>", "exec")

    def test_python_type_to_usr_handles_annotated(self):
        """Test TypeMapper.python_type_to_usr directly with Annotated types"""
        from typing import Annotated

        from schema_gen.core.usr import FieldType, TypeMapper

        assert TypeMapper.python_type_to_usr(Annotated[str, "desc"]) == FieldType.STRING
        assert (
            TypeMapper.python_type_to_usr(Annotated[int, {"x": 1}]) == FieldType.INTEGER
        )
        assert (
            TypeMapper.python_type_to_usr(Annotated[list[str], "tags"])
            == FieldType.LIST
        )
        assert (
            TypeMapper.python_type_to_usr(Annotated[bool, "flag"]) == FieldType.BOOLEAN
        )


class TestTupleSupport:
    """Test tuple type handling across generators"""

    def setup_method(self):
        """Clear registry before each test"""
        SchemaRegistry._schemas.clear()

    def _make_tuple_schema(self):
        """Create a USR schema with tuple fields directly (bypassing @Schema decorator)"""
        from schema_gen.core.usr import FieldType, USRField, USRSchema

        # coordinates: tuple[float, float]
        coord_inner_0 = USRField(
            name="coordinates_0", type=FieldType.FLOAT, python_type=float
        )
        coord_inner_1 = USRField(
            name="coordinates_1", type=FieldType.FLOAT, python_type=float
        )
        coordinates_field = USRField(
            name="coordinates",
            type=FieldType.TUPLE,
            python_type=tuple,
            union_types=[coord_inner_0, coord_inner_1],
            description="Lat/Lon pair",
        )

        # record: tuple[str, int, bool]
        rec_inner_0 = USRField(name="record_0", type=FieldType.STRING, python_type=str)
        rec_inner_1 = USRField(name="record_1", type=FieldType.INTEGER, python_type=int)
        rec_inner_2 = USRField(
            name="record_2", type=FieldType.BOOLEAN, python_type=bool
        )
        record_field = USRField(
            name="record",
            type=FieldType.TUPLE,
            python_type=tuple,
            union_types=[rec_inner_0, rec_inner_1, rec_inner_2],
            description="A heterogeneous record",
        )

        return USRSchema(
            name="TupleTest",
            fields=[coordinates_field, record_field],
            description="Schema with tuple fields",
        )

    def test_pydantic_tuple(self):
        """Test Pydantic generator produces tuple[float, float] and tuple[str, int, bool]"""
        schema = self._make_tuple_schema()
        generator = PydanticGenerator()
        file_content = generator.generate_file(schema)

        assert "tuple[float, float]" in file_content
        assert "tuple[str, int, bool]" in file_content
        compile(file_content, "<test>", "exec")

    def test_zod_tuple(self):
        """Test Zod generator produces z.tuple([z.number(), z.number()])"""
        schema = self._make_tuple_schema()
        generator = ZodGenerator()
        file_content = generator.generate_file(schema)

        assert "z.tuple([z.number(), z.number()])" in file_content
        assert "z.tuple([z.string(), z.number().int(), z.boolean()])" in file_content

    def test_jsonschema_tuple(self):
        """Test JSON Schema generator produces prefixItems"""
        schema = self._make_tuple_schema()
        generator = JsonSchemaGenerator()
        file_content = generator.generate_file(schema)

        schema_data = json.loads(file_content)
        tuple_test = schema_data["$defs"]["TupleTest"]

        # coordinates should have prefixItems with two number types
        coords_prop = tuple_test["properties"]["coordinates"]
        assert coords_prop["type"] == "array"
        assert "prefixItems" in coords_prop
        assert len(coords_prop["prefixItems"]) == 2
        assert coords_prop["prefixItems"][0]["type"] == "number"
        assert coords_prop["prefixItems"][1]["type"] == "number"
        assert coords_prop["items"] is False

        # record should have prefixItems with three types
        record_prop = tuple_test["properties"]["record"]
        assert record_prop["type"] == "array"
        assert len(record_prop["prefixItems"]) == 3
        assert record_prop["prefixItems"][0]["type"] == "string"
        assert record_prop["prefixItems"][1]["type"] == "integer"
        assert record_prop["prefixItems"][2]["type"] == "boolean"
        assert record_prop["items"] is False

    def test_kotlin_tuple(self):
        """Test Kotlin generates Pair<Double, Double> for 2-element tuple"""
        schema = self._make_tuple_schema()
        generator = KotlinGenerator()
        file_content = generator.generate_file(schema)

        assert "Pair<Double, Double>" in file_content
        # 3-element tuple should use Triple
        assert "Triple<String, Long, Boolean>" in file_content

    def test_dataclasses_tuple(self):
        """Test Dataclasses generator produces tuple[float, float]"""
        schema = self._make_tuple_schema()
        generator = DataclassesGenerator()
        file_content = generator.generate_file(schema)

        assert "tuple[float, float]" in file_content
        assert "tuple[str, int, bool]" in file_content
        compile(file_content, "<test>", "exec")

    def test_typeddict_tuple(self):
        """Test TypedDict generator produces tuple[float, float]"""
        schema = self._make_tuple_schema()
        generator = TypedDictGenerator()
        file_content = generator.generate_file(schema)

        assert "tuple[float, float]" in file_content
        assert "tuple[str, int, bool]" in file_content
        compile(file_content, "<test>", "exec")

    def test_sqlalchemy_tuple(self):
        """Test SQLAlchemy generator uses JSON for tuple fields"""
        schema = self._make_tuple_schema()
        generator = SqlAlchemyGenerator()
        file_content = generator.generate_file(schema)

        assert "JSON" in file_content

    def test_jackson_tuple(self):
        """Test Jackson generator uses List<Object> for tuple fields"""
        schema = self._make_tuple_schema()
        generator = JacksonGenerator()
        file_content = generator.generate_file(schema)

        assert "List<Object>" in file_content

    def test_pathway_tuple(self):
        """Test Pathway generator uses tuple comment"""
        schema = self._make_tuple_schema()
        generator = PathwayGenerator()
        file_content = generator.generate_file(schema)

        assert "pw.ColumnExpression  # tuple" in file_content


class TestSelfReferentialTypes:
    """Test self-referential (recursive) type support across generators"""

    @pytest.fixture
    def tree_node_schema(self):
        """Create a USRSchema representing a self-referential tree node"""
        from schema_gen.core.usr import FieldType, USRField, USRSchema

        return USRSchema(
            name="TreeNode",
            fields=[
                USRField(name="value", type=FieldType.STRING, python_type=str),
                USRField(
                    name="children",
                    type=FieldType.LIST,
                    python_type=list,
                    inner_type=USRField(
                        name="children_item",
                        type=FieldType.NESTED_SCHEMA,
                        python_type=object,
                        nested_schema="TreeNode",
                    ),
                ),
                USRField(
                    name="parent",
                    type=FieldType.NESTED_SCHEMA,
                    python_type=object,
                    nested_schema="TreeNode",
                    optional=True,
                ),
            ],
            description="A tree node with recursive children",
        )

    def test_get_self_referencing_fields(self, tree_node_schema):
        """Test that get_self_referencing_fields correctly identifies self-referential fields"""
        self_ref_fields = tree_node_schema.get_self_referencing_fields()
        self_ref_names = [f.name for f in self_ref_fields]

        # 'children' references TreeNode via inner_type, 'parent' references TreeNode directly
        assert "children" in self_ref_names
        assert "parent" in self_ref_names
        assert "value" not in self_ref_names
        assert len(self_ref_fields) == 2

    def test_get_self_referencing_fields_no_self_ref(self):
        """Test that get_self_referencing_fields returns empty for non-recursive schemas"""
        from schema_gen.core.usr import FieldType, USRField, USRSchema

        schema = USRSchema(
            name="Simple",
            fields=[
                USRField(name="name", type=FieldType.STRING, python_type=str),
                USRField(name="age", type=FieldType.INTEGER, python_type=int),
            ],
        )
        assert schema.get_self_referencing_fields() == []

    def test_pydantic_self_reference(self, tree_node_schema):
        """Test that Pydantic generator produces forward references and model_rebuild()"""
        generator = PydanticGenerator()
        file_content = generator.generate_file(tree_node_schema)

        # Should use forward reference string for nested self-references
        assert '"TreeNode"' in file_content

        # Should include model_rebuild() call for resolving forward references
        assert "TreeNode.model_rebuild()" in file_content

        # Should still compile as valid Python
        compile(file_content, "<test>", "exec")

    def test_jsonschema_self_reference(self, tree_node_schema):
        """Test that JSON Schema generator produces proper $ref for self-references"""
        generator = JsonSchemaGenerator()
        file_content = generator.generate_file(tree_node_schema)

        schema_data = json.loads(file_content)

        # The TreeNode definition should exist in $defs
        assert "TreeNode" in schema_data["$defs"]

        tree_def = schema_data["$defs"]["TreeNode"]

        # 'children' should be an array with items referencing TreeNode
        children_prop = tree_def["properties"]["children"]
        assert children_prop["type"] == "array"
        assert children_prop["items"]["$ref"] == "#/$defs/TreeNode"

        # 'parent' should reference TreeNode directly
        parent_prop = tree_def["properties"]["parent"]
        assert parent_prop["$ref"] == "#/$defs/TreeNode"

    def test_zod_self_reference(self, tree_node_schema):
        """Test that Zod generator uses z.lazy() for self-referential fields"""
        generator = ZodGenerator()
        file_content = generator.generate_file(tree_node_schema)

        # Self-referential fields should use z.lazy()
        assert "z.lazy(() => TreeNodeSchema)" in file_content

        # The children field should wrap the lazy reference in z.array()
        assert "z.array(z.lazy(() => TreeNodeSchema))" in file_content

    def test_graphql_self_reference(self, tree_node_schema):
        """Test that GraphQL generator handles self-referential types correctly"""
        generator = GraphQLGenerator()
        file_content = generator.generate_file(tree_node_schema)

        # Should contain the type definition
        assert "type TreeNode {" in file_content

        # Children should be a list of TreeNode
        assert "[TreeNode]" in file_content

        # Parent should be an optional TreeNode
        assert "parent: TreeNode" in file_content


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
