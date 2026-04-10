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

# Rust built-in integer types accepted by Field(rust={"type": "..."}).
_VALID_RUST_INT_TYPES = frozenset(
    {
        "i8",
        "i16",
        "i32",
        "i64",
        "i128",
        "isize",
        "u8",
        "u16",
        "u32",
        "u64",
        "u128",
        "usize",
    }
)

# Rust built-in float types accepted by Field(rust={"type": "..."}).
_VALID_RUST_FLOAT_TYPES = frozenset({"f32", "f64"})


def _rust_field_ident(name: str) -> str:
    """Return the Rust identifier for a field name, escaping reserved words."""
    if name in _RUST_RESERVED_WORDS:
        return f"r#{name}"
    return name


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
    """Generates Rust structs and enums with serde derives from USR schemas.

    Emits one ``.rs`` file per ``@Schema`` plus a shared ``common.rs``
    for deduplicated enums, a ``lib.rs`` index with ``pub mod`` /
    ``pub use`` re-exports, and (by default) a minimal ``Cargo.toml``.
    Supports ``SerdeMeta`` on both schemas and enums, per-field
    integer/float width overrides via ``Field(rust={"type": ...})``,
    discriminated unions via ``Annotated[Union[...], Field(
    discriminator=...)]``, and ``Config.rust`` for crate-level
    settings. See ``docs/generators/rust.md`` for the full guide.
    """

    index_filename = "lib.rs"

    # Keys honored from ``Config.rust``. Any other key triggers a warning.
    _SUPPORTED_RUST_CONFIG_KEYS: frozenset[str] = frozenset(
        {
            "json_schema_derive",
            "deny_unknown_fields",
            "rename_all",
            "crate_name",
            "crate_version",
            "edition",
            "extra_deps",
            "emit_cargo_toml",
        }
    )

    def __init__(self, config: Any | None = None) -> None:  # type: ignore[override]
        super().__init__(config=config)
        # Enums deduplicated across all generated files into a shared
        # ``common.rs`` module (POC finding C1). Populated by the first
        # call to ``get_extra_files`` and consumed by ``generate_file``
        # so per-schema files skip re-emitting the shared enums.
        self._common_enum_names: set[str] = set()
        self._emit_common_module: bool = False
        # Per-call map of {field_name: helper_enum_name} for discriminated
        # unions. Set in generate_file before struct emission so
        # _rust_type_for can substitute the helper enum name in place of
        # the original Union type. Cleared afterwards.
        self._du_helper_names: dict[str, str] = {}
        # Name of the struct currently being emitted. Used by
        # _rust_type_for to detect direct self-references and wrap them
        # in Box<T> (Rust E0072: recursive type has infinite size).
        self._current_struct_name: str | None = None
        # Validate Config.rust keys and warn on unknown ones.
        self._warn_unknown_config_keys()

    def _warn_unknown_config_keys(self) -> None:
        """Log a warning for every key in ``Config.rust`` that is not
        in ``_SUPPORTED_RUST_CONFIG_KEYS``."""
        if self.config is None:
            return
        rust_cfg: dict[str, Any] = getattr(self.config, "rust", None) or {}
        for key in rust_cfg:
            if key not in self._SUPPORTED_RUST_CONFIG_KEYS:
                logger.warning(
                    "Unknown Config.rust key: %s (supported: %s)",
                    key,
                    sorted(self._SUPPORTED_RUST_CONFIG_KEYS),
                )

    def _rust_cfg(self) -> dict[str, Any]:
        """Return the ``Config.rust`` dict, or empty dict if not set."""
        if self.config is None:
            return {}
        return getattr(self.config, "rust", None) or {}

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

    def get_extra_files(
        self, schemas: list[USRSchema], output_dir: Path
    ) -> dict[str, str]:
        """Emit ``common.rs`` with all deduplicated enums and a
        ``Cargo.toml`` if enabled (POC findings C1 + C3).
        """
        extras: dict[str, str] = {}

        # Collect unique enums across every schema. First occurrence wins.
        seen: dict[str, USREnum] = {}
        for schema in schemas:
            for enum in schema.enums:
                if enum.name not in seen:
                    seen[enum.name] = enum
        self._common_enum_names = set(seen.keys())
        self._emit_common_module = bool(seen)

        if seen:
            json_schema_derive = self._rust_cfg().get("json_schema_derive", True)
            lines = [
                "// AUTO-GENERATED FILE - DO NOT EDIT MANUALLY",
                "// Generator: schema-gen Rust Serde generator",
                "// Shared enum definitions referenced by multiple schemas.",
                "",
                "use serde::{Deserialize, Serialize};",
            ]
            if json_schema_derive:
                lines.append("use schemars::JsonSchema;")
            lines.append("")
            lines.append("")
            for name in sorted(seen):
                lines.append(
                    self._generate_enum(
                        seen[name], json_schema_derive=json_schema_derive
                    )
                )
                lines.append("")
            extras["common.rs"] = "\n".join(lines).rstrip() + "\n"

        # Cargo.toml (Fix #C3) — honors Config.rust overrides.
        rust_cfg: dict[str, Any] = {}
        if self.config is not None:
            rust_cfg = getattr(self.config, "rust", None) or {}
        if rust_cfg.get("emit_cargo_toml", True):
            extras["Cargo.toml"] = _render_cargo_toml(rust_cfg)

        return extras

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

        # Shared enum module first so downstream modules can `use` it.
        if self._emit_common_module:
            lines.append("pub mod common;")
        for module in module_names:
            lines.append(f"pub mod {module};")

        if module_names or self._emit_common_module:
            lines.append("")

        if self._emit_common_module:
            lines.append("pub use common::*;")
        for module in module_names:
            lines.append(f"pub use {module}::*;")

        lines.append("")
        return "\n".join(lines)

    def generate_file(self, schema: USRSchema) -> str:
        """Emit a complete ``.rs`` file for a single schema."""
        custom_code = schema.custom_code.get("rust", {}) or {}
        global_cfg = self._rust_cfg()
        # Per-schema SerdeMeta overrides Config.rust global defaults.
        json_schema_derive = custom_code.get(
            "json_schema_derive", global_cfg.get("json_schema_derive", True)
        )

        imports: set[str] = set()
        body_parts: list[str] = []

        # Cross-module schema references → ``use super::other::Other;``
        # (POC finding C2). Collected before struct emission so the header
        # can render the correct ``use`` lines.
        external_schema_refs = _collect_external_schema_refs(schema)

        # Schema-level rename_all (from SerdeMeta) — if set and valid, it
        # applies uniformly across both the struct and every emitted enum
        # in this schema. Falls back to Config.rust global default. Enums
        # fall back to per-variant `rename` attributes (preserving the Python
        # enum value) when no rename_all is given.
        schema_rename_all = custom_code.get("rename_all", global_cfg.get("rename_all"))
        enum_rename_all = (
            schema_rename_all if schema_rename_all in _VALID_RENAME_ALL else None
        )

        # Enums: when running under the engine (generate_all), shared
        # enums live in ``common.rs`` — don't re-emit them here. When the
        # generator is used standalone (direct generate_file call in a
        # test), ``_common_enum_names`` is empty and all enums are
        # emitted inline as before.
        for enum in schema.enums:
            if enum.name in self._common_enum_names:
                continue
            body_parts.append(
                self._generate_enum(
                    enum,
                    json_schema_derive=json_schema_derive,
                    rename_all=enum_rename_all,
                )
            )

        # Discriminated-union helper enums (#18). For each field on the
        # base struct that carries a discriminator + resolved tag values,
        # emit a serde-tagged enum so the field can reference it by name.
        # The struct itself replaces the field's type with the helper
        # enum name during _rust_type_for via the helper-name lookup.
        du_helper_names: dict[str, str] = {}
        for f in schema.fields:
            if f.discriminator and f.union_types and f.union_tag_values:
                helper_name = self._discriminated_union_helper_name(schema.name, f.name)
                du_helper_names[f.name] = helper_name
                body_parts.append(
                    self._generate_discriminated_union_enum(
                        helper_name=helper_name,
                        discriminator=f.discriminator,
                        variants=f.union_types,
                        tag_values=f.union_tag_values,
                        json_schema_derive=json_schema_derive,
                        imports=imports,
                    )
                )
        # Hand the helper-name map down via a struct attribute so
        # _rust_type_for can read it without changing every signature.
        # Cleared after struct emission to avoid leaking across calls.
        self._du_helper_names = du_helper_names

        # Base struct
        self._current_struct_name = schema.name
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
        self._current_struct_name = None
        self._du_helper_names = {}

        # Variant structs
        base_field_names = {f.name for f in schema.fields}
        for variant_name in schema.variants:
            variant_fields = schema.get_variant_fields(variant_name)
            variant_struct_name = self._variant_to_struct_name(
                schema.name, variant_name
            )
            self._current_struct_name = variant_struct_name
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
            self._current_struct_name = None

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
            external_schema_refs=external_schema_refs,
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
        global_cfg = self._rust_cfg()
        json_schema_derive = custom_code.get(
            "json_schema_derive", global_cfg.get("json_schema_derive", True)
        )

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
        external_schema_refs: set[str] | None = None,
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

        # Shared enum module (POC finding C1 + C2). Pulled in via
        # ``use super::common::*;`` so enum names resolve without
        # fully-qualified paths.
        if self._emit_common_module:
            lines.append("use super::common::*;")

        # Cross-module schema references (POC finding C2). Emit an
        # explicit ``use super::<module>::<Type>;`` for every nested
        # schema name that is NOT this schema itself.
        for ref_name in sorted(external_schema_refs or ()):
            if ref_name == schema.name:
                continue
            module = _snake_case(ref_name)
            lines.append(f"use super::{module}::{ref_name};")

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

        global_cfg = self._rust_cfg()
        deny_unknown = global_cfg.get("deny_unknown_fields", True)
        if is_base and "deny_unknown_fields" in (custom_code or {}):
            deny_unknown = bool(custom_code["deny_unknown_fields"])

        serde_struct_attrs: list[str] = []
        if deny_unknown:
            serde_struct_attrs.append("deny_unknown_fields")

        # Per-schema override takes precedence; fall back to Config.rust.
        rename_all = (
            ((custom_code or {}).get("rename_all") or global_cfg.get("rename_all"))
            if is_base
            else None
        )
        if rename_all is not None:
            if rename_all in _VALID_RENAME_ALL:
                serde_struct_attrs.append(f'rename_all = "{rename_all}"')
            else:
                logger.warning(
                    "Rust generator: ignoring invalid SerdeMeta.rename_all=%r "
                    "on struct %s (valid: %s).",
                    rename_all,
                    struct_name,
                    sorted(_VALID_RENAME_ALL),
                )

        if serde_struct_attrs:
            lines.append(f"#[serde({', '.join(serde_struct_attrs)})]")

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
        emitted_name = _rust_field_ident(name)

        if name in _RUST_RESERVED_WORDS:
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

    def _rust_type_for(
        self,
        field: USRField,
        imports: set[str],
        *,
        inside_container: bool = False,
    ) -> str:
        """Map a USR field to a Rust type string."""
        # Optional with inner_type → recurse on the inner.
        # Option is NOT a heap-allocated container, so self-references
        # inside Option still need Box<T>.
        if field.type == FieldType.OPTIONAL and field.inner_type is not None:
            return f"Option<{self._rust_type_for(field.inner_type, imports, inside_container=inside_container)}>"

        # Many parsers emit ``optional=True`` + ``inner_type`` while keeping
        # ``field.type`` as the underlying type (e.g. INTEGER). For such
        # fields the caller wraps the result in ``Option<...>`` separately,
        # so here we just resolve the base type.
        ftype = field.type

        # Per-field Rust-specific overrides via Field(rust={"type": "u32"}).
        # Validated against Rust's built-in integer/float type whitelists;
        # invalid values log a warning and fall back to the default.
        rust_override = (field.target_config or {}).get("rust", {}) or {}
        override_type = rust_override.get("type")

        if ftype == FieldType.STRING:
            return "String"
        if ftype == FieldType.INTEGER:
            if override_type:
                if override_type in _VALID_RUST_INT_TYPES:
                    return override_type
                logger.warning(
                    "Rust generator: ignoring invalid Field(rust={'type': %r}) "
                    "on integer field '%s' (valid: %s). Falling back to i64.",
                    override_type,
                    field.name,
                    sorted(_VALID_RUST_INT_TYPES),
                )
            return "i64"
        if ftype == FieldType.FLOAT:
            if override_type:
                if override_type in _VALID_RUST_FLOAT_TYPES:
                    return override_type
                logger.warning(
                    "Rust generator: ignoring invalid Field(rust={'type': %r}) "
                    "on float field '%s' (valid: %s). Falling back to f64.",
                    override_type,
                    field.name,
                    sorted(_VALID_RUST_FLOAT_TYPES),
                )
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
                inner = self._rust_type_for(
                    field.inner_type, imports, inside_container=True
                )
                return f"Vec<{inner}>"
            return "Vec<serde_json::Value>"

        if ftype == FieldType.DICT:
            imports.add("HashMap")
            # We don't currently thread a value type through USR for dicts
            # so default to ``serde_json::Value`` (matches ``dict[str, Any]``).
            return "HashMap<String, serde_json::Value>"

        if ftype == FieldType.TUPLE:
            if field.union_types:
                parts = [
                    self._rust_type_for(t, imports, inside_container=True)
                    for t in field.union_types
                ]
                return f"({', '.join(parts)})"
            return "Vec<serde_json::Value>"

        if ftype == FieldType.UNION:
            # Discriminated union (#18): substitute the per-struct helper
            # enum name. The helper is emitted earlier in generate_file.
            helper = self._du_helper_names.get(field.name)
            if helper:
                return helper
            logger.warning(
                "Rust generator: union field '%s' emitted as serde_json::Value. "
                "Use Field(discriminator='<tag>') with Annotated[Union[...]] to "
                "emit a serde-tagged enum instead. See schema-gen#18.",
                field.name,
            )
            # Return a bare type so the struct emission stays valid Rust.
            # Inline comments embedded in a type position produce syntax
            # errors in generated structs — the warning above is the only
            # user-facing signal.
            return "serde_json::Value"

        if ftype == FieldType.LITERAL:
            # Treat as a string-valued enum at the type level; v1 keeps it
            # simple and just uses String.
            return "String"

        if ftype == FieldType.ENUM:
            return field.enum_name or "String"

        if ftype == FieldType.NESTED_SCHEMA:
            # Discriminated union (#18): when the parser resolves a
            # Union via types.UnionType (Python 3.12+ pipe syntax),
            # the field may be typed as NESTED_SCHEMA rather than UNION.
            # Check the helper-name map so the struct field references
            # the helper enum.
            helper = self._du_helper_names.get(field.name)
            if helper:
                return helper
            nested = field.nested_schema or "serde_json::Value"
            # Python 3.12+ pipe unions (A | B) may be stored as a
            # stringified UnionType in nested_schema. This is not a
            # valid Rust type — fall back to serde_json::Value (same
            # as the plain Union path) and warn.
            if "|" in nested:
                logger.warning(
                    "Rust generator: union field '%s' emitted as serde_json::Value. "
                    "Use Field(discriminator='<tag>') with Annotated[Union[...]] to "
                    "emit a serde-tagged enum instead. See schema-gen#18.",
                    field.name,
                )
                return "serde_json::Value"
            # Direct self-reference requires Box<T> to avoid E0072
            # (recursive type has infinite size). Vec<T> and other
            # heap-allocated containers are already on the heap, so
            # Box is unnecessary there.
            if nested == self._current_struct_name and not inside_container:
                return f"Box<{nested}>"
            return nested

        return "serde_json::Value"

    def _generate_enum(
        self,
        enum: USREnum,
        json_schema_derive: bool,
        rename_all: str | None = None,
    ) -> str:
        # Pull SerdeMeta extras attached to the Enum class itself (extra
        # derives, raw_code impl blocks). Mirrors the per-struct mechanism
        # so users can attach `is_terminal()` etc. directly on the enum.
        enum_meta = (enum.custom_code or {}).get("rust", {}) or {}

        derives = list(_DEFAULT_ENUM_DERIVES)
        if json_schema_derive:
            derives.append("JsonSchema")
        for extra in enum_meta.get("derives", []) or []:
            if extra not in derives:
                derives.append(extra)

        lines = [f"#[derive({', '.join(derives)})]"]

        # Per-variant `#[serde(rename = "<value>")]` using the actual enum
        # value from the IR is the correct default: it's the only way to
        # preserve mixed wire-format casings (e.g. NSE="NSE" + buy="buy")
        # without silently losing the Python enum value.
        #
        # Users who want a uniform transform instead (e.g. all lowercase)
        # can set SerdeMeta.rename_all on the schema; in that case we
        # delegate to serde's `rename_all` at the enum level and skip the
        # per-variant renames entirely.
        if rename_all is not None:
            lines.append(f'#[serde(rename_all = "{rename_all}")]')
            lines.append(f"pub enum {enum.name} {{")
            for member_name, _member_value in enum.values:
                variant = _to_pascal_case(member_name)
                lines.append(f"    {variant},")
        else:
            lines.append(f"pub enum {enum.name} {{")
            for member_name, member_value in enum.values:
                variant = _to_pascal_case(member_name)
                wire_value = (
                    member_value if isinstance(member_value, str) else member_name
                )
                if wire_value != variant:
                    lines.append(f'    #[serde(rename = "{wire_value}")]')
                lines.append(f"    {variant},")
        lines.append("}")

        # Append SerdeMeta.raw_code (typically an `impl Enum { ... }` block)
        # after the enum definition. Imports requested via SerdeMeta.imports
        # on enums are intentionally NOT handled here — they'd need to be
        # threaded through the per-file header. Users can put `use ...;`
        # lines inside raw_code if needed.
        raw_code = (enum_meta.get("raw_code") or "").strip()
        if raw_code:
            lines.append("")
            lines.append(raw_code)

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Discriminated unions (#18)
    # ------------------------------------------------------------------

    def _discriminated_union_helper_name(
        self, schema_name: str, field_name: str
    ) -> str:
        """Build the helper enum name for a discriminated-union field.

        Convention: ``<StructName><CamelFieldName>`` — matches the user
        spec example (Order + leg → OrderLeg). Field-name conflicts with
        existing types are the user's responsibility for v1.
        """
        return schema_name + _to_pascal_case(field_name)

    def _generate_discriminated_union_enum(
        self,
        helper_name: str,
        discriminator: str,
        variants: list[USRField],
        tag_values: list[str],
        json_schema_derive: bool,
        imports: set[str],
    ) -> str:
        """Emit a serde internally-tagged enum for a discriminated union.

        Each variant becomes ``VariantName(VariantStruct)`` with
        ``#[serde(rename = "<literal>")]`` if the wire tag differs from
        the variant identifier. The struct field referencing this enum
        will resolve through ``_du_helper_names`` in ``_rust_type_for``.
        """
        # Trim the JsonSchema derive separately because schemars 0.8 supports
        # it on tagged enums but a few older toolchains balk; we keep it
        # consistent with regular enums for now.
        derives = ["Debug", "Clone", "PartialEq", "Serialize", "Deserialize"]
        if json_schema_derive:
            derives.append("JsonSchema")

        lines = [
            f"#[derive({', '.join(derives)})]",
            f'#[serde(tag = "{discriminator}")]',
            f"pub enum {helper_name} {{",
        ]
        for variant, tag in zip(variants, tag_values, strict=True):
            variant_struct = variant.nested_schema or "serde_json::Value"
            variant_ident = _to_pascal_case(tag) if tag else variant_struct
            # Ensure the variant struct is importable from this file. The
            # existing _collect_external_schema_refs covers it because the
            # union member is itself a NESTED_SCHEMA reference.
            if variant_ident != tag:
                lines.append(f'    #[serde(rename = "{tag}")]')
            lines.append(f"    {variant_ident}({variant_struct}),")
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
        """Emit a ``From<Source> for Target`` impl filling missing fields.

        Only called after ``_variant_is_from_eligible`` has verified every
        field missing on the source side is either ``Option<T>`` (None) or
        has an explicit default (``Default::default()``).
        """
        source_names = {f.name for f in source_fields}
        lines = [
            f"impl From<{source}> for {target} {{",
            f"    fn from(value: {source}) -> Self {{",
            "        Self {",
        ]
        for tf in target_fields:
            ident = _rust_field_ident(tf.name)
            if tf.name in source_names:
                lines.append(f"            {ident}: value.{ident},")
            else:
                if _field_is_optional(tf):
                    lines.append(f"            {ident}: None,")
                else:
                    lines.append(f"            {ident}: Default::default(),")
        lines.append("        }")
        lines.append("    }")
        lines.append("}")
        return "\n".join(lines)


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------


def _snake_case(name: str) -> str:
    """Convert PascalCase/camelCase to snake_case.

    Leading underscores are stripped so that Python-convention private
    prefixes (``_CeLeg``, ``__DoublePrivate``) don't produce module
    names starting with ``__`` which look like reserved internals in Rust
    and trigger clippy warnings.
    """
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


def _collect_external_schema_refs(schema: USRSchema) -> set[str]:
    """Return the set of NESTED_SCHEMA names referenced by a schema.

    Walks through ``inner_type`` and ``union_types`` so nested containers
    (lists, unions, tuples) produce imports too. The caller filters out
    self-references when emitting ``use`` lines.

    Fields with a discriminator are handled separately (their union
    variants already appear in ``union_types``), so the top-level
    ``nested_schema`` (which may be a garbage ``UnionType.__str__``)
    is skipped.
    """
    refs: set[str] = set()

    def _walk(field: USRField, *, skip_top_nested: bool = False) -> None:
        if (
            field.type == FieldType.NESTED_SCHEMA
            and field.nested_schema
            and not skip_top_nested
        ):
            refs.add(field.nested_schema)
        if field.inner_type is not None:
            _walk(field.inner_type)
        for ut in field.union_types or []:
            _walk(ut)

    for f in schema.fields:
        # When a field carries a discriminator its nested_schema may be
        # the string repr of a Python UnionType (e.g. "mod._A | mod._B")
        # which is not a valid Rust import. Skip it; the individual
        # union_types already contribute their nested_schema names.
        _walk(f, skip_top_nested=bool(f.discriminator and f.union_types))
    return refs


def _render_cargo_toml(rust_cfg: dict[str, Any]) -> str:
    """Render a minimal ``Cargo.toml`` for the generated crate.

    Honors ``Config.rust`` overrides:
      - ``crate_name`` (default ``schema-gen-generated-contracts``)
      - ``crate_version`` (default ``0.0.0``)
      - ``edition`` (default ``2021``)
      - ``extra_deps`` (mapping of crate name → version string)
    """
    name = rust_cfg.get("crate_name", "schema-gen-generated-contracts")
    version = rust_cfg.get("crate_version", "0.0.0")
    edition = rust_cfg.get("edition", "2021")
    extra_deps: dict[str, Any] = rust_cfg.get("extra_deps", {}) or {}

    lines = [
        "# AUTO-GENERATED FILE - DO NOT EDIT MANUALLY",
        "# Generator: schema-gen Rust Serde generator",
        "",
        "[package]",
        f'name = "{name}"',
        f'version = "{version}"',
        f'edition = "{edition}"',
        'description = "Auto-generated contract types from schema-gen"',
        'license = "MIT OR Apache-2.0"',
        "",
        "[lib]",
        'path = "lib.rs"',
        "",
        "[dependencies]",
        'serde = { version = "1", features = ["derive"] }',
        'chrono = { version = "0.4", features = ["serde"] }',
        'schemars = "0.8"',
    ]
    for crate, spec in sorted(extra_deps.items()):
        if isinstance(spec, str):
            lines.append(f'{crate} = "{spec}"')
        else:
            # Assume a pre-formatted inline table string provided by the user.
            lines.append(f"{crate} = {spec}")
    lines.append("")
    return "\n".join(lines)


def _field_is_optional(field: USRField) -> bool:
    """Return True if a field is optional (None is a valid value)."""
    if field.type == FieldType.OPTIONAL:
        return True
    return bool(getattr(field, "optional", False))


def _field_has_explicit_default(field: USRField) -> bool:
    """Return True if the field has an explicit, usable default value.

    We treat any of ``default``, ``default_factory``, ``default_value``,
    ``has_default``, or ``schema_default`` being set as evidence of an
    explicit default. USRField populates ``default=None`` by convention,
    so we also look at ``default_factory`` which is the more reliable
    marker for "user supplied a default" across parsers.
    """
    if getattr(field, "default_factory", None) is not None:
        return True
    if getattr(field, "has_default", False):
        return True
    for attr in ("default_value", "schema_default"):
        if getattr(field, attr, None) is not None:
            return True
    default = getattr(field, "default", None)
    return default is not None


def _variant_is_from_eligible(
    base_fields: list[USRField], variant_fields: list[USRField]
) -> bool:
    """Decide whether to emit a ``From<Variant> for Full`` impl.

    The variant must be a strict field-name subset of the base, AND every
    field missing on the variant side must either be optional (None) or
    have an explicit default. Otherwise the ``From`` impl would emit
    ``missing: Default::default()`` for a type that doesn't implement
    ``Default``, which fails to compile.
    """
    variant_names = {f.name for f in variant_fields}
    base_names = {f.name for f in base_fields}
    if not variant_names.issubset(base_names) or variant_names == base_names:
        return False
    missing = [f for f in base_fields if f.name not in variant_names]
    for f in missing:
        if _field_is_optional(f):
            continue
        if _field_has_explicit_default(f):
            continue
        return False
    return True
