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
    """Return the Rust identifier for a field name.

    Handles two cases:

    - Reserved words (e.g. ``type``) → ``r#type`` with ``#[serde(rename)]``.
    - Non-snake_case names (e.g. ``theta_vega_ratio_CE_otm``) → lowercased
      with consecutive underscores collapsed (``theta_vega_ratio_ce_otm``);
      caller must add ``#[serde(rename = "<original>")]`` to preserve the
      wire format.

    After snake_case normalization the resulting identifier is re-checked
    against :data:`_RUST_RESERVED_WORDS` and escaped with ``r#`` if needed
    (e.g. the schema field ``TYPE`` normalises to ``type``).

    Note: :func:`_snake_case` strips leading underscores from the name before
    converting, consistent with its struct-name behavior.  Schema field names
    that start with ``_`` will therefore have the prefix dropped in the emitted
    Rust identifier (the serde rename preserves the original wire key).

    Use :func:`_rust_field_wire_name` to determine whether a rename attribute
    is needed.
    """
    import re  # noqa: PLC0415 — local import to avoid module-level churn

    if name in _RUST_RESERVED_WORDS:
        return f"r#{name}"

    # If the name contains uppercase letters it is not valid Rust snake_case
    # and ``rustc`` will emit a ``non_snake_case`` warning.  Convert to proper
    # snake_case by lowercasing after word boundaries, then collapse any run of
    # consecutive underscores to a single underscore that arise when uppercase
    # sequences are preceded or followed by an existing underscore
    # (e.g. ``ratio_CE_otm`` → ``ratio__ce_otm`` → ``ratio_ce_otm``).
    if any(c.isupper() for c in name):
        snake = _snake_case(name)
        snake = re.sub(r"_+", "_", snake)
        # Re-check: normalisation may have produced a reserved keyword
        # (e.g. the field ``TYPE`` normalises to ``type``).
        if snake in _RUST_RESERVED_WORDS:
            return f"r#{snake}"
        return snake

    return name


def _rust_field_wire_name(name: str) -> str | None:
    """Return the original wire-format name when a ``#[serde(rename)]`` is needed.

    Returns ``name`` when the Rust identifier differs from the original field
    name (reserved-word escape or non-snake_case conversion), ``None`` when
    no rename attribute is required.
    """
    ident = _rust_field_ident(name)
    # r#foo → the Rust identifier differs; wire name is bare ``foo``.
    if name in _RUST_RESERVED_WORDS:
        return name
    # Non-snake_case → the Rust ident was lowercased; wire name is original.
    if ident != name:
        return name
    return None


