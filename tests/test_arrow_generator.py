"""Tests for the Arrow generators (#148)."""

import logging
from datetime import date, datetime, time
from decimal import Decimal
from uuid import UUID

import pytest

from schema_gen import Field, Schema
from schema_gen.core.schema import SchemaRegistry
from schema_gen.core.usr import FieldType, USRField
from schema_gen.generators.arrow_generator import (
    ArrowPythonGenerator,
    ArrowRustGenerator,
    _arrow_kind_for,
)
from schema_gen.parsers.schema_parser import SchemaParser


def _field(ftype: FieldType, **kwargs) -> USRField:
    """Build a bare USRField for unit-testing ``_arrow_kind_for`` directly,
    without going through the full ``@Schema``/parser pipeline."""
    return USRField(
        name=kwargs.pop("name", "f"), type=ftype, python_type=object, **kwargs
    )


class TestArrowKindForScalarTypes:
    """FieldType -> Arrow scalar type mapping (issue #148 requirement #1)."""

    @pytest.mark.parametrize(
        "ftype,expected",
        [
            (FieldType.STRING, "Utf8"),
            (FieldType.BOOLEAN, "Boolean"),
            (FieldType.INTEGER, "Int64"),
            (FieldType.FLOAT, "Float64"),
            (FieldType.DATE, "Date32"),
            (FieldType.TIME, "Time64(Microsecond)"),
            (FieldType.BYTES, "Binary"),
            (FieldType.UUID, "Utf8"),
            (FieldType.JSON, "Utf8"),
            (FieldType.LITERAL, "Utf8"),
            (FieldType.ENUM, "Utf8"),
        ],
    )
    def test_scalar_mapping(self, ftype, expected):
        kind = _arrow_kind_for(_field(ftype))
        assert kind.kind == "scalar"
        assert kind.scalar == expected

    def test_nested_schema_is_unmapped(self):
        with pytest.raises(ValueError, match="NESTED_SCHEMA"):
            _arrow_kind_for(_field(FieldType.NESTED_SCHEMA, nested_schema="Other"))

    def test_union_without_types_is_unmapped(self):
        with pytest.raises(ValueError, match="UNION"):
            _arrow_kind_for(_field(FieldType.UNION))


class TestArrowKindForDatetime:
    """DATETIME -> Timestamp with a configurable unit (default microsecond)."""

    def test_default_unit_is_microsecond(self):
        kind = _arrow_kind_for(_field(FieldType.DATETIME))
        assert kind.kind == "timestamp"
        assert kind.scalar == "microsecond"

    @pytest.mark.parametrize(
        "unit", ["second", "millisecond", "microsecond", "nanosecond"]
    )
    def test_override_via_target_config(self, unit):
        f = _field(
            FieldType.DATETIME, target_config={"arrow": {"timestamp_unit": unit}}
        )
        kind = _arrow_kind_for(f)
        assert kind.scalar == unit

    def test_invalid_unit_falls_back_to_default(self, caplog):
        f = _field(
            FieldType.DATETIME, target_config={"arrow": {"timestamp_unit": "fortnight"}}
        )
        with caplog.at_level(logging.WARNING):
            kind = _arrow_kind_for(f)
        assert kind.scalar == "microsecond"
        assert "invalid" in caplog.text.lower()


class TestArrowKindForDecimal:
    def test_default_precision_and_scale(self):
        kind = _arrow_kind_for(_field(FieldType.DECIMAL))
        assert kind.kind == "decimal"
        assert kind.precision == 38
        assert kind.scale == 9

    def test_override_via_target_config(self):
        f = _field(
            FieldType.DECIMAL, target_config={"arrow": {"precision": 10, "scale": 2}}
        )
        kind = _arrow_kind_for(f)
        assert kind.precision == 10
        assert kind.scale == 2


