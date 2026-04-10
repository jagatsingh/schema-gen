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

    def test_recursive_struct_uses_box_for_direct_self_reference(self):
        """Direct self-reference (not via Vec) must use Box<T> to avoid
        Rust E0072: recursive type has infinite size."""
        schema = USRSchema(
            name="TreeNode",
            fields=[
                USRField(name="value", type=FieldType.INTEGER, python_type=int),
                USRField(
                    name="parent",
                    type=FieldType.NESTED_SCHEMA,
                    python_type=str,
                    nested_schema="TreeNode",
                    optional=True,
                ),
            ],
        )
        out = RustGenerator().generate_file(schema)

        assert "pub parent: Option<Box<TreeNode>>," in out
        # Must NOT be Option<TreeNode> — that's E0072.
        assert "Option<TreeNode>," not in out

    def test_recursive_struct_vec_does_not_use_box(self):
        """Vec<TreeNode> is already heap-allocated — no Box needed."""
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

        assert "pub children: Vec<TreeNode>," in out
        assert "Box<TreeNode>" not in out

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
        # dict[str, Any] should produce serde_json::Value, not HashMap
        assert "pub attributes: serde_json::Value," in out
        assert "pub created_at: chrono::DateTime<chrono::Utc>," in out
        assert "pub event_id: uuid::Uuid," in out
        assert "pub price: rust_decimal::Decimal," in out

    # ------------------------------------------------------------------
    # 7b. dict[str, Any] vs dict[str, T] in Rust
    # ------------------------------------------------------------------

    def test_dict_str_any_produces_serde_json_value(self):
        """dict[str, Any] should generate serde_json::Value, not HashMap."""

        @Schema
        class Config:
            settings: dict[str, Any]

        schema = SchemaParser().parse_schema(Config)
        out = RustGenerator().generate_file(schema)

        assert "pub settings: serde_json::Value," in out
        # HashMap should NOT be imported when the only dict is dict[str, Any]
        assert "use std::collections::HashMap;" not in out

    def test_dict_str_specific_type_produces_hashmap(self):
        """dict[str, int] should generate HashMap<String, i64>."""

        @Schema
        class Scores:
            values: dict[str, int]

        schema = SchemaParser().parse_schema(Scores)
        out = RustGenerator().generate_file(schema)

        assert "pub values: HashMap<String, i64>," in out
        assert "use std::collections::HashMap;" in out

    def test_dict_str_nested_type_produces_hashmap(self):
        """dict[str, list[str]] should generate HashMap<String, Vec<String>>."""

        @Schema
        class TagMap:
            tags: dict[str, list[str]]

        schema = SchemaParser().parse_schema(TagMap)
        out = RustGenerator().generate_file(schema)

        assert "pub tags: HashMap<String, Vec<String>>," in out
        assert "use std::collections::HashMap;" in out

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


# ------------------------------------------------------------------
# _snake_case helper — Fix #3: leading underscores
# ------------------------------------------------------------------


class TestSnakeCase:
    """The _snake_case helper must strip leading underscores so module
    names don't start with __ (Python-private convention has no place
    in Rust module names)."""

    def test_single_leading_underscore(self):
        from schema_gen.generators.rust_generator import _snake_case

        assert _snake_case("_CeLeg") == "ce_leg"

    def test_double_leading_underscore(self):
        from schema_gen.generators.rust_generator import _snake_case

        assert _snake_case("__DoublePrivate") == "double_private"

    def test_no_leading_underscore_unchanged(self):
        from schema_gen.generators.rust_generator import _snake_case

        assert _snake_case("OrderRequest") == "order_request"

    def test_already_snake_case(self):
        from schema_gen.generators.rust_generator import _snake_case

        assert _snake_case("order_request") == "order_request"


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
    with caplog.at_level(
        logging.WARNING, logger="schema_gen.generators.rust_generator"
    ):
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
    with caplog.at_level(
        logging.WARNING, logger="schema_gen.generators.rust_generator"
    ):
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


class _Side(StrEnum):
    BUY = "buy"
    SELL = "sell"


@Schema
class OrderAlphaForC1:
    side: _Side
    qty: int


@Schema
class OrderBetaForC1:
    side: _Side
    price: float


@Schema
class PositionLegForC2:
    symbol: str
    qty: int