def _rust_string_literal(value: str) -> str:
    """Render ``value`` as a double-quoted Rust string literal.

    Escapes the four characters that would otherwise produce invalid
    Rust source when interpolated into ``"..."``: backslash (must be
    doubled), double-quote (must be backslash-escaped), and the two
    common control characters that appear in user input (newline and
    carriage return). Other control characters are unlikely in alias
    values but pass through unchanged — Rust accepts arbitrary UTF-8
    inside string literals.

    Used for ``#[serde(rename = "<alias>")]`` and the alias-driven
    entries in ``<TAG>_FIELDS`` constants so a user-supplied alias like
    ``Field(alias='owner"id')`` does not break the emitted ``.rs``.
    """
    return (
        '"'
        + value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        + '"'
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

        # Field-tag constants (#82)
        tag_groups = schema.get_tagged_fields()
        if tag_groups:
            body_parts.append(self._generate_tag_constants(tag_groups, schema.fields))

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

        # Discriminated-union variant structs carry a ``#[serde(skip)]`` tag
        # field (#18 round-trip fix). A skipped field is reconstructed via
        # ``Default::default()`` on deserialize, so the struct must derive
        # ``Default``. Added here (not in _DEFAULT_STRUCT_DERIVES) so only
        # the affected structs pick it up.
        if any(getattr(f, "is_discriminator_tag", False) for f in fields):
            if "Default" not in derives:
                derives.append("Default")

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

        # Detect identifier collisions before generating — two schema fields
        # can normalise to the same Rust snake_case identifier (e.g.
        # ``ratio_CE_otm`` and ``ratio_ce_otm`` both → ``ratio_ce_otm``).
        # Fail fast with a clear message rather than emitting invalid Rust.
        seen_idents: dict[str, str] = {}
        for field in fields:
            ident = _rust_field_ident(field.name)
            # Strip the exact r# prefix when checking for collisions so that
            # ``r#type`` and ``type`` (impossible in practice, but defensive)
            # are treated as the same identifier.
            bare = ident[2:] if ident.startswith("r#") else ident
            if bare in seen_idents:
                msg = (
                    f"Schema '{struct_name}': fields '{seen_idents[bare]}' and "
                    f"'{field.name}' both normalise to the Rust identifier "
                    f"'{ident}'. Rename one field in the schema source."
                )
                raise ValueError(msg)
            seen_idents[bare] = field.name

        # Pre-compute helper fn names for fields with non-trivial defaults
        # (issue #115). Done before field generation so the name is available
        # to _generate_field without relying on mutable instance state.
        field_helper_names: dict[str, str] = {}
        for f in fields:
            if _needs_default_helper(f):
                field_helper_names[f.name] = _default_helper_fn_name(struct_name, f)

        field_lines: list[str] = []
        for field in fields:
            field_lines.extend(
                self._generate_field(field, imports, field_helper_names.get(field.name))
            )

        # Join fields with blank lines between each for readability. Each
        # field may contain doc comments + serde attrs + the field itself.
        for i, block in enumerate(_split_field_blocks(field_lines)):
            if i > 0:
                lines.append("")
            lines.extend("    " + line if line else "" for line in block)

        lines.append("}")
        struct_str = "\n".join(lines)

        # Emit helper functions (if any) before the struct definition so
        # serde can resolve ``default = "fn_name"`` in the current module.
        helper_fns: list[str] = []
        for f in fields:
            fn_name = field_helper_names.get(f.name)
            if fn_name:
                rust_type = self._rust_type_for(f, imports)
                fn_str = _generate_default_helper_fn(fn_name, f, rust_type)
                if fn_str:
                    helper_fns.append(fn_str)

        if helper_fns:
            return "\n".join(helper_fns) + "\n\n" + struct_str
        return struct_str

    def _generate_field(
        self,
        field: USRField,
        imports: set[str],
        default_helper_name: str | None = None,
    ) -> list[str]:
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

        # Discriminated-union tag field (#18 round-trip fix). When this
        # struct is a variant of a serde internally-tagged enum, serde owns
        # the discriminator key on the wire: it is consumed on deserialize
        # and re-emitted from the enum variant identity on serialize. The
        # variant struct must therefore NOT (de)serialize the field itself,
        # or serde double-emits / fails on the missing key. ``skip`` drops
        # it from both directions; the value is reconstructed via the
        # struct's ``Default`` derive on deserialize. This branch is
        # mutually exclusive with rename/default/alias handling below.
        if getattr(field, "is_discriminator_tag", False):
            out.append("#[serde(skip)]")
            out.append(f"pub {emitted_name}: {rust_type},")
            out.append("")
            return out

        # Per-field alias (issue #108) wins over the name-based wire-name
        # heuristic. The user wrote ``Field(alias="...")`` precisely to
        # override the wire key. Suppress the rename only when the alias
        # equals serde's effective default wire key for this field —
        # NOT the Rust identifier. The two diverge for raw identifiers:
        # a field named ``type`` has identifier ``r#type`` but serde
        # serializes it as ``"type"``, so a user opting in with
        # ``alias="r#type"`` MUST emit a rename to land that wire key.
        explicit_alias = getattr(field, "alias", None)
        if explicit_alias is not None:
            default_wire_key = _rust_field_wire_name(name) or name
            if explicit_alias != default_wire_key:
                serde_attrs.append(f"rename = {_rust_string_literal(explicit_alias)}")
        else:
            wire_name = _rust_field_wire_name(name)
            if wire_name is not None:
                serde_attrs.append(f"rename = {_rust_string_literal(wire_name)}")

        if is_optional:
            serde_attrs.append('skip_serializing_if = "Option::is_none"')
        elif _field_has_explicit_default(field):
            if _rust_type_has_native_default(field):
                # Zero-value default matches Rust's Default::default() — serde
                # can call Default::default() directly when the field is absent.
                serde_attrs.append("default")
            elif default_helper_name is not None:
                # Non-trivial default (e.g. String "drop_and_audit", int 42,
                # bool True) — serde calls a named free function instead of
                # Default::default() so the correct value is used.
                serde_attrs.append(f'default = "{default_helper_name}"')

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
            # dict[str, Any] or plain dict -> serde_json::Value (any JSON)
            # dict[str, T] where T is a specific type -> HashMap<String, T>
            if field.inner_type is None or field.inner_type.type == FieldType.JSON:
                return "serde_json::Value"
            imports.add("HashMap")
            value_type = self._rust_type_for(
                field.inner_type, imports, inside_container=True
            )
            return f"HashMap<String, {value_type}>"

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

        lines: list[str] = []
        if enum.docstring:
            for doc_line in enum.docstring.splitlines():
                if doc_line.strip():
                    lines.append(f"/// {doc_line.strip()}")
                else:
                    lines.append("///")
        lines.append(f"#[derive({', '.join(derives)})]")

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
    # Field-tag constants (#82)
    # ------------------------------------------------------------------

    def _generate_tag_constants(
        self,
        tag_groups: dict[str, list[str]],
        fields: list[USRField],
    ) -> str:
        """Emit ``pub const <TAG>_FIELDS: &[&str]`` for each tag group.

        Wire names prefer ``field.alias`` (issue #108) over the
        name-based heuristic so the constant matches the serialized
        keys consumers actually see.
        """
        by_name: dict[str, USRField] = {f.name: f for f in fields}
        lines: list[str] = []
        for tag, field_names in tag_groups.items():
            wire_names: list[str] = []
            for n in field_names:
                f = by_name.get(n)
                alias = getattr(f, "alias", None) if f is not None else None
                if alias is not None:
                    wire_names.append(alias)
                else:
                    wire_names.append(_rust_field_wire_name(n) or n)
            values = ", ".join(_rust_string_literal(w) for w in wire_names)
            lines.append(f"pub const {tag.upper()}_FIELDS: &[&str] = &[{values}];")
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
    ]
    # Default base deps — overridable via extra_deps
    base_deps = {
        "serde": '{ version = "1", features = ["derive"] }',
        "chrono": '{ version = "0.4", features = ["serde"] }',
        "schemars": '"0.8"',
    }
    for crate, default_spec in base_deps.items():
        if crate not in extra_deps:
            lines.append(f"{crate} = {default_spec}")
    for crate, spec in sorted(extra_deps.items()):
        if isinstance(spec, str) and not spec.lstrip().startswith("{"):
            # Simple version string — wrap in quotes
            lines.append(f'{crate} = "{spec}"')
        else:
            # Inline table or pre-formatted TOML — emit verbatim
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