class TestArrowKindForDict:
    """DICT defaults to a JSON-serialized LargeUtf8 column, not a native Map
    (tradingcore#697 — see arrow_generator.py module docstring)."""

    def test_typed_dict_defaults_to_large_string(self):
        inner = _field(FieldType.FLOAT, name="value")
        f = _field(FieldType.DICT, inner_type=inner)
        kind = _arrow_kind_for(f)
        assert kind.kind == "scalar"
        assert kind.scalar == "LargeUtf8"

    def test_bare_dict_defaults_to_large_string(self):
        kind = _arrow_kind_for(_field(FieldType.DICT))
        assert kind.kind == "scalar"
        assert kind.scalar == "LargeUtf8"

    def test_untyped_json_dict_defaults_to_large_string(self):
        inner = _field(FieldType.JSON, name="value")
        f = _field(FieldType.DICT, inner_type=inner)
        kind = _arrow_kind_for(f)
        assert kind.scalar == "LargeUtf8"

    def test_map_opt_in_with_concrete_value_type(self):
        inner = _field(FieldType.FLOAT, name="value")
        f = _field(
            FieldType.DICT,
            inner_type=inner,
            target_config={"arrow": {"dict_as": "map"}},
        )
        kind = _arrow_kind_for(f)
        assert kind.kind == "map"
        assert kind.value is not None
        assert kind.value.scalar == "Float64"

    def test_map_opt_in_without_concrete_value_falls_back(self, caplog):
        f = _field(FieldType.DICT, target_config={"arrow": {"dict_as": "map"}})
        with caplog.at_level(logging.WARNING):
            kind = _arrow_kind_for(f)
        assert kind.kind == "scalar"
        assert kind.scalar == "LargeUtf8"
        assert "concrete value type" in caplog.text

    def test_invalid_dict_as_falls_back_with_warning(self, caplog):
        f = _field(FieldType.DICT, target_config={"arrow": {"dict_as": "hashmap"}})
        with caplog.at_level(logging.WARNING):
            kind = _arrow_kind_for(f)
        assert kind.scalar == "LargeUtf8"
        assert "invalid" in caplog.text.lower()


class TestArrowKindForContainers:
    def test_list_with_inner_type(self):
        inner = _field(FieldType.STRING, name="item")
        kind = _arrow_kind_for(_field(FieldType.LIST, inner_type=inner))
        assert kind.kind == "list"
        assert kind.item is not None
        assert kind.item.scalar == "Utf8"

    def test_list_without_inner_type_defaults_to_utf8_items(self):
        kind = _arrow_kind_for(_field(FieldType.LIST))
        assert kind.kind == "list"
        assert kind.item is not None
        assert kind.item.scalar == "Utf8"

    def test_optional_wrapper_recurses_into_inner(self):
        inner = _field(FieldType.INTEGER, name="inner")
        kind = _arrow_kind_for(_field(FieldType.OPTIONAL, inner_type=inner))
        assert kind.kind == "scalar"
        assert kind.scalar == "Int64"

    @pytest.mark.parametrize("ftype", [FieldType.SET, FieldType.FROZENSET])
    def test_set_and_frozenset_map_like_list(self, ftype):
        inner = _field(FieldType.INTEGER, name="item")
        kind = _arrow_kind_for(_field(ftype, inner_type=inner))
        assert kind.kind == "list"
        assert kind.item is not None
        assert kind.item.scalar == "Int64"

    def test_tuple_with_union_types_uses_first_members_type(self):
        members = [
            _field(FieldType.STRING, name="t0"),
            _field(FieldType.INTEGER, name="t1"),
        ]
        kind = _arrow_kind_for(_field(FieldType.TUPLE, union_types=members))
        assert kind.kind == "list"
        assert kind.item is not None
        assert kind.item.scalar == "Utf8"

    def test_tuple_without_union_types_defaults_to_utf8_items(self):
        kind = _arrow_kind_for(_field(FieldType.TUPLE))
        assert kind.kind == "list"
        assert kind.item is not None
        assert kind.item.scalar == "Utf8"


