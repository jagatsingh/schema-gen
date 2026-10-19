"""Generators to create Apache Arrow schemas from USR schemas (#148).

Two targets share one FieldType -> Arrow DataType mapping table:

- ``ArrowRustGenerator`` (target ``arrow_rust``) emits a ``.rs`` file per
  schema with a ``pub fn <schema>_arrow_schema() -> arrow::datatypes::Schema``
  builder, for Rust Parquet writers (``arrow-rs``).
- ``ArrowPythonGenerator`` (target ``arrow_python``) emits a ``.py`` module
  per schema with a module-level ``SCHEMA = pa.schema([...])``, for Python
  Parquet readers/writers (``pyarrow``).

Both targets resolve fields through ``_arrow_kind_for()``, a small finite
dispatch table (see ``_ArrowKind``) so the two emission back ends can never
silently diverge on what a given ``FieldType`` maps to. Unmapped
``FieldType`` values raise ``ValueError`` rather than falling back to a
lossy default (issue #148 requirement #1).
"""

import logging
from dataclasses import dataclass
from pathlib import Path

from ..core.usr import FieldType, USRField, USRSchema
from .base import BaseGenerator

logger = logging.getLogger(__name__)

# Default Decimal128 precision/scale when a DECIMAL field doesn't override
# via ``Field(arrow={"precision": ..., "scale": ...})``. Mirrors the
# per-target override pattern avro_generator.py uses for its own decimal
# logical type (``field.target_config.get("avro", {})``).
_DEFAULT_DECIMAL_PRECISION = 38
_DEFAULT_DECIMAL_SCALE = 9

# DATETIME -> Arrow Timestamp unit. Configurable per-field via
# ``Field(arrow={"timestamp_unit": "nanosecond"})`` because real consumers
# mix granularities in one schema — e.g. tradingcore's Parquet export uses
# nanosecond precision for its primary ``timestamp`` field but millisecond
# for secondary last-tick-time fields (``spot_ltt``, ``futures_ltt``,
# ``option_ltt``) in the same struct (see tradingcore src/sink/backtest.rs).
_TIMESTAMP_UNITS: frozenset[str] = frozenset(
    {"second", "millisecond", "microsecond", "nanosecond"}
)
_DEFAULT_TIMESTAMP_UNIT = "microsecond"
_RUST_TIME_UNIT: dict[str, str] = {
    "second": "Second",
    "millisecond": "Millisecond",
    "microsecond": "Microsecond",
    "nanosecond": "Nanosecond",
}
_PYARROW_TIME_UNIT: dict[str, str] = {
    "second": "s",
    "millisecond": "ms",
    "microsecond": "us",
    "nanosecond": "ns",
}

# Arrow's Time64 (as opposed to Time32) only supports microsecond/nanosecond
# resolution. TIME fields aren't configurable per-field (unlike DATETIME) —
# there's no known real consumer that needs anything but microsecond — but
# the unit is still carried on the ``_ArrowKind`` (kind="time") rather than
# baked into a literal Rust-source-text string shared as a dict key with the
# Python table. A prior version keyed ``_PYARROW_SCALAR_MAPPING`` on the
# literal string ``"Time64(Microsecond)"``, which meant fixing the Rust
# emission (``DataType::Time64(Microsecond)`` doesn't compile — it needs
# ``TimeUnit::Microsecond``) without also touching the Python table would
# silently KeyError on the Python side. See schema-gen post-#149 review.
_DEFAULT_TIME_UNIT = "microsecond"

# DICT value representation. Defaults to a JSON-serialized ``LargeUtf8``
# string column, NOT a native Arrow ``Map`` — this matches the real,
# already-shipped consumer (tradingcore's Parquet writer, see
# src/sink/backtest.rs's ``schema_meets_cme_export_invariants`` test guarding
# tradingcore#697): CME per-strike dict fields (``oi_change_5m`` etc.) can
# average ~100KB/row of JSON; a day's export (~40k rows) produces ~4GB of
# text, which overflows plain ``Utf8``'s i32-offset (2GB) ceiling, hence
# ``LargeUtf8`` (i64 offsets) specifically — not just "a string type".
# A caller that wants a decodable native Map can opt in per-field via
# ``Field(arrow={"dict_as": "map"})``.
_DEFAULT_DICT_AS = "large_string"


