"""Tests for the Rust Serde generator (#12)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from typing import Any
from uuid import UUID

from schema_gen import Field, Schema
from schema_gen.core.schema import SchemaRegistry
from schema_gen.core.usr import FieldType, USRField, USRSchema
from schema_gen.generators.rust_generator import RustGenerator
from schema_gen.parsers.schema_parser import SchemaParser


# Module-level helpers. Forward-reference resolution runs at decorator
# time, so recursive / cross-referenced @Schema classes must be defined at
# module scope (not inside test methods).
class _Status(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    DELETED = "deleted"


@Schema
class _Address:
    street: str
    city: str


@Schema
class _Customer:
    name: str
    address: _Address


class TestRustGenerator:
    """String-level assertions mirroring ``tests/test_generators.py``."""

    def setup_method(self):
        SchemaRegistry._schemas.clear()

    # ------------------------------------------------------------------
    # 1. Simple struct
    # ------------------------------------------------------------------

    def test_simple_struct(self):
        @Schema
        class User:
            """A user of the system"""

            id: int = Field(description="Unique identifier")
            name: str = Field(description="Full name")
            email: str = Field(description="Email address")
            age: int | None = Field(default=None)

        schema = SchemaParser().parse_schema(User)
        out = RustGenerator().generate_file(schema)

        assert "pub struct User {" in out
        assert "/// A user of the system" in out
        assert "pub id: i64," in out
        assert "pub name: String," in out
        assert "pub email: String," in out
        assert 'skip_serializing_if = "Option::is_none"' in out
        assert "pub age: Option<i64>," in out
        assert (
            "#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, JsonSchema)]"
            in out
        )
        assert "#[serde(deny_unknown_fields)]" in out
        assert "use serde::{Deserialize, Serialize};" in out
        assert "use schemars::JsonSchema;" in out

    # ------------------------------------------------------------------
    # 2. Enum
    # ------------------------------------------------------------------

    def test_enum_emission(self):
        @Schema
        class Account:
            id: int
            status: _Status

        schema = SchemaParser().parse_schema(Account)
        out = RustGenerator().generate_file(schema)

        assert "pub enum _Status {" in out
        assert "Active," in out
        assert "Suspended," in out
        assert "Deleted," in out
        assert '#[serde(rename_all = "snake_case")]' in out
        assert "Debug, Clone, Copy, PartialEq, Eq, Hash" in out
        assert "pub status: _Status," in out

    # ------------------------------------------------------------------
    # 3. Nested struct reference
    # ------------------------------------------------------------------

    def test_nested_struct_reference(self):
        # Re-register (setup_method cleared the registry).
        SchemaRegistry.register(_Address)
        SchemaRegistry.register(_Customer)

        schema = SchemaParser().parse_schema(_Customer)
        out = RustGenerator().generate_file(schema)

        assert "pub struct _Customer {" in out
        assert "pub address: _Address," in out

    # ------------------------------------------------------------------
    # 4. Recursive / self-referential struct
    # ------------------------------------------------------------------

    def test_recursive_struct_uses_nested_name(self):
        # Build the USRSchema directly (same pattern as the other generator
        # tests use for self-referential fixtures).
        schema = USRSchema(
            name="TreeNode",
            fields=[
                USRField(name="value", type=FieldType.INTEGER, python_type=int),
                USRField(
                    name="children",
                    type=FieldType.LIST,
                    python_type=list,
                    inner_type=USRField(
                        name="children_item",
                        type=FieldType.NESTED_SCHEMA,
                        python_type=str,
                        nested_schema="TreeNode",
                    ),
                ),
            ],
        )
        out = RustGenerator().generate_file(schema)

        assert "pub struct TreeNode {" in out
        assert "pub children: Vec<TreeNode>," in out

    # ------------------------------------------------------------------
    # 5. SerdeMeta custom code injection
    # ------------------------------------------------------------------

    def test_serde_meta_custom_code(self):
        @Schema
        class OrderStatus:
            """Lifecycle state for an order"""

            code: str

            class SerdeMeta:
                derives = ["Default"]
                imports = ["use std::fmt"]
                raw_code = (
                    "impl OrderStatus {\n"
                    "    pub fn is_terminal(&self) -> bool { false }\n"
                    "}"
                )

        schema = SchemaParser().parse_schema(OrderStatus)
        out = RustGenerator().generate_file(schema)

        assert "use std::fmt;" in out
        assert "Default" in out  # extra derive
        assert "impl OrderStatus {" in out
        assert "pub fn is_terminal(&self) -> bool { false }" in out

    # ------------------------------------------------------------------
    # 6. Variants
    # ------------------------------------------------------------------

    def test_variants_emit_separate_struct_and_from_impl(self):
        @Schema
        class Product:
            id: int = Field(primary_key=True)
            name: str
            price: float
            description: str | None = Field(default=None)

            class Variants:
                create_request = ["name", "price"]

        schema = SchemaParser().parse_schema(Product)
        out = RustGenerator().generate_file(schema)

        assert "pub struct Product {" in out
        assert "pub struct ProductCreateRequest {" in out
        assert "impl From<ProductCreateRequest> for Product {" in out
        assert "name: value.name," in out
        assert "price: value.price," in out
        # Missing Option field → None; missing required → Default::default()
        assert "description: None," in out
        assert "id: Default::default()," in out

    # ------------------------------------------------------------------
    # 7. Collection / stdlib types
    # ------------------------------------------------------------------

    def test_collection_and_stdlib_types(self):
        @Schema
        class Event:
            tags: list[str]
            attributes: dict[str, Any]
            created_at: datetime
            event_id: UUID
            price: Decimal

        schema = SchemaParser().parse_schema(Event)
        out = RustGenerator().generate_file(schema)

        assert "pub tags: Vec<String>," in out
        assert "pub attributes: HashMap<String, serde_json::Value>," in out
        assert "use std::collections::HashMap;" in out
        assert "pub created_at: chrono::DateTime<chrono::Utc>," in out
        assert "pub event_id: uuid::Uuid," in out
        assert "pub price: rust_decimal::Decimal," in out

    # ------------------------------------------------------------------
    # 8. Reserved-word field name
    # ------------------------------------------------------------------

    def test_reserved_word_field_name(self):
        @Schema
        class Message:
            type: str
            body: str

        schema = SchemaParser().parse_schema(Message)
        out = RustGenerator().generate_file(schema)

        assert "pub r#type: String," in out
        assert '#[serde(rename = "type")]' in out

    # ------------------------------------------------------------------
    # 9. Skip JsonSchema derive when config disables it
    # ------------------------------------------------------------------

    def test_json_schema_derive_opt_out(self):
        @Schema
        class Tiny:
            x: int

            class SerdeMeta:
                json_schema_derive = False

        schema = SchemaParser().parse_schema(Tiny)
        out = RustGenerator().generate_file(schema)

        assert "JsonSchema" not in out
        assert "use schemars::JsonSchema;" not in out

    def test_deny_unknown_fields_opt_out(self):
        @Schema
        class Loose:
            x: int

            class SerdeMeta:
                deny_unknown_fields = False

        schema = SchemaParser().parse_schema(Loose)
        out = RustGenerator().generate_file(schema)
        assert "#[serde(deny_unknown_fields)]" not in out

    # ------------------------------------------------------------------
    # 10. Index (lib.rs) generation
    # ------------------------------------------------------------------

    def test_index_file(self):
        @Schema
        class OrderRequest:
            id: int

        @Schema
        class FillEvent:
            id: int

        parser = SchemaParser()
        schemas = [
            parser.parse_schema(OrderRequest),
            parser.parse_schema(FillEvent),
        ]
        gen = RustGenerator()
        index = gen.generate_index(schemas, Path("."))

        assert "pub mod order_request;" in index
        assert "pub mod fill_event;" in index
        assert "pub use order_request::*;" in index
        assert "pub use fill_event::*;" in index
        # Filenames follow snake_case convention
        assert gen.get_schema_filename(schemas[0]) == "order_request.rs"
        assert gen.get_schema_filename(schemas[1]) == "fill_event.rs"


def test_rust_generator_registered_in_registry():
    from schema_gen.generators.registry import GENERATOR_REGISTRY

    assert "rust" in GENERATOR_REGISTRY
    assert GENERATOR_REGISTRY["rust"] is RustGenerator
