"""Tests for the Rust Serde generator (#12)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum, StrEnum
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


class _Exchange(str, Enum):
    """Uppercase wire values — must not be silently lowercased."""

    NSE = "NSE"
    BSE = "BSE"


class _Mode(str, Enum):
    """PascalCase values matching variant names — no rename needed."""

    Active = "Active"
    Paused = "Paused"


@Schema
class _ExchangeHolder:
    exchange: _Exchange


@Schema
class _ModeHolder:
    mode: _Mode


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
        # Per-variant renames preserve the actual Python enum value on the
        # wire; see _generate_enum for the rationale.
        assert '#[serde(rename = "active")]' in out
        assert '#[serde(rename = "suspended")]' in out
        assert '#[serde(rename = "deleted")]' in out
        assert "Debug, Clone, Copy, PartialEq, Eq, Hash" in out
        assert "pub status: _Status," in out

    def test_enum_preserves_uppercase_wire_format(self):
        """Enums whose Python values use uppercase must keep that casing
        in the Rust wire format — no silent snake_case transform."""
        schema = SchemaParser().parse_schema(_ExchangeHolder)
        out = RustGenerator().generate_file(schema)

        assert "pub enum _Exchange {" in out
        assert '#[serde(rename = "NSE")]' in out
        assert '#[serde(rename = "BSE")]' in out
        # Must NOT have a default rename_all that would lowercase these.
        assert 'rename_all = "snake_case"' not in out

    def test_enum_omits_rename_when_variant_matches_value(self):
        """If the PascalCase variant name already equals the wire value,
        no redundant #[serde(rename)] attribute is emitted."""
        schema = SchemaParser().parse_schema(_ModeHolder)
        out = RustGenerator().generate_file(schema)

        # Variant present, no redundant rename.
        assert "Active," in out
        assert "Paused," in out
        assert '#[serde(rename = "Active")]' not in out
        assert '#[serde(rename = "Paused")]' not in out

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

    def test_variants_emit_separate_structs(self):
        """A variant that drops a required non-optional field without an
        explicit default must still emit both structs, but the ``From`` impl
        is skipped because ``Default::default()`` wouldn't compile for the
        missing ``id: i64`` field in the general case.
        """

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
        # Missing required field without explicit default → no From impl.
        assert "impl From<ProductCreateRequest> for Product {" not in out

    def test_variant_from_impl_emitted_when_missing_fields_are_optional(self):
        """If every missing field is optional, the ``From`` impl is safe
        to emit because all gaps are filled with ``None``."""

        @Schema
        class Profile:
            name: str
            bio: str | None = Field(default=None)
            avatar_url: str | None = Field(default=None)

            class Variants:
                minimal = ["name"]

        schema = SchemaParser().parse_schema(Profile)
        out = RustGenerator().generate_file(schema)

        assert "pub struct Profile {" in out
        assert "pub struct ProfileMinimal {" in out
        assert "impl From<ProfileMinimal> for Profile {" in out
        assert "name: value.name," in out
        assert "bio: None," in out
        assert "avatar_url: None," in out
        # And definitely no Default::default() sneaking in for non-Default types.
        assert "Default::default()" not in out

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


# ----------------------------------------------------------------------
# Engine integration — Fix #A1 / #A7: lib.rs, Cargo.toml, imports
# ----------------------------------------------------------------------


def test_engine_writes_lib_rs_not_init_py(tmp_path):
    """Regression for Copilot #13.1: Rust index file must be ``lib.rs``."""
    from schema_gen.core.config import Config
    from schema_gen.core.generator import SchemaGenerationEngine

    SchemaRegistry._schemas.clear()

    @Schema
    class EngineFixOrder:
        id: int
        price: float

    @Schema
    class EngineFixFill:
        id: int

    out_dir = tmp_path / "out"
    config = Config(
        input_dir=str(tmp_path / "schemas"),
        output_dir=str(out_dir),
        targets=["rust"],
    )
    engine = SchemaGenerationEngine(config)
    engine.generate_all()

    rust_dir = out_dir / "rust"
    lib_rs = rust_dir / "lib.rs"
    assert lib_rs.exists(), "Rust generator must write lib.rs as the index file"
    assert not (rust_dir / "__init__.py").exists()

    content = lib_rs.read_text()
    assert "pub mod engine_fix_order;" in content
    assert "pub mod engine_fix_fill;" in content
    assert "pub use engine_fix_order::*;" in content

    # And the per-schema .rs files exist too.
    assert (rust_dir / "engine_fix_order.rs").exists()
    assert (rust_dir / "engine_fix_fill.rs").exists()