@dataclass(frozen=True)
class _ArrowKind:
    """One resolved Arrow type, kind-tagged so both back ends can render it
    without re-deriving field-specific details (map value type, decimal
    precision/scale, list item kind) from the USR field a second time.
    """

    kind: str  # "scalar", "timestamp", "time", "decimal", "list", "map"
    scalar: str | None = None  # canonical Arrow scalar type name (e.g. "Utf8")
    item: _ArrowKind | None = None  # LIST inner kind
    value: _ArrowKind | None = None  # MAP value kind (key is always Utf8)
    precision: int | None = None  # DECIMAL
    scale: int | None = None  # DECIMAL


# FieldType values with a direct, context-free Arrow scalar mapping. Kept
# as a plain table (not a chain of ``if``) so the mapping is auditable at a
# glance and can't quietly grow inconsistent between the two generators.
_SCALAR_ARROW_TYPES: dict[FieldType, str] = {
    FieldType.STRING: "Utf8",
    FieldType.BOOLEAN: "Boolean",
    FieldType.INTEGER: "Int64",
    FieldType.FLOAT: "Float64",
    # DATETIME is handled separately (see below) — its Arrow Timestamp unit
    # is configurable per-field, unlike every other entry in this table.
    FieldType.DATE: "Date32",
    # TIME is handled separately (see below), like DATETIME — it resolves
    # to a unit-carrying "time" kind rather than a literal scalar string,
    # so the Rust and Python tables can never drift out of sync on it.
    FieldType.BYTES: "Binary",
    # Arrow has no native UUID/JSON/Literal/Enum type; all four are carried
    # as plain strings. Documented explicitly (issue #148) rather than left
    # implicit so downstream authors don't mistake this for an oversight.
    FieldType.UUID: "Utf8",
    FieldType.JSON: "Utf8",
    FieldType.LITERAL: "Utf8",
    FieldType.ENUM: "Utf8",
}