def _rust_type_has_native_default(field: USRField) -> bool:
    """Return True if the field's Rust type implements ``Default`` natively AND
    the Python-side default value matches what ``Default::default()`` would produce.

    Used to guard ``#[serde(default)]`` emission — only types that implement
    ``Default`` without a hand-written impl can be annotated this way. Emitting
    it on an ``ENUM`` or ``NESTED_SCHEMA`` field whose generated Rust type does
    not derive/impl ``Default`` causes a compile error.

    Additionally, we only emit ``#[serde(default)]`` when the Python default
    matches Rust's zero-value default for the type. If the Python default is a
    non-trivial value (e.g. ``default="drop_and_audit"`` for a String field), the
    ``Default::default()`` impl would produce ``""`` instead, creating a mismatch
    between what the contract deserializes and what the runtime expects.

    Types with native ``Default`` in Rust and their zero-value defaults:
    - Primitives: INTEGER → 0/0.0, BOOLEAN → false
    - String (DEFAULT = "")
    - LIST / SET / FROZENSET (Vec<T> — Default = empty vec, requires T: Default)
    - JSON / DICT (serde_json::Value — Default = Value::Null)

    Unsafe types (may not have Default):
    - ENUM — only if ``#[derive(Default)]`` is explicitly added
    - NESTED_SCHEMA — only if all fields have defaults or derive(Default)
    - UNION, OPTIONAL (handled by the is_optional path)
    """
    safe_types = frozenset(
        {
            FieldType.STRING,
            FieldType.INTEGER,
            FieldType.FLOAT,
            FieldType.BOOLEAN,
            FieldType.LIST,
            FieldType.SET,
            FieldType.FROZENSET,
            FieldType.JSON,  # serde_json::Value (Default = Value::Null)
            FieldType.DICT,  # serde_json::Value when inner_type is None/JSON
        }
    )
    if field.type not in safe_types:
        return False

    # Verify the Python default matches the Rust Default::default() value.
    # If the Python default is non-trivial (e.g. a non-empty string or non-zero int),
    # emitting #[serde(default)] would produce the WRONG value when the JSON field
    # is absent — Rust's Default::default() would kick in instead of the intended
    # Python default. Only emit for fields whose Python default IS the zero-value.
    default = getattr(field, "default", None)
    # default_factory always maps to Rust's container Default (empty Vec/Value)
    if getattr(field, "default_factory", None) is not None:
        return True
    if default is None:
        # No explicit default — default_factory must be set; covered above.
        return False
    # Check that the Python default matches the Rust zero-value for the type.
    if field.type == FieldType.STRING:
        return default == ""
    if field.type in (FieldType.INTEGER, FieldType.FLOAT):
        return default == 0 or default == 0.0
    if field.type == FieldType.BOOLEAN:
        return default is False or default == False  # noqa: E712
    # JSON/DICT: Python None (null) maps to serde_json::Value::Null
    if field.type in (FieldType.JSON, FieldType.DICT):
        return default is None
    # LIST/SET/FROZENSET: empty sequence (but should be default_factory, caught above)
    if field.type in (FieldType.LIST, FieldType.SET, FieldType.FROZENSET):
        return isinstance(default, (list, set, frozenset)) and len(default) == 0
    return False