# ----------------------------------------------------------------------
# Fix #A3: union type returns clean Rust (no inline comment)
# ----------------------------------------------------------------------


def test_union_field_emits_clean_rust_type(caplog):
    import logging

    schema = USRSchema(
        name="WithUnion",
        fields=[
            USRField(
                name="payload",
                type=FieldType.UNION,
                python_type=object,
                union_types=[
                    USRField(name="_", type=FieldType.INTEGER, python_type=int),
                    USRField(name="_", type=FieldType.STRING, python_type=str),
                ],
            ),
        ],
    )
    with caplog.at_level(logging.WARNING, logger="schema_gen.generators.rust_generator"):
        out = RustGenerator().generate_file(schema)

    assert "pub payload: serde_json::Value," in out
    # No inline comment corrupting the struct body.
    assert "//" not in out.split("pub payload:")[1].split("\n")[0]
    # Warning was logged.
    assert any("union" in rec.message for rec in caplog.records)


# ----------------------------------------------------------------------
# Fix #A4: reserved-word escaping in From<Variant> impl
# ----------------------------------------------------------------------


def test_reserved_word_preserved_in_from_impl():
    @Schema
    class _ReservedMsg:
        type: str = Field(default="info")
        body: str
        priority: int = Field(default=0)

        class Variants:
            minimal = ["body"]

    schema = SchemaParser().parse_schema(_ReservedMsg)
    out = RustGenerator().generate_file(schema)

    # From impl exists (type and priority both have explicit defaults).
    assert "impl From<_ReservedMsgMinimal> for _ReservedMsg {" in out
    # Reserved-word field is escaped on BOTH sides of the struct literal.
    # Since the variant omits `type`, we hit the Default::default() branch,
    # but the LHS identifier must still be r#type.
    assert "r#type: Default::default()" in out


# ----------------------------------------------------------------------
# Fix #A5: struct-level rename_all
# ----------------------------------------------------------------------


def test_struct_rename_all_valid():
    @Schema
    class CamelStruct:
        first_name: str
        last_name: str

        class SerdeMeta:
            rename_all = "camelCase"

    schema = SchemaParser().parse_schema(CamelStruct)
    out = RustGenerator().generate_file(schema)
    assert 'rename_all = "camelCase"' in out


def test_struct_rename_all_invalid_is_ignored_with_warning(caplog):
    import logging

    @Schema
    class BadStruct:
        x: int

        class SerdeMeta:
            rename_all = "nonsense"

    schema = SchemaParser().parse_schema(BadStruct)
    with caplog.at_level(logging.WARNING, logger="schema_gen.generators.rust_generator"):
        out = RustGenerator().generate_file(schema)

    assert 'rename_all = "nonsense"' not in out
    assert any("rename_all" in rec.message for rec in caplog.records)


# ----------------------------------------------------------------------
# Fix #A6: enum-level rename_all override
# ----------------------------------------------------------------------


class _EnumRenameStatus(StrEnum):
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"


@Schema
class _EnumRenameHolder:
    status: _EnumRenameStatus

    class SerdeMeta:
        rename_all = "lowercase"


def test_enum_rename_all_from_schema_meta_overrides_per_variant():
    SchemaRegistry.register(_EnumRenameHolder)
    schema = SchemaParser().parse_schema(_EnumRenameHolder)
    out = RustGenerator().generate_file(schema)

    # Enum itself picks up rename_all and skips per-variant renames.
    assert 'rename_all = "lowercase"' in out
    assert '#[serde(rename = "ACTIVE")]' not in out
    assert '#[serde(rename = "PAUSED")]' not in out
    assert "Active," in out
    assert "Paused," in out


def test_enum_without_rename_all_keeps_per_variant_renames():
    # _ExchangeHolder (module-level) has no SerdeMeta, so per-variant
    # renames are preserved — this is the default/current behavior.
    schema = SchemaParser().parse_schema(_ExchangeHolder)
    out = RustGenerator().generate_file(schema)
    assert '#[serde(rename = "NSE")]' in out
    assert '#[serde(rename = "BSE")]' in out