def _arrow_kind_for(field: USRField) -> _ArrowKind:
    """Resolve ``field`` to an ``_ArrowKind``, ignoring optionality.

    Nullability is a ``Field`` wrapper applied by the caller from
    ``field.optional`` (or the OPTIONAL wrapper type, see below) — it is
    not baked into the returned ``DataType`` itself, matching how
    ``rust_generator.py`` separates ``_rust_type_for`` from the
    ``Option<...>`` wrapping in ``_generate_field``.
    """
    ftype = field.type

    # OPTIONAL is a wrapper FieldType some parser paths use (nested inside
    # containers) rather than the flat ``field.optional`` bool. Recurse into
    # the wrapped type — nullability is applied by the caller either way.
    if ftype == FieldType.OPTIONAL and field.inner_type is not None:
        return _arrow_kind_for(field.inner_type)

    if ftype in _SCALAR_ARROW_TYPES:
        return _ArrowKind(kind="scalar", scalar=_SCALAR_ARROW_TYPES[ftype])

    arrow_cfg = field.target_config.get("arrow", {}) if field.target_config else {}

    if ftype == FieldType.DATETIME:
        unit = arrow_cfg.get("timestamp_unit", _DEFAULT_TIMESTAMP_UNIT)
        if unit not in _TIMESTAMP_UNITS:
            logger.warning(
                "Arrow generator: ignoring invalid Field(arrow={'timestamp_unit': %r}) "
                "on field '%s' (valid: %s). Falling back to %s.",
                unit,
                field.name,
                sorted(_TIMESTAMP_UNITS),
                _DEFAULT_TIMESTAMP_UNIT,
            )
            unit = _DEFAULT_TIMESTAMP_UNIT
        return _ArrowKind(kind="timestamp", scalar=unit)

    if ftype == FieldType.TIME:
        return _ArrowKind(kind="time", scalar=_DEFAULT_TIME_UNIT)

    if ftype == FieldType.DECIMAL:
        precision = arrow_cfg.get("precision", _DEFAULT_DECIMAL_PRECISION)
        scale = arrow_cfg.get("scale", _DEFAULT_DECIMAL_SCALE)
        # pyarrow's ``decimal128``/``decimal256`` only actually validates
        # precision at construction time (1-38 for decimal128); an
        # out-of-range value raises ValueError at *import* time of the
        # generated Python module, not at generation time. Scale isn't
        # range-checked by pyarrow itself, but a scale outside
        # [0, precision] is never a meaningful decimal, so we treat it the
        # same way as the other per-field overrides in this file (warn +
        # fall back to the default rather than emit a value we know is
        # either invalid or nonsensical).
        if not (1 <= precision <= 38):
            logger.warning(
                "Arrow generator: ignoring invalid Field(arrow={'precision': %r}) "
                "on field '%s' (must be 1-38 for Decimal128). Falling back to "
                "precision=%s, scale=%s.",
                precision,
                field.name,
                _DEFAULT_DECIMAL_PRECISION,
                _DEFAULT_DECIMAL_SCALE,
            )
            precision = _DEFAULT_DECIMAL_PRECISION
            scale = _DEFAULT_DECIMAL_SCALE
        elif not (0 <= scale <= precision):
            logger.warning(
                "Arrow generator: ignoring invalid Field(arrow={'scale': %r}) "
                "on field '%s' (must satisfy 0 <= scale <= precision=%s). "
                "Falling back to precision=%s, scale=%s.",
                scale,
                field.name,
                precision,
                _DEFAULT_DECIMAL_PRECISION,
                _DEFAULT_DECIMAL_SCALE,
            )
            precision = _DEFAULT_DECIMAL_PRECISION
            scale = _DEFAULT_DECIMAL_SCALE
        return _ArrowKind(kind="decimal", precision=precision, scale=scale)

    if ftype in (FieldType.LIST, FieldType.SET, FieldType.FROZENSET):
        item = (
            _arrow_kind_for(field.inner_type)
            if field.inner_type
            else _ArrowKind(kind="scalar", scalar="Utf8")
        )
        return _ArrowKind(kind="list", item=item)

    if ftype == FieldType.TUPLE:
        # Arrow has no tuple type. Best-effort: a List of the first union
        # member's type when the tuple is homogeneous-ish, else Utf8 items
        # (mirrors avro_generator.py's best-effort tuple handling).
        if field.union_types:
            first_kind = _arrow_kind_for(field.union_types[0])
            return _ArrowKind(kind="list", item=first_kind)
        return _ArrowKind(kind="list", item=_ArrowKind(kind="scalar", scalar="Utf8"))

    if ftype == FieldType.DICT:
        # Default: JSON-serialize the dict into a LargeUtf8 string column
        # (see _DEFAULT_DICT_AS docstring above for why LargeUtf8 and not
        # Map or plain Utf8). Opt in to a native Map(Utf8, T) per-field via
        # ``Field(arrow={"dict_as": "map"})`` — only viable when the value
        # type is concrete (dict[str, T]), not a bare/untyped dict.
        dict_as = arrow_cfg.get("dict_as", _DEFAULT_DICT_AS)
        inner = field.inner_type
        has_concrete_value = inner is not None and inner.type != FieldType.JSON
        if dict_as == "map" and has_concrete_value and inner is not None:
            value_kind = _arrow_kind_for(inner)
            return _ArrowKind(kind="map", value=value_kind)
        if dict_as == "map" and not has_concrete_value:
            logger.warning(
                "Arrow generator: Field(arrow={'dict_as': 'map'}) on field "
                "'%s' has no concrete value type (bare dict / dict[str, Any]); "
                "Arrow Map requires one. Falling back to LargeUtf8.",
                field.name,
            )
        elif dict_as != _DEFAULT_DICT_AS:
            logger.warning(
                "Arrow generator: ignoring invalid Field(arrow={'dict_as': %r}) "
                "on field '%s' (valid: 'large_string', 'map'). Falling back "
                "to 'large_string'.",
                dict_as,
                field.name,
            )
        return _ArrowKind(kind="scalar", scalar="LargeUtf8")

    raise ValueError(
        f"Arrow generator: no Arrow type mapping for FieldType.{ftype.name} "
        f"(field {field.name!r}). Unmapped types are a hard error — see "
        f"schema-gen#148 requirement #1 (no silent lossy fallback)."
    )


def _is_optional(field: USRField) -> bool:
    return field.optional or field.type == FieldType.OPTIONAL