def _needs_default_helper(field: USRField) -> bool:
    """Return True when a field needs a serde default helper function.

    This applies to non-optional fields whose explicit default is a non-zero
    value — i.e. cases where ``#[serde(default)]`` would call the wrong
    ``Default::default()`` instead of the intended value.  Only STRING,
    INTEGER, FLOAT, and BOOLEAN are handled; other types (ENUM, NESTED_SCHEMA,
    datetime, …) need a hand-written impl or derive(Default) and are out of
    scope for auto-generation.

    Requires ``field.default`` to be non-None so that
    ``_generate_default_helper_fn`` can emit a concrete Rust literal.
    Fields where ``has_default=True`` / ``schema_default`` / ``default_value``
    is set but ``field.default is None`` fall through without a helper; the
    struct field will have no serde default attribute, which is the safest
    fallback (missing JSON key → deserialization error with a clear message
    rather than silently referencing a missing free function).
    """
    if field.optional or field.type == FieldType.OPTIONAL:
        return False
    if getattr(field, "default", None) is None:
        return False
    if not _field_has_explicit_default(field):
        return False
    if _rust_type_has_native_default(field):
        return False  # zero-value → serde(default) is sufficient
    return field.type in (
        FieldType.STRING,
        FieldType.INTEGER,
        FieldType.FLOAT,
        FieldType.BOOLEAN,
    )


def _default_helper_fn_name(struct_name: str, field: USRField) -> str:
    """Return the serde default helper function name for ``field``.

    Uses ``default_<struct_snake>_<field_bare_ident>`` so that multiple
    structs in the same ``.rs`` file (e.g. base + variant) can each have a
    field with the same name without producing duplicate free-function
    definitions.
    """
    struct_snake = _snake_case(struct_name)
    field_ident = _rust_field_ident(field.name)
    bare_ident = field_ident[2:] if field_ident.startswith("r#") else field_ident
    return f"default_{struct_snake}_{bare_ident}"


def _generate_default_helper_fn(fn_name: str, field: USRField, rust_type: str) -> str:
    """Emit a free function used as ``#[serde(default = "<fn_name>")]``.

    The function returns the field's Python-side default as a Rust literal.
    Returns an empty string when the default cannot be represented (should
    not occur given ``_needs_default_helper`` guards the call site).
    """
    import math  # noqa: PLC0415

    default = getattr(field, "default", None)
    if default is None:
        return ""
    if field.type == FieldType.STRING:
        body = f"{_rust_string_literal(str(default))}.to_string()"
    elif field.type == FieldType.INTEGER:
        body = str(int(default))
    elif field.type == FieldType.FLOAT:
        val = float(default)
        if math.isnan(val):
            body = f"{rust_type}::NAN"
        elif math.isinf(val):
            body = f"{rust_type}::INFINITY" if val > 0 else f"{rust_type}::NEG_INFINITY"
        else:
            body = str(val)
    elif field.type == FieldType.BOOLEAN:
        body = "true" if default else "false"
    else:
        return ""
    return f"fn {fn_name}() -> {rust_type} {{ {body} }}"


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