@Schema
class PositionForC2:
    account: str
    leg: PositionLegForC2


@Schema
class _CargoTest:
    id: int


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


# ----------------------------------------------------------------------
# Fix #C1 + #C2 + #C3: common.rs dedup, cross-module use, Cargo.toml
# ----------------------------------------------------------------------


def test_engine_emits_common_rs_and_dedups_enums(tmp_path):
    """Fix #C1: an enum referenced by multiple schemas should be emitted
    exactly once, in ``common.rs``."""
    from schema_gen.core.config import Config
    from schema_gen.core.generator import SchemaGenerationEngine

    SchemaRegistry._schemas.clear()
    SchemaRegistry.register(OrderAlphaForC1)
    SchemaRegistry.register(OrderBetaForC1)

    out_dir = tmp_path / "out"
    config = Config(
        input_dir=str(tmp_path / "schemas"),
        output_dir=str(out_dir),
        targets=["rust"],
    )
    SchemaGenerationEngine(config).generate_all()

    rust_dir = out_dir / "rust"
    common = (rust_dir / "common.rs").read_text()
    assert "pub enum _Side" in common
    assert 'rename = "buy"' in common

    alpha = (rust_dir / "order_alpha_for_c1.rs").read_text()
    beta = (rust_dir / "order_beta_for_c1.rs").read_text()

    # Enum emitted exactly once — neither per-schema file defines _Side.
    assert "pub enum _Side" not in alpha
    assert "pub enum _Side" not in beta
    # Both files pull the enum in via common.
    assert "use super::common::*;" in alpha
    assert "use super::common::*;" in beta
    # lib.rs exposes common too.
    lib = (rust_dir / "lib.rs").read_text()
    assert "pub mod common;" in lib
    assert "pub use common::*;" in lib


def test_engine_emits_cross_module_use_for_nested_schema(tmp_path):
    """Fix #C2: Schema B referencing Schema A gets
    ``use super::schema_a::SchemaA;`` at the top of schema_b.rs."""
    from schema_gen.core.config import Config
    from schema_gen.core.generator import SchemaGenerationEngine

    SchemaRegistry._schemas.clear()
    SchemaRegistry.register(PositionLegForC2)
    SchemaRegistry.register(PositionForC2)

    out_dir = tmp_path / "out"
    config = Config(
        input_dir=str(tmp_path / "schemas"),
        output_dir=str(out_dir),
        targets=["rust"],
    )
    SchemaGenerationEngine(config).generate_all()

    position = (out_dir / "rust" / "position_for_c2.rs").read_text()
    assert "use super::position_leg_for_c2::PositionLegForC2;" in position


def test_engine_emits_cargo_toml(tmp_path):
    """Fix #C3: ``Cargo.toml`` is written alongside the .rs files."""
    from schema_gen.core.config import Config
    from schema_gen.core.generator import SchemaGenerationEngine

    SchemaRegistry._schemas.clear()
    SchemaRegistry.register(_CargoTest)

    out_dir = tmp_path / "out"
    config = Config(
        input_dir=str(tmp_path / "schemas"),
        output_dir=str(out_dir),
        targets=["rust"],
    )
    SchemaGenerationEngine(config).generate_all()

    cargo = (out_dir / "rust" / "Cargo.toml").read_text()
    assert "[package]" in cargo
    assert 'name = "schema-gen-generated-contracts"' in cargo
    assert "[lib]" in cargo
    assert 'path = "lib.rs"' in cargo
    assert "[dependencies]" in cargo
    assert 'serde = { version = "1"' in cargo
    assert "chrono = " in cargo
    assert 'schemars = "0.8"' in cargo


def test_engine_cargo_toml_overrides(tmp_path):
    """Fix #C3: ``Config.rust`` overrides crate metadata + extra deps."""
    from schema_gen.core.config import Config
    from schema_gen.core.generator import SchemaGenerationEngine

    SchemaRegistry._schemas.clear()
    SchemaRegistry.register(_CargoTest)

    out_dir = tmp_path / "out"
    config = Config(
        input_dir=str(tmp_path / "schemas"),
        output_dir=str(out_dir),
        targets=["rust"],
        rust={
            "crate_name": "my-contracts",
            "crate_version": "1.2.3",
            "edition": "2024",
            "extra_deps": {"thiserror": "1.0"},
        },
    )
    SchemaGenerationEngine(config).generate_all()

    cargo = (out_dir / "rust" / "Cargo.toml").read_text()
    assert 'name = "my-contracts"' in cargo
    assert 'version = "1.2.3"' in cargo
    assert 'edition = "2024"' in cargo
    assert 'thiserror = "1.0"' in cargo