class TestArrowRustGeneratorOutput:
    def setup_method(self):
        SchemaRegistry._schemas.clear()

    def test_optional_field_is_nullable(self):
        @Schema
        class Thing:
            required_field: str = Field(description="required")
            optional_field: int | None = Field(default=None)

        schema = SchemaParser().parse_schema(Thing)
        out = ArrowRustGenerator().generate_file(schema)
        assert 'Field::new("required_field", DataType::Utf8, false)' in out
        assert 'Field::new("optional_field", DataType::Int64, true)' in out

    def test_function_name_and_signature(self):
        @Schema
        class OrderBookLevel:
            price: float

        schema = SchemaParser().parse_schema(OrderBookLevel)
        out = ArrowRustGenerator().generate_file(schema)
        assert "pub fn order_book_level_arrow_schema() -> Schema {" in out

    def test_schema_and_field_descriptions_pass_through(self):
        @Schema
        class Documented:
            """A documented schema."""

            price: float = Field(description="Limit price")

        schema = SchemaParser().parse_schema(Documented)
        out = ArrowRustGenerator().generate_file(schema)
        assert "/// A documented schema." in out
        assert "// Limit price" in out
        assert '"description".to_string(), "A documented schema.".to_string()' in out

    def test_dict_field_emits_large_utf8(self):
        @Schema
        class WithMap:
            oi_change_5m: dict[str, float] | None = Field(default=None)

        schema = SchemaParser().parse_schema(WithMap)
        out = ArrowRustGenerator().generate_file(schema)
        assert 'Field::new("oi_change_5m", DataType::LargeUtf8, true)' in out
        assert "DataType::Map" not in out

    def test_index_lists_all_modules(self):
        @Schema
        class A:
            x: int

        @Schema
        class B:
            y: int

        schemas = [SchemaParser().parse_schema(A), SchemaParser().parse_schema(B)]
        index = ArrowRustGenerator().generate_index(schemas)
        assert "pub mod a;" in index
        assert "pub mod b;" in index
        assert "pub use a::*;" in index
        assert "pub use b::*;" in index

    def test_variant_emits_additional_fn_with_scoped_fields(self):
        @Schema
        class Order:
            id: int
            name: str
            extra: float | None = Field(default=None)

            class Variants:
                create_request = ["id", "name"]

        schema = SchemaParser().parse_schema(Order)
        out = ArrowRustGenerator().generate_file(schema)
        assert "pub fn order_arrow_schema() -> Schema {" in out
        assert "pub fn order_create_request_arrow_schema() -> Schema {" in out
        # Variant fn body must only include the variant's fields.
        variant_block = out.split("pub fn order_create_request_arrow_schema")[1]
        assert '"id"' in variant_block
        assert '"name"' in variant_block
        assert '"extra"' not in variant_block

    def test_generate_model_with_variant_returns_only_that_fn(self):
        @Schema
        class Order:
            id: int
            name: str

            class Variants:
                create_request = ["id"]

        schema = SchemaParser().parse_schema(Order)
        out = ArrowRustGenerator().generate_model(schema, variant="create_request")
        assert "pub fn order_create_request_arrow_schema() -> Schema {" in out
        assert '"id"' in out
        assert '"name"' not in out

    def test_unidentifier_field_name_warns_not_raises(self, caplog):
        @Schema
        class Weird:
            pass

        schema = SchemaParser().parse_schema(Weird)
        # Inject a non-identifier field name directly (parser normally
        # only produces valid Python identifiers from source, so this
        # simulates a hand-built/foreign USRSchema).
        schema.fields.append(
            USRField(name="1bad-name", type=FieldType.STRING, python_type=str)
        )
        with caplog.at_level(logging.WARNING):
            out = ArrowRustGenerator().generate_file(schema)
        assert 'Field::new("1bad-name", DataType::Utf8, false)' in out
        assert "not a valid Python/Rust identifier" in caplog.text

    def test_determinism_same_schema_byte_identical_output(self):
        @Schema
        class Deterministic:
            a: int
            b: str
            c: float

        schema = SchemaParser().parse_schema(Deterministic)
        gen = ArrowRustGenerator()
        out1 = gen.generate_file(schema)
        out2 = gen.generate_file(schema)
        assert out1 == out2
        # Field order must follow declaration order, not e.g. dict iteration.
        assert out1.index('"a"') < out1.index('"b"') < out1.index('"c"')


