"""Example user schema definition"""

from schema_gen import Schema, Field
from typing import Optional
from datetime import datetime


@Schema
class User:
    """User schema for the application"""

    id: int = Field(
        primary_key=True, auto_increment=True, description="Unique identifier"
    )

    name: str = Field(max_length=100, min_length=2, description="User's full name")

    email: str = Field(
        unique=True, format="email", index=True, description="User's email address"
    )

    age: Optional[int] = Field(
        default=None, min_value=13, max_value=120, description="User's age"
    )

    created_at: datetime = Field(
        auto_now_add=True, index=True, description="Account creation timestamp"
    )

    # Define output variants for different use cases
    class Variants:
        create_request = ["name", "email", "age"]  # Exclude auto-generated fields
        update_request = ["name", "email", "age"]  # All optional for updates
        public_response = ["id", "name", "age", "created_at"]  # Exclude email
        full_response = ["id", "name", "email", "age", "created_at"]  # All fields


if __name__ == "__main__":
    # Test schema registration
    from schema_gen.core.schema import SchemaRegistry

    print("Registered schemas:")
    for name, schema_cls in SchemaRegistry.get_all_schemas().items():
        print(f"  {name}: {schema_cls}")
        print(f"    Fields: {list(schema_cls._schema_fields.keys())}")

    print("\nUser schema fields:")
    for field_name, field_data in User._schema_fields.items():
        field_info = field_data["field_info"]
        print(f"  {field_name}: {field_data['type']} = {field_info}")