def test_engine_cargo_toml_can_be_disabled(tmp_path):
    from schema_gen.core.config import Config
    from schema_gen.core.generator import SchemaGenerationEngine

    SchemaRegistry._schemas.clear()
    SchemaRegistry.register(_CargoTest)

    out_dir = tmp_path / "out"
    config = Config(
        input_dir=str(tmp_path / "schemas"),
        output_dir=str(out_dir),
        targets=["rust"],
        rust={"emit_cargo_toml": False},
    )
    SchemaGenerationEngine(config).generate_all()

    assert not (out_dir / "rust" / "Cargo.toml").exists()


# ----------------------------------------------------------------------
# Per-field integer / float width override (#19)
# ----------------------------------------------------------------------


class TestRustWidthOverride:
    """Field(rust={"type": "u32"}) controls Rust integer / float widths."""

    def setup_method(self):
        SchemaRegistry._schemas.clear()

    def test_integer_width_override_u32(self):
        @Schema
        class OrderRequest:
            quantity: int = Field(rust={"type": "u32"})

        usr = SchemaParser().parse_schema(OrderRequest)
        out = RustGenerator().generate_file(usr)
        assert "pub quantity: u32," in out
        assert "pub quantity: i64," not in out

    def test_integer_width_override_u16_leg_index(self):
        @Schema
        class Leg:
            leg_index: int = Field(rust={"type": "u16"})

        usr = SchemaParser().parse_schema(Leg)
        out = RustGenerator().generate_file(usr)
        assert "pub leg_index: u16," in out

    def test_integer_width_override_invalid_type(self, caplog):
        @Schema
        class Bogus:
            count: int = Field(rust={"type": "bogus"})

        usr = SchemaParser().parse_schema(Bogus)
        import logging

        with caplog.at_level(logging.WARNING):
            out = RustGenerator().generate_file(usr)
        assert "pub count: i64," in out
        assert any("bogus" in rec.message for rec in caplog.records)

    def test_float_width_override_f32(self):
        @Schema
        class Pricing:
            price: float = Field(rust={"type": "f32"})

        usr = SchemaParser().parse_schema(Pricing)
        out = RustGenerator().generate_file(usr)
        assert "pub price: f32," in out
        assert "pub price: f64," not in out

    def test_float_width_override_invalid_type(self, caplog):
        @Schema
        class BadFloat:
            x: float = Field(rust={"type": "decimal"})

        usr = SchemaParser().parse_schema(BadFloat)
        import logging

        with caplog.at_level(logging.WARNING):
            out = RustGenerator().generate_file(usr)
        assert "pub x: f64," in out
        assert any("decimal" in rec.message for rec in caplog.records)

    def test_integer_default_still_i64(self):
        @Schema
        class Plain:
            count: int

        usr = SchemaParser().parse_schema(Plain)
        out = RustGenerator().generate_file(usr)
        assert "pub count: i64," in out

    def test_optional_integer_width_override(self):
        @Schema
        class OptOrder:
            quantity: int | None = Field(default=None, rust={"type": "u32"})

        usr = SchemaParser().parse_schema(OptOrder)
        out = RustGenerator().generate_file(usr)
        assert "pub quantity: Option<u32>," in out


# ----------------------------------------------------------------------
# Enum-level SerdeMeta support
# ----------------------------------------------------------------------


# Defined at module scope so the @Schema decorator's get_type_hints can
# resolve forward references.
class _OrderStatus(str, Enum):
    PENDING = "pending"
    FILLED = "filled"
    CANCELLED = "cancelled"

    class SerdeMeta:
        raw_code = (
            "impl _OrderStatus {\n"
            "    pub fn is_terminal(&self) -> bool {\n"
            "        matches!(self, Self::Filled | Self::Cancelled)\n"
            "    }\n"
            "}"
        )


class _Priority(str, Enum):
    LOW = "low"
    HIGH = "high"

    class SerdeMeta:
        derives = ["Ord", "PartialOrd"]


