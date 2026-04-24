"""Tests for the Markdown docs generator."""

from enum import Enum
from pathlib import Path

from schema_gen import Config, Field, Schema
from schema_gen.core.schema import SchemaRegistry
from schema_gen.generators.docs_generator import DocsGenerator
from schema_gen.parsers.schema_parser import SchemaParser


class _Status(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class TestDocsFieldTable:
    def setup_method(self):
        SchemaRegistry._schemas.clear()

    def test_field_table_rendered(self):
        @Schema
        class User:
            """A user account."""

            name: str = Field(max_length=100, description="Full name")
            age: int | None = Field(default=None, description="User age")

        schema = SchemaParser().parse_schema(User)
        md = DocsGenerator().generate_file(schema)

        assert "# User" in md
        assert "> A user account." in md
        assert "| Field | Type | Required | Default | Description |" in md
        assert "| name |" in md
        assert "| yes |" in md  # name is required
        assert "| age |" in md
        assert "| no |" in md  # age is optional
        assert "| None |" in md  # age default
        assert "Full name" in md
        assert "User age" in md


class TestDocsEnumSection:
    def setup_method(self):
        SchemaRegistry._schemas.clear()

    def test_enum_table_rendered(self):
        @Schema
        class Order:
            status: _Status = Field(description="Current status")

        schema = SchemaParser().parse_schema(Order)
        md = DocsGenerator().generate_file(schema)

        assert "## Enums" in md
        assert "### _Status" in md
        assert "| ACTIVE | active |" in md
        assert "| INACTIVE | inactive |" in md


class TestDocsVariants:
    def setup_method(self):
        SchemaRegistry._schemas.clear()

    def test_variants_section(self):
        @Schema
        class Item:
            id: int = Field(description="ID")
            name: str = Field(description="Name")
            price: float = Field(description="Price")

            class Variants:
                create_request = ["name", "price"]
                public_response = ["id", "name"]

        schema = SchemaParser().parse_schema(Item)
        md = DocsGenerator().generate_file(schema)

        assert "## Variants" in md
        assert "### ItemCreateRequest" in md
        assert "name, price" in md
        assert "### ItemPublicResponse" in md
        assert "id, name" in md


class TestDocsCrossReferences:
    def setup_method(self):
        SchemaRegistry._schemas.clear()

    def test_nested_type_linked(self):
        @Schema
        class Address:
            street: str = Field(description="Street")

        @Schema
        class Person:
            name: str = Field(description="Name")
            address: Address = Field(description="Home address")

        schema = SchemaParser().parse_schema(Person)
        md = DocsGenerator().generate_file(schema)

        assert "## Related Types" in md
        assert "[Address](address.md)" in md
        # Type column should also link
        assert "[Address](address.md)" in md


class TestDocsIndex:
    def setup_method(self):
        SchemaRegistry._schemas.clear()

    def test_index_page(self):
        @Schema
        class Alpha:
            """First schema."""

            x: int = Field(description="x")

        @Schema
        class Beta:
            """Second schema."""

            y: str = Field(description="y")
            status: _Status = Field(description="status")

        schemas = SchemaParser().parse_all_schemas()
        gen = DocsGenerator()
        md = gen.generate_index(schemas, Path("/tmp"))

        assert "# Schema Reference" in md
        assert "## Schemas" in md
        assert "[Alpha](alpha.md)" in md
        assert "[Beta](beta.md)" in md
        assert "First schema." in md
        assert "## Enums" in md
        assert "_Status" in md
        assert "Beta" in md  # used by


class TestDocsConfigTitle:
    def setup_method(self):
        SchemaRegistry._schemas.clear()

    def test_custom_title(self):
        @Schema
        class Foo:
            x: int = Field(description="x")

        schemas = SchemaParser().parse_all_schemas()
        config = Config(docs={"title": "TradingCore Contract Reference"})
        gen = DocsGenerator(config=config)
        md = gen.generate_index(schemas, Path("/tmp"))

        assert "# TradingCore Contract Reference" in md


class TestDocsRequiredVsOptional:
    def setup_method(self):
        SchemaRegistry._schemas.clear()

    def test_required_and_optional_fields(self):
        @Schema
        class Mixed:
            required_field: str = Field(description="must provide")
            optional_field: int | None = Field(default=None, description="optional")
            with_default: str = Field(default="hello", description="has default")
            with_factory: list[str] = Field(
                default_factory=list, description="factory default"
            )

        schema = SchemaParser().parse_schema(Mixed)
        md = DocsGenerator().generate_file(schema)

        lines = md.splitlines()
        for line in lines:
            if "| required_field |" in line:
                assert "| yes |" in line
            if "| optional_field |" in line:
                assert "| no |" in line
            if "| with_default |" in line:
                assert "| no |" in line  # has default, not required
                assert '"hello"' in line
            if "| with_factory |" in line:
                assert "| no |" in line
                assert "list()" in line
