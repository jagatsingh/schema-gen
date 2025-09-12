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
        assert "from pydantic import BaseModel, Field" in file_content
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
        assert "from sqlalchemy import" in file_content
        assert "from sqlalchemy.orm import" in file_content
        assert '__tablename__ = "test_user"' in file_content
        assert "Column(" in file_content
        assert "Integer, primary_key=True" in file_content

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
        assert "class TestUser(TypedDict, total=False):" in file_content
        assert "class TestUserCreateRequest(TypedDict, total=False):" in file_content
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

        # Verify field constraints
        user_schema = schema_data["$defs"]["TestUser"]
        assert user_schema["properties"]["name"]["minLength"] == 2
        assert user_schema["properties"]["name"]["maxLength"] == 100
        assert user_schema["properties"]["email"]["format"] == "email"
        assert user_schema["properties"]["age"]["minimum"] == 13
        assert user_schema["properties"]["age"]["maximum"] == 120

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

    def test_jackson_generator(self, comprehensive_schema):
        """Test Jackson generator"""
        generator = JacksonGenerator()

        file_content = generator.generate_file(comprehensive_schema)

        # Verify content
        assert "package com.example.testuser;" in file_content
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

    def test_kotlin_generator(self, comprehensive_schema):
        """Test Kotlin generator"""
        generator = KotlinGenerator()

        file_content = generator.generate_file(comprehensive_schema)

        # Verify content
        assert "package com.example.testuser" in file_content
        assert "data class TestUser(" in file_content
        assert "data class TestUserCreateRequest(" in file_content
        assert "@Serializable" in file_content
        assert "import kotlinx.serialization.Serializable" in file_content
        assert "import kotlinx.datetime.Instant" in file_content
        assert "val id: Long" in file_content
        assert "val name: String" in file_content
        assert "val age: Int? = null" in file_content
        assert "val created_at: Instant" in file_content


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
        assert "List[str]" in pydantic_result
        assert "Optional[List[int]]" in pydantic_result

        kotlin_gen = KotlinGenerator()
        kotlin_result = kotlin_gen.generate_file(schema)
        assert "List<String>" in kotlin_result
        assert "List<Long>" in kotlin_result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