def _check_identifier_safety(schema: USRSchema, target: str) -> None:
    """Warn (not raise) on field names that aren't valid identifiers.

    Arrow itself doesn't care what a column name looks like, but downstream
    consumers do (e.g. ``pandas.itertuples`` silently renames non-identifier
    column names) — issue #148 requirement #5.
    """
    for f in schema.fields:
        if not f.name.isidentifier():
            logger.warning(
                "Arrow %s generator: field '%s' on schema '%s' is not a "
                "valid Python/Rust identifier; downstream consumers "
                "(e.g. pandas.itertuples) may silently rename this column.",
                target,
                f.name,
                schema.name,
            )


# ---------------------------------------------------------------------
# Rust target
# ---------------------------------------------------------------------


def _rust_dtype(k: _ArrowKind) -> str:
    if k.kind == "scalar":
        assert k.scalar is not None
        return f"DataType::{k.scalar}"
    if k.kind == "timestamp":
        assert k.scalar is not None
        unit = _RUST_TIME_UNIT[k.scalar]
        return f'DataType::Timestamp(TimeUnit::{unit}, Some("UTC".into()))'
    if k.kind == "time":
        assert k.scalar is not None
        unit = _RUST_TIME_UNIT[k.scalar]
        return f"DataType::Time64(TimeUnit::{unit})"
    if k.kind == "decimal":
        return f"DataType::Decimal128({k.precision}, {k.scale})"
    if k.kind == "list":
        assert k.item is not None
        item_field = _rust_field_expr("item", k.item, nullable=True)
        return f"DataType::List(Arc::new({item_field}))"
    if k.kind == "map":
        assert k.value is not None
        key_field = 'Field::new("key", DataType::Utf8, false)'
        value_field = _rust_field_expr("value", k.value, nullable=True)
        return (
            'DataType::Map(Arc::new(Field::new("entries", '
            f"DataType::Struct(vec![{key_field}, {value_field}].into()), false)), false)"
        )
    raise AssertionError(f"unreachable arrow kind: {k.kind}")  # pragma: no cover


def _rust_str_lit(s: str) -> str:
    """Render ``s`` as a Rust string literal, escaping backslashes/quotes.

    Arrow column names aren't Rust identifiers (they're just the string
    label passed to ``Field::new``), so unlike struct field idents
    elsewhere in this codebase, non-identifier-safe names are allowed here
    — they just need to round-trip as valid Rust *source text*.
    """
    escaped = (
        s.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
    )
    return f'"{escaped}"'


def _rust_field_expr(name: str, k: _ArrowKind, *, nullable: bool) -> str:
    dtype = _rust_dtype(k)
    return f"Field::new({_rust_str_lit(name)}, {dtype}, {str(nullable).lower()})"


def _snake_case(name: str) -> str:
    """Convert PascalCase/camelCase to snake_case (mirrors rust_generator.py)."""
    stripped = name.lstrip("_")
    if not stripped:
        return name.lower()
    out: list[str] = []
    for i, ch in enumerate(stripped):
        if (
            ch.isupper()
            and i > 0
            and (
                not stripped[i - 1].isupper()
                or (i + 1 < len(stripped) and stripped[i + 1].islower())
            )
        ):
            out.append("_")
        out.append(ch.lower())
    return "".join(out)


def _rust_fn_block(
    fn_name: str, doc_lines: list[str], fields: list[USRField], description: str | None
) -> str:
    """Render one ``pub fn <fn_name>() -> Schema { ... }`` block."""
    lines: list[str] = list(doc_lines)
    lines.append(f"pub fn {fn_name}() -> Schema {{")
    lines.append("    let fields: Vec<Field> = vec![")
    for f in fields:
        kind = _arrow_kind_for(f)
        nullable = _is_optional(f)
        field_expr = _rust_field_expr(f.name, kind, nullable=nullable)
        if f.description:
            for doc_line in f.description.strip().splitlines():
                lines.append(
                    f"        // {doc_line.strip()}"
                    if doc_line.strip()
                    else "        //"
                )
        lines.append(f"        {field_expr},")
    lines.append("    ];")
    if description:
        lines.append(
            "    Schema::new(fields).with_metadata(std::collections::HashMap::from(["
        )
        lines.append(
            f'        ("description".to_string(), {_rust_str_lit(description)}.to_string()),'
        )
        lines.append("    ]))")
    else:
        lines.append("    Schema::new(fields)")
    lines.append("}")
    return "\n".join(lines)