class TestArrowPythonGeneratorOutput:
    def setup_method(self):
        SchemaRegistry._schemas.clear()

    def test_optional_field_is_nullable(self):
        @Schema
        class Thing:
            required_field: str = Field(description="required")
            optional_field: int | None = Field(default=None)

        schema = SchemaParser().parse_schema(Thing)
        out = ArrowPythonGenerator().generate_file(schema)
        assert "pa.field('required_field', pa.string(), nullable=False" in out
        assert "pa.field('optional_field', pa.int64(), nullable=True" in out

    def test_dict_field_emits_large_string(self):
        @Schema
        class WithMap:
            oi_change_5m: dict[str, float] | None = Field(default=None)

        schema = SchemaParser().parse_schema(WithMap)
        out = ArrowPythonGenerator().generate_file(schema)
        assert "pa.large_string()" in out
        assert "pa.map_(" not in out

    def test_variant_emits_additional_schema_with_scoped_fields(self):
        @Schema
        class Order:
            id: int
            name: str
            extra: float | None = Field(default=None)

            class Variants:
                create_request = ["id", "name"]

        schema = SchemaParser().parse_schema(Order)
        out = ArrowPythonGenerator().generate_file(schema)
        assert "SCHEMA = pa.schema(" in out
        assert "CREATE_REQUEST_SCHEMA = pa.schema(" in out
        variant_block = out.split("CREATE_REQUEST_SCHEMA = pa.schema(")[1]
        assert "'id'" in variant_block
        assert "'name'" in variant_block
        assert "'extra'" not in variant_block

    def test_generate_model_with_variant_returns_only_that_schema(self):
        @Schema
        class Order:
            id: int
            name: str

            class Variants:
                create_request = ["id"]

        schema = SchemaParser().parse_schema(Order)
        out = ArrowPythonGenerator().generate_model(schema, variant="create_request")
        assert "CREATE_REQUEST_SCHEMA = pa.schema(" in out
        assert "'id'" in out
        assert "'name'" not in out

    def test_index_namespaces_base_and_variant_schemas_per_schema_name(self):
        @Schema
        class Order:
            id: int

            class Variants:
                create_request = ["id"]

        @Schema
        class User:
            id: int

        schemas = [
            SchemaParser().parse_schema(Order),
            SchemaParser().parse_schema(User),
        ]
        index = ArrowPythonGenerator().generate_index(schemas)
        assert "SCHEMA as ORDER_SCHEMA" in index
        assert "CREATE_REQUEST_SCHEMA as ORDER_CREATE_REQUEST_SCHEMA" in index
        assert "SCHEMA as USER_SCHEMA" in index
        # No bare "SCHEMA as SCHEMA" — that would collide across schemas.
        assert " SCHEMA as SCHEMA," not in index
        assert " SCHEMA as SCHEMA\n" not in index
        import ast

        ast.parse(index)

    def test_timestamp_unit_override(self):
        @Schema
        class WithTimestamp:
            ts: datetime = Field(arrow={"timestamp_unit": "nanosecond"})

        schema = SchemaParser().parse_schema(WithTimestamp)
        out = ArrowPythonGenerator().generate_file(schema)
        assert 'pa.timestamp("ns", tz="UTC")' in out

    def test_unidentifier_field_name_warns_not_raises(self, caplog):
        @Schema
        class Weird:
            pass

        schema = SchemaParser().parse_schema(Weird)
        schema.fields.append(
            USRField(name="1bad-name", type=FieldType.STRING, python_type=str)
        )
        with caplog.at_level(logging.WARNING):
            out = ArrowPythonGenerator().generate_file(schema)
        assert "pa.field('1bad-name', pa.string(), nullable=False)" in out
        assert "not a valid Python/Rust identifier" in caplog.text

    def test_schema_and_field_metadata_pass_through(self):
        @Schema
        class Documented:
            """A documented schema."""

            price: float = Field(description="Limit price")

        schema = SchemaParser().parse_schema(Documented)
        out = ArrowPythonGenerator().generate_file(schema)
        assert "metadata={'description': 'A documented schema.'}" in out
        assert "metadata={'description': 'Limit price'}" in out

    def test_determinism_same_schema_byte_identical_output(self):
        @Schema
        class Deterministic:
            a: int
            b: str
            c: float

        schema = SchemaParser().parse_schema(Deterministic)
        gen = ArrowPythonGenerator()
        assert gen.generate_file(schema) == gen.generate_file(schema)

    def test_output_is_syntactically_valid_python(self):
        import ast

        @Schema
        class Full:
            """Exercises every basic scalar + a dict + a list."""

            s: str = Field(description="s")
            n: int
            f: float | None = Field(default=None)
            b: bool
            d: date
            t: time
            u: UUID
            byte_field: bytes
            dec: Decimal
            tags: list[str] = Field(default_factory=list)
            oi_change_5m: dict[str, float] | None = Field(default=None)

        schema = SchemaParser().parse_schema(Full)
        out = ArrowPythonGenerator().generate_file(schema)
        ast.parse(out)  # raises SyntaxError on malformed output
