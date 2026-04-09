"""Generator to create Rust Serde models from USR schemas.

Implements the v1 spec from jagatsingh/schema-gen#12. Emits one ``.rs`` file
per ``@Schema`` plus a ``lib.rs`` index. Structs use ``serde``, optionally
``schemars::JsonSchema``, and support ``SerdeMeta`` for custom code injection
(extra derives, imports, and raw ``impl`` blocks).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from ..core.usr import FieldType, USREnum, USRField, USRSchema
from .base import BaseGenerator

logger = logging.getLogger(__name__)


# Rust 2021 reserved keywords + a few contextual ones that are unsafe as
# identifiers. Fields with these names are emitted as ``r#<name>`` with a
# matching ``#[serde(rename = "<name>")]`` attribute.
_RUST_RESERVED_WORDS: frozenset[str] = frozenset(
    {
        "as",
        "break",
        "const",
        "continue",
        "crate",
        "else",
        "enum",
        "extern",
        "false",
        "fn",
        "for",
        "if",
        "impl",
        "in",
        "let",
        "loop",
        "match",
        "mod",
        "move",
        "mut",
        "pub",
        "ref",
        "return",
        "self",
        "Self",
        "static",
        "struct",
        "super",
        "trait",
        "true",
        "type",
        "unsafe",
        "use",
        "where",
        "while",
        "async",
        "await",
        "dyn",
        "abstract",
        "become",
        "box",
        "do",
        "final",
        "macro",
        "override",
        "priv",
        "typeof",
        "unsized",
        "virtual",
        "yield",
        "try",
        "union",
    }
)

_VALID_RENAME_ALL = frozenset(
    {
        "lowercase",
        "UPPERCASE",
        "PascalCase",
        "camelCase",
        "snake_case",
        "SCREAMING_SNAKE_CASE",
        "kebab-case",
        "SCREAMING-KEBAB-CASE",
    }
)

_DEFAULT_STRUCT_DERIVES = [
    "Debug",
    "Clone",
    "PartialEq",
    "Serialize",
    "Deserialize",
]

_DEFAULT_ENUM_DERIVES = [
    "Debug",
    "Clone",
    "Copy",
    "PartialEq",
    "Eq",
    "Hash",
    "Serialize",
    "Deserialize",
]


class RustGenerator(BaseGenerator):
    """Generates Rust structs and enums with serde derives from USR schemas."""

    @property
    def file_extension(self) -> str:
        return ".rs"

    @property
    def generates_index_file(self) -> bool:
        return True

    def get_schema_filename(self, schema: USRSchema) -> str:
        return f"{_snake_case(schema.name)}{self.file_extension}"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate_index(
        self, schemas: list[USRSchema], output_dir: Path | None = None
    ) -> str:
        """Generate ``lib.rs`` with ``pub mod`` and ``pub use`` re-exports."""
        lines = [
            "// AUTO-GENERATED FILE - DO NOT EDIT MANUALLY",
            "// Generator: schema-gen Rust Serde generator",
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

    def generate_file(self, schema: USRSchema) -> str:
        """Emit a complete ``.rs`` file for a single schema."""
        custom_code = schema.custom_code.get("rust", {}) or {}
        json_schema_derive = custom_code.get("json_schema_derive", True)

        imports: set[str] = set()
        body_parts: list[str] = []

        # Enums (referenced by fields) get emitted before the struct.
        for enum in schema.enums:
            body_parts.append(
                self._generate_enum(enum, json_schema_derive=json_schema_derive)
            )

        # Base struct
        body_parts.append(
            self._generate_struct(
                schema=schema,
                struct_name=schema.name,
                fields=schema.fields,
                imports=imports,
                json_schema_derive=json_schema_derive,
                custom_code=custom_code,
                is_base=True,
            )
        )

        # Variant structs
        base_field_names = {f.name for f in schema.fields}
        for variant_name in schema.variants:
            variant_fields = schema.get_variant_fields(variant_name)
            variant_struct_name = self._variant_to_struct_name(
                schema.name, variant_name
            )
            body_parts.append(
                self._generate_struct(
                    schema=schema,
                    struct_name=variant_struct_name,
                    fields=variant_fields,
                    imports=imports,
                    json_schema_derive=json_schema_derive,
                    custom_code={},  # variants don't inherit raw_code
                    is_base=False,
                )
            )

            # Emit From<Variant> for Full if variant is a strict subset
            variant_field_names = {f.name for f in variant_fields}
            if variant_field_names.issubset(
                base_field_names
            ) and _variant_is_from_eligible(schema.fields, variant_fields):
                body_parts.append(
                    self._generate_from_impl(
                        source=variant_struct_name,
                        target=schema.name,
                        source_fields=variant_fields,
                        target_fields=schema.fields,
                    )
                )

        header = self._generate_header(
            schema=schema,
            imports=imports,
            custom_code=custom_code,
            json_schema_derive=json_schema_derive,
        )

        trailing = ""
        raw_code = (custom_code.get("raw_code") or "").strip()
        if raw_code:
            trailing = "\n\n" + raw_code + "\n"

        return header + "\n\n".join(body_parts) + trailing + "\n"

    def generate_model(self, schema: USRSchema, variant: str | None = None) -> str:
        """Generate a single struct (base or variant) without headers."""
        imports: set[str] = set()
        custom_code = schema.custom_code.get("rust", {}) or {}
        json_schema_derive = custom_code.get("json_schema_derive", True)

        if variant is None:
            return self._generate_struct(
                schema=schema,
                struct_name=schema.name,
                fields=schema.fields,
                imports=imports,
                json_schema_derive=json_schema_derive,
                custom_code=custom_code,
                is_base=True,
            )

        variant_fields = schema.get_variant_fields(variant)
        variant_struct_name = self._variant_to_struct_name(schema.name, variant)
        return self._generate_struct(
            schema=schema,
            struct_name=variant_struct_name,
            fields=variant_fields,
            imports=imports,
            json_schema_derive=json_schema_derive,
            custom_code={},
            is_base=False,
        )

    # ------------------------------------------------------------------
    # Struct / enum emission
    # ------------------------------------------------------------------

    def _generate_header(
        self,
        schema: USRSchema,
        imports: set[str],
        custom_code: dict[str, Any],
        json_schema_derive: bool,
    ) -> str:
        lines = [
            "// AUTO-GENERATED FILE - DO NOT EDIT MANUALLY",
            f"// Generated from: {schema.name}",
            "// Generator: schema-gen Rust Serde generator",
            "//",
            "// To regenerate: schema-gen generate --target rust",
            "",
            "use serde::{Deserialize, Serialize};",
        ]

        if json_schema_derive:
            lines.append("use schemars::JsonSchema;")

        # Collect standard-library / crate imports discovered while
        # processing fields.
        if "HashMap" in imports:
            lines.append("use std::collections::HashMap;")
        if "chrono_datetime" in imports:
            # chrono types are referenced via fully-qualified paths in field
            # emission, so no extra ``use`` is required here — keep the
            # import set self-documenting.
            pass

        # Custom imports from SerdeMeta
        for custom_import in custom_code.get("imports", []) or []:
            line = custom_import.rstrip(";")
            lines.append(f"{line};")

        lines.append("")
        lines.append("")
        return "\n".join(lines)

    def _generate_struct(
        self,
        schema: USRSchema,
        struct_name: str,
        fields: list[USRField],
        imports: set[str],
        json_schema_derive: bool,
        custom_code: dict[str, Any],
        is_base: bool,
    ) -> str:
        derives = list(_DEFAULT_STRUCT_DERIVES)
        if json_schema_derive:
            derives.append("JsonSchema")

        if is_base:
            for extra in custom_code.get("derives", []) or []:
                if extra not in derives:
                    derives.append(extra)

        lines: list[str] = []
        if schema.description and is_base:
            for doc_line in schema.description.strip().splitlines():
                lines.append(f"/// {doc_line.strip()}")

        lines.append(f"#[derive({', '.join(derives)})]")

        deny_unknown = True
        if is_base and "deny_unknown_fields" in (custom_code or {}):
            deny_unknown = bool(custom_code["deny_unknown_fields"])
        if deny_unknown:
            lines.append("#[serde(deny_unknown_fields)]")

        lines.append(f"pub struct {struct_name} {{")

        field_lines: list[str] = []
        for field in fields:
            field_lines.extend(self._generate_field(field, imports))

        # Join fields with blank lines between each for readability. Each
        # field may contain doc comments + serde attrs + the field itself.
        for i, block in enumerate(_split_field_blocks(field_lines)):
            if i > 0:
                lines.append("")
            lines.extend("    " + line if line else "" for line in block)

        lines.append("}")
        return "\n".join(lines)

    def _generate_field(self, field: USRField, imports: set[str]) -> list[str]:
        """Generate doc comments, serde attrs, and the field declaration."""
        out: list[str] = []

        if field.description:
            for doc_line in field.description.strip().splitlines():
                out.append(f"/// {doc_line.strip()}")

        is_optional = field.optional or field.type == FieldType.OPTIONAL
        rust_type = self._rust_type_for(field, imports)
        if is_optional and not rust_type.startswith("Option<"):
            rust_type = f"Option<{rust_type}>"

        serde_attrs: list[str] = []
        name = field.name
        emitted_name = name

        if name in _RUST_RESERVED_WORDS:
            emitted_name = f"r#{name}"
            serde_attrs.append(f'rename = "{name}"')

        if is_optional:
            serde_attrs.append('skip_serializing_if = "Option::is_none"')

        if serde_attrs:
            out.append(f"#[serde({', '.join(serde_attrs)})]")

        out.append(f"pub {emitted_name}: {rust_type},")

        # Sentinel blank line separates this field block from the next
        # during assembly (stripped when joining).
        out.append("")
        return out

    def _rust_type_for(self, field: USRField, imports: set[str]) -> str:
        """Map a USR field to a Rust type string."""
        # Optional with inner_type → recurse on the inner.
        if field.type == FieldType.OPTIONAL and field.inner_type is not None:
            return f"Option<{self._rust_type_for(field.inner_type, imports)}>"

        # Many parsers emit ``optional=True`` + ``inner_type`` while keeping
        # ``field.type`` as the underlying type (e.g. INTEGER). For such
        # fields the caller wraps the result in ``Option<...>`` separately,
        # so here we just resolve the base type.
        ftype = field.type

        if ftype == FieldType.STRING:
            return "String"
        if ftype == FieldType.INTEGER:
            return "i64"
        if ftype == FieldType.FLOAT:
            return "f64"
        if ftype == FieldType.BOOLEAN:
            return "bool"
        if ftype == FieldType.BYTES:
            return "Vec<u8>"
        if ftype == FieldType.DATETIME:
            return "chrono::DateTime<chrono::Utc>"
        if ftype == FieldType.DATE:
            return "chrono::NaiveDate"
        if ftype == FieldType.TIME:
            return "chrono::NaiveTime"
        if ftype == FieldType.UUID:
            return "uuid::Uuid"
        if ftype == FieldType.DECIMAL:
            return "rust_decimal::Decimal"
        if ftype == FieldType.JSON:
            return "serde_json::Value"

        if ftype in (FieldType.LIST, FieldType.SET, FieldType.FROZENSET):
            if field.inner_type is not None:
                inner = self._rust_type_for(field.inner_type, imports)
                return f"Vec<{inner}>"
            return "Vec<serde_json::Value>"

        if ftype == FieldType.DICT:
            imports.add("HashMap")
            # We don't currently thread a value type through USR for dicts
            # so default to ``serde_json::Value`` (matches ``dict[str, Any]``).
            return "HashMap<String, serde_json::Value>"

        if ftype == FieldType.TUPLE:
            if field.union_types:
                parts = [self._rust_type_for(t, imports) for t in field.union_types]
                return f"({', '.join(parts)})"
            return "Vec<serde_json::Value>"

        if ftype == FieldType.UNION:
            logger.warning(
                "Rust generator: union field '%s' emitted as serde_json::Value "
                "(tagged unions are out of scope for v1).",
                field.name,
            )
            return "serde_json::Value  // TODO: union not supported in v1"

        if ftype == FieldType.LITERAL:
            # Treat as a string-valued enum at the type level; v1 keeps it
            # simple and just uses String.
            return "String"

        if ftype == FieldType.ENUM:
            return field.enum_name or "String"

        if ftype == FieldType.NESTED_SCHEMA:
            nested = field.nested_schema or "serde_json::Value"
            return nested

        return "serde_json::Value"

    def _generate_enum(self, enum: USREnum, json_schema_derive: bool) -> str:
        derives = list(_DEFAULT_ENUM_DERIVES)
        if json_schema_derive:
            derives.append("JsonSchema")

        # Emit per-variant `#[serde(rename = "<value>")]` using the actual
        # enum value from the IR. This is the only correct behavior when the
        # source Python enum mixes wire-format casings (e.g. `NSE = "NSE"` +
        # `BUY = "buy"` + `MIS = "MIS"`). A single `rename_all` on the enum
        # cannot express that mix, and silently dropping the value — as an
        # earlier draft did — breaks wire format compatibility with any
        # downstream consumer that uses the Python enum's string value.
        lines = [
            f"#[derive({', '.join(derives)})]",
            f"pub enum {enum.name} {{",
        ]
        for member_name, member_value in enum.values:
            variant = _to_pascal_case(member_name)
            wire_value = (
                member_value if isinstance(member_value, str) else member_name
            )
            if wire_value != variant:
                lines.append(f'    #[serde(rename = "{wire_value}")]')
            lines.append(f"    {variant},")
        lines.append("}")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Variants
    # ------------------------------------------------------------------

    def _variant_to_struct_name(self, schema_name: str, variant_name: str) -> str:
        parts = variant_name.split("_")
        return schema_name + "".join(p.capitalize() for p in parts if p)

    def _generate_from_impl(
        self,
        source: str,
        target: str,
        source_fields: list[USRField],
        target_fields: list[USRField],
    ) -> str:
        """Emit a ``From<Source> for Target`` impl filling missing fields with ``Default::default()``.

        Only emitted when the source is a strict field-name subset of the
        target AND every field missing on the source side is either
        ``Option<T>`` (None) or otherwise filled via ``Default::default()``.
        """
        source_names = {f.name for f in source_fields}
        lines = [
            f"impl From<{source}> for {target} {{",
            f"    fn from(value: {source}) -> Self {{",
            "        Self {",
        ]
        for tf in target_fields:
            if tf.name in source_names:
                lines.append(f"            {tf.name}: value.{tf.name},")
            else:
                if tf.optional or tf.type == FieldType.OPTIONAL:
                    lines.append(f"            {tf.name}: None,")
                else:
                    lines.append(f"            {tf.name}: Default::default(),")
        lines.append("        }")
        lines.append("    }")
        lines.append("}")
        return "\n".join(lines)


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------


def _snake_case(name: str) -> str:
    """Convert PascalCase/camelCase to snake_case."""
    out: list[str] = []
    for i, ch in enumerate(name):
        if (
            ch.isupper()
            and i > 0
            and (
                not name[i - 1].isupper()
                or (i + 1 < len(name) and name[i + 1].islower())
            )
        ):
            out.append("_")
        out.append(ch.lower())
    return "".join(out)


def _to_pascal_case(name: str) -> str:
    """Convert SCREAMING_SNAKE_CASE or snake_case to PascalCase."""
    return "".join(part.capitalize() for part in name.split("_") if part)


def _split_field_blocks(lines: list[str]) -> list[list[str]]:
    """Split a flat list of field lines (with blank-line sentinels) into blocks."""
    blocks: list[list[str]] = []
    current: list[str] = []
    for line in lines:
        if line == "":
            if current:
                blocks.append(current)
                current = []
        else:
            current.append(line)
    if current:
        blocks.append(current)
    return blocks


def _variant_is_from_eligible(
    base_fields: list[USRField], variant_fields: list[USRField]
) -> bool:
    """Only emit ``From`` impls for variants that are strict subsets."""
    variant_names = {f.name for f in variant_fields}
    base_names = {f.name for f in base_fields}
    return variant_names.issubset(base_names) and variant_names != base_names