class ArrowRustGenerator(BaseGenerator):
    """Emits a ``pub fn <schema>_arrow_schema() -> arrow::datatypes::Schema``
    builder per ``@Schema`` (plus one per ``Variants`` entry), for Rust
    Parquet writers (``arrow-rs``).
    """

    index_filename = "mod.rs"

    @property
    def file_extension(self) -> str:
        return ".rs"

    @property
    def generates_index_file(self) -> bool:
        return True

    def get_schema_filename(self, schema: USRSchema) -> str:
        return f"{_snake_case(schema.name)}{self.file_extension}"

    def generate_index(
        self, schemas: list[USRSchema], output_dir: Path | None = None
    ) -> str:
        lines = [
            "// AUTO-GENERATED FILE - DO NOT EDIT MANUALLY",
            "// Generator: schema-gen Arrow (Rust) generator",
            "",
        ]
        module_names = [_snake_case(s.name) for s in schemas]
        for module in module_names:
            lines.append(f"pub mod {module};")
        if module_names:
            lines.append("")
        for module in module_names:
            lines.append(f"pub use {module}::*;")
        lines.append("")
        return "\n".join(lines)

    def generate_model(self, schema: USRSchema, variant: str | None = None) -> str:
        if variant is None:
            return self.generate_file(schema)
        fn_name = f"{_snake_case(schema.name)}_{_snake_case(variant)}_arrow_schema"
        doc_lines = [f"/// Arrow schema for `{schema.name}` (variant `{variant}`)."]
        return _rust_fn_block(
            fn_name, doc_lines, schema.get_variant_fields(variant), description=None
        )

    def generate_file(self, schema: USRSchema) -> str:
        _check_identifier_safety(schema, "Rust")
        base_fn_name = f"{_snake_case(schema.name)}_arrow_schema"
        base_doc_lines = [
            f"/// Arrow schema for `{schema.name}`, generated from its USR definition."
        ]
        if schema.description:
            for doc_line in schema.description.strip().splitlines():
                base_doc_lines.append(
                    f"/// {doc_line.strip()}" if doc_line.strip() else "///"
                )

        blocks = [
            _rust_fn_block(
                base_fn_name, base_doc_lines, schema.fields, schema.description
            )
        ]
        for variant_name in schema.variants:
            variant_fn_name = (
                f"{_snake_case(schema.name)}_{_snake_case(variant_name)}_arrow_schema"
            )
            variant_doc_lines = [
                f"/// Arrow schema for `{schema.name}` (variant `{variant_name}`)."
            ]
            blocks.append(
                _rust_fn_block(
                    variant_fn_name,
                    variant_doc_lines,
                    schema.get_variant_fields(variant_name),
                    description=None,
                )
            )

        header = [
            "// AUTO-GENERATED FILE - DO NOT EDIT MANUALLY",
            "// Generator: schema-gen Arrow (Rust) generator",
            "",
            "use std::sync::Arc;",
            "",
            "use arrow::datatypes::{DataType, Field, Schema, TimeUnit};",
            "",
            "",
        ]
        return "\n".join(header) + "\n\n".join(blocks) + "\n"


# ---------------------------------------------------------------------
# Python (pyarrow) target
# ---------------------------------------------------------------------


_PYARROW_SCALAR_MAPPING: dict[str, str] = {
    "Utf8": "pa.string()",
    "LargeUtf8": "pa.large_string()",
    "Boolean": "pa.bool_()",
    "Int64": "pa.int64()",
    "Float64": "pa.float64()",
    "Date32": "pa.date32()",
    "Binary": "pa.binary()",
}


def _python_dtype(k: _ArrowKind) -> str:
    if k.kind == "scalar":
        assert k.scalar is not None
        return _PYARROW_SCALAR_MAPPING[k.scalar]
    if k.kind == "timestamp":
        assert k.scalar is not None
        unit = _PYARROW_TIME_UNIT[k.scalar]
        return f'pa.timestamp("{unit}", tz="UTC")'
    if k.kind == "time":
        assert k.scalar is not None
        unit = _PYARROW_TIME_UNIT[k.scalar]
        return f'pa.time64("{unit}")'
    if k.kind == "decimal":
        return f"pa.decimal128({k.precision}, {k.scale})"
    if k.kind == "list":
        assert k.item is not None
        return f"pa.list_({_python_field_expr('item', k.item, nullable=True)})"
    if k.kind == "map":
        assert k.value is not None
        return f"pa.map_(pa.string(), {_python_dtype(k.value)})"
    raise AssertionError(f"unreachable arrow kind: {k.kind}")  # pragma: no cover


