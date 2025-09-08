"""Simple tests to verify basic functionality"""

import pytest
from schema_gen import Schema, Field
from schema_gen.core.schema import SchemaRegistry


def test_simple_field_creation():
    """Test basic field creation"""
    field = Field()
    assert field is not None
    assert field.default is None


def test_simple_schema_creation():
    """Test basic schema creation"""
    SchemaRegistry._schemas.clear()

    @Schema
    class TestSchema:
        name: str = Field()

    assert TestSchema._schema_name == "TestSchema"
    assert "name" in TestSchema._schema_fields
    assert TestSchema in SchemaRegistry._schemas.values()


if __name__ == "__main__":
    test_simple_field_creation()
    test_simple_schema_creation()
    print("✅ Basic tests passed!")