class _PlainColor(str, Enum):
    RED = "red"
    BLUE = "blue"


class _Mode2(str, Enum):
    AUTO = "auto"
    MANUAL = "manual"

    class SerdeMeta:
        raw_code = (
            "impl _Mode2 {\n"
            "    pub fn is_auto(&self) -> bool {\n"
            "        matches!(self, Self::Auto)\n"
            "    }\n"
            "}"
        )


@Schema
class _OrderEnumHolder:
    status: _OrderStatus


@Schema
class _PrioHolder:
    priority: _Priority


@Schema
class _PlainColorHolder:
    color: _PlainColor


@Schema
class _Mode2Holder:
    mode: _Mode2


class TestRustEnumMeta:
    """SerdeMeta on Enum classes injects extra derives + raw_code impl
    blocks into the generated Rust enum."""

    def setup_method(self):
        SchemaRegistry._schemas.clear()

    def test_enum_serde_meta_raw_code(self):
        usr = SchemaParser().parse_schema(_OrderEnumHolder)
        out = RustGenerator().generate_file(usr)
        assert "impl _OrderStatus {" in out
        assert "pub fn is_terminal(&self) -> bool" in out
        assert "matches!(self, Self::Filled | Self::Cancelled)" in out

    def test_enum_serde_meta_extra_derives(self):
        usr = SchemaParser().parse_schema(_PrioHolder)
        out = RustGenerator().generate_file(usr)
        all_derive_lines = [
            line for line in out.splitlines() if line.startswith("#[derive(")
        ]
        # The enum derive line is the first one emitted.
        enum_derive = all_derive_lines[0]
        assert "Ord" in enum_derive
        assert "PartialOrd" in enum_derive

    def test_enum_without_meta_unchanged(self):
        # Regression: a plain enum with no SerdeMeta still generates
        # exactly the same output it always has.
        usr = SchemaParser().parse_schema(_PlainColorHolder)
        out = RustGenerator().generate_file(usr)
        assert "pub enum _PlainColor {" in out
        assert "impl _PlainColor" not in out  # no impl block when no raw_code

    def test_enum_serde_meta_via_common_module(self, tmp_path):
        """End-to-end via the engine: shared enum lands in common.rs and
        carries its raw_code impl block."""
        from schema_gen.core.config import Config
        from schema_gen.core.generator import SchemaGenerationEngine

        SchemaRegistry._schemas.clear()
        SchemaRegistry.register(_Mode2Holder)

        out_dir = tmp_path / "out"
        config = Config(
            input_dir=str(tmp_path / "schemas"),
            output_dir=str(out_dir),
            targets=["rust"],
        )
        SchemaGenerationEngine(config).generate_all()

        common_rs = (out_dir / "rust" / "common.rs").read_text()
        assert "pub enum _Mode2 {" in common_rs
        assert "impl _Mode2 {" in common_rs
        assert "pub fn is_auto(&self) -> bool" in common_rs


# ----------------------------------------------------------------------
# Discriminated unions (#18)
# ----------------------------------------------------------------------

from typing import Annotated, Literal  # noqa: E402


@Schema
class _CeLeg:
    option_type: Literal["CE"]
    strike: float


@Schema
class _PeLeg:
    option_type: Literal["PE"]
    strike: float


@Schema
class _OtherLeg:
    option_type: Literal["XX"]
    strike: float


@Schema
class _DiscriminatedOrder:
    leg: Annotated[_CeLeg | _PeLeg, Field(discriminator="option_type")]


@Schema
class _DiscriminatedThreeWay:
    leg: Annotated[_CeLeg | _PeLeg | _OtherLeg, Field(discriminator="option_type")]


@Schema
class _PlainUnionOrder:
    leg: _CeLeg | _PeLeg