def _python_field_expr(name: str, k: _ArrowKind, *, nullable: bool) -> str:
    dtype = _python_dtype(k)
    return f"pa.field({name!r}, {dtype}, nullable={nullable})"


def _python_schema_block(
    var_name: str, fields: list[USRField], description: str | None
) -> list[str]:
    """Render one ``<var_name> = pa.schema([...])`` assignment."""
    lines = [f"{var_name} = pa.schema("]
    lines.append("    [")
    for f in fields:
        kind = _arrow_kind_for(f)
        nullable = _is_optional(f)
        metadata = (
            f", metadata={{'description': {f.description!r}}}" if f.description else ""
        )
        lines.append(
            f"        pa.field({f.name!r}, {_python_dtype(kind)}, "
            f"nullable={nullable}{metadata}),"
        )
    lines.append("    ],")
    if description:
        lines.append(f"    metadata={{'description': {description!r}}},")
    lines.append(")")
    return lines


class ArrowPythonGenerator(BaseGenerator):
    """Emits a module-level ``SCHEMA = pa.schema([...])`` per ``@Schema``
    (plus one ``<VARIANT>_SCHEMA`` per ``Variants`` entry), for Python
    Parquet readers/writers (``pyarrow``).
    """

    @property
    def file_extension(self) -> str:
        return ".py"

    @property
    def generates_index_file(self) -> bool:
        return True

    def get_schema_filename(self, schema: USRSchema) -> str:
        return f"{schema.name.lower()}_arrow.py"

    def generate_index(
        self, schemas: list[USRSchema], output_dir: Path | None = None
    ) -> str:
        lines = ['"""AUTO-GENERATED FILE - DO NOT EDIT MANUALLY."""', ""]
        all_aliases: list[str] = []
        for schema in schemas:
            module_stem = schema.name.lower()
            name_upper = schema.name.upper()
            # Local var names inside the per-schema module (SCHEMA,
            # <VARIANT>_SCHEMA) are namespaced per-schema on re-export
            # (<NAME>_SCHEMA, <NAME>_<VARIANT>_SCHEMA) — a bare "SCHEMA"
            # alias would collide across every schema sharing this index.
            var_names = ["SCHEMA"] + [
                f"{variant_name.upper()}_SCHEMA" for variant_name in schema.variants
            ]
            aliases = [f"{name_upper}_{var_name}" for var_name in var_names]
            imports = ", ".join(
                f"{v} as {a}" for v, a in zip(var_names, aliases, strict=True)
            )
            lines.append(f"from .{module_stem}_arrow import {imports}")
            all_aliases.extend(aliases)
        lines.append("")
        lines.append("__all__ = [")
        for alias in all_aliases:
            lines.append(f'    "{alias}",')
        lines.append("]")
        lines.append("")
        return "\n".join(lines)

    def generate_model(self, schema: USRSchema, variant: str | None = None) -> str:
        if variant is None:
            return self.generate_file(schema)
        var_name = f"{variant.upper()}_SCHEMA"
        return "\n".join(
            _python_schema_block(
                var_name, schema.get_variant_fields(variant), description=None
            )
        )

    def generate_file(self, schema: USRSchema) -> str:
        _check_identifier_safety(schema, "Python")
        header = [
            '"""AUTO-GENERATED FILE - DO NOT EDIT MANUALLY.',
            "",
            f"pyarrow schema for `{schema.name}`, generated from its USR definition.",
            '"""',
            "",
            "import pyarrow as pa",
            "",
            "",
        ]
        blocks = [_python_schema_block("SCHEMA", schema.fields, schema.description)]
        for variant_name in schema.variants:
            blocks.append(
                _python_schema_block(
                    f"{variant_name.upper()}_SCHEMA",
                    schema.get_variant_fields(variant_name),
                    description=None,
                )
            )
        body = "\n\n\n".join("\n".join(block) for block in blocks)
        return "\n".join(header) + body + "\n"