class TestRustDiscriminatedUnion:
    """Annotated[Union[A, B], Field(discriminator="...")] → serde tagged enum."""

    def setup_method(self):
        # Other test classes wipe SchemaRegistry in their setup_method, so
        # re-register the variant @Schema classes the parser needs to look
        # up to resolve Literal tags.
        SchemaRegistry._schemas.clear()
        for cls in (
            _CeLeg,
            _PeLeg,
            _OtherLeg,
            _DiscriminatedOrder,
            _DiscriminatedThreeWay,
            _PlainUnionOrder,
        ):
            SchemaRegistry.register(cls)

    def test_discriminated_union_two_variants(self):
        usr = SchemaParser().parse_schema(_DiscriminatedOrder)
        out = RustGenerator().generate_file(usr)
        assert 'tag = "option_type"' in out
        assert "pub enum _DiscriminatedOrderLeg {" in out
        assert "Ce(_CeLeg)" in out
        assert "Pe(_PeLeg)" in out
        assert "pub leg: _DiscriminatedOrderLeg," in out
        assert "serde_json::Value" not in out.split("pub leg:")[1].split(",")[0]

    def test_discriminated_union_three_variants(self):
        usr = SchemaParser().parse_schema(_DiscriminatedThreeWay)
        out = RustGenerator().generate_file(usr)
        assert "pub enum _DiscriminatedThreeWayLeg {" in out
        assert "Ce(_CeLeg)" in out
        assert "Pe(_PeLeg)" in out
        assert "Xx(_OtherLeg)" in out

    def test_discriminated_union_uses_literal_tag(self):
        """Variant identifier comes from the Literal value, with rename
        if the Pascal-cased identifier differs from the wire tag."""
        usr = SchemaParser().parse_schema(_DiscriminatedOrder)
        out = RustGenerator().generate_file(usr)
        # "CE".capitalize() == "Ce", so a rename is needed to preserve
        # the wire value "CE".
        assert '#[serde(rename = "CE")]' in out
        assert '#[serde(rename = "PE")]' in out

    def test_plain_union_still_falls_back_to_value(self, caplog):
        import logging

        usr = SchemaParser().parse_schema(_PlainUnionOrder)
        with caplog.at_level(logging.WARNING):
            out = RustGenerator().generate_file(usr)
        assert "pub leg: serde_json::Value," in out
        assert any("union field 'leg'" in rec.message for rec in caplog.records)


# ------------------------------------------------------------------
# Fix #4: strict discriminator resolution errors
# ------------------------------------------------------------------


# Module-level fixtures for Fix #4 discriminator error tests.
# @Schema classes must be at module scope for forward-reference resolution.


@Schema
class _DiscErrAVariant:
    kind: Literal["A"]
    x: int


@Schema
class _DiscErrBVariant:
    kind: Literal["B"]
    x: int


@Schema
class _BadDiscHolder:
    leg: Annotated[_DiscErrAVariant | _DiscErrBVariant, Field(discriminator="typ")]


@Schema
class _StrTagVariant:
    kind: str
    x: int


@Schema
class _NonLiteralHolder:
    leg: Annotated[_StrTagVariant | _DiscErrBVariant, Field(discriminator="kind")]


@Schema
class _DiscV1:
    tag: Literal["v1"]
    data: str


@Schema
class _DiscV2:
    tag: Literal["v2"]
    data: int


@Schema
class _GoodDiscHolder:
    item: Annotated[_DiscV1 | _DiscV2, Field(discriminator="tag")]


class TestDiscriminatorErrors:
    """Discriminator resolution errors must raise ValueError, not silently
    fall back to plain Union / serde_json::Value."""

    def setup_method(self):
        SchemaRegistry._schemas.clear()
        for cls in (
            _DiscErrAVariant,
            _DiscErrBVariant,
            _BadDiscHolder,
            _StrTagVariant,
            _NonLiteralHolder,
            _DiscV1,
            _DiscV2,
            _GoodDiscHolder,
        ):
            SchemaRegistry.register(cls)

    def test_bad_discriminator_field_name_raises(self):
        """Typo in discriminator field name must raise, not silently degrade."""
        import pytest

        with pytest.raises(ValueError, match="has no discriminator field 'typ'"):
            SchemaParser().parse_schema(_BadDiscHolder)

    def test_non_literal_discriminator_raises(self):
        """Discriminator field must be Literal[...], not plain str."""
        import pytest

        with pytest.raises(ValueError, match="must be Literal"):
            SchemaParser().parse_schema(_NonLiteralHolder)

    def test_correct_discriminator_still_works(self):
        """Regression: correct discriminated unions must still parse fine."""
        usr = SchemaParser().parse_schema(_GoodDiscHolder)
        assert usr.fields[0].discriminator == "tag"
        assert usr.fields[0].union_tag_values == ["v1", "v2"]
