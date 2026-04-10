"""Registry index builder for schema-gen.

Takes a list of USRSchema objects and produces a deterministic registry
index dict that catalogues all types, enums, cross-references, domains,
and variants.
"""

from __future__ import annotations

import datetime
from typing import Any

from .. import __version__
from ..core.config import Config
from ..core.usr import FieldType, USRField, USRSchema

REGISTRY_INDEX_VERSION = "1.0.0"


def build_registry_index(
    schemas: list[USRSchema],
    config: Config,
) -> dict[str, Any]:
    """Build a registry index from parsed USR schemas.

    The result is deterministic: given the same input schemas and config,
    the output dict is identical except for the ``generated_at`` timestamp.

    Args:
        schemas: Parsed USR schemas.
        config: Generation configuration (used for domain detection via
            ``input_dir``).

    Returns:
        Registry index dict ready for JSON serialization.
    """
    types_index: dict[str, dict[str, Any]] = {}
    enums_index: dict[str, dict[str, Any]] = {}

    # First pass: collect all enum names and their values.
    all_enums: dict[str, list[tuple[str, Any]]] = {}
    for schema in schemas:
        for enum in schema.enums:
            all_enums[enum.name] = enum.values

    # Second pass: build type entries and track enum usage.
    enum_used_by: dict[str, set[str]] = {name: set() for name in all_enums}

    for schema in sorted(schemas, key=lambda s: s.name):
        domain = _detect_domain(schema, config)
        enums_referenced: list[str] = []
        nested_types: list[str] = []
        fields_index: dict[str, dict[str, Any]] = {}

        for usr_field in sorted(schema.fields, key=lambda f: f.name):
            field_entry = _build_field_entry(usr_field)
            fields_index[usr_field.name] = field_entry

            # Track enum references.
            referenced_enum = _extract_enum_ref(usr_field)
            if referenced_enum and referenced_enum not in enums_referenced:
                enums_referenced.append(referenced_enum)
                if referenced_enum in enum_used_by:
                    enum_used_by[referenced_enum].add(schema.name)

            # Track nested type references.
            referenced_nested = _extract_nested_ref(usr_field)
            if referenced_nested and referenced_nested not in nested_types:
                nested_types.append(referenced_nested)

        # Build variant names (sorted for determinism).
        variant_names = sorted(
            f"{schema.name}{''.join(part.capitalize() for part in v.split('_'))}"
            for v in schema.variants
        )

        types_index[schema.name] = {
            "domain": domain,
            "kind": "struct",
            "description": schema.description or "",
            "fields": fields_index,
            "enums_referenced": sorted(enums_referenced),
            "nested_types": sorted(nested_types),
            "variants": variant_names,
        }

    # Build enums index.
    for enum_name in sorted(all_enums):
        values = all_enums[enum_name]
        enums_index[enum_name] = {
            "values": [
                {"name": str(name), "value": _serialize_value(val)}
                for name, val in values
            ],
            "used_by": sorted(enum_used_by.get(enum_name, set())),
        }

    return {
        "version": REGISTRY_INDEX_VERSION,
        "generated_at": datetime.datetime.now(tz=datetime.UTC).isoformat(),
        "schema_gen_version": __version__,
        "types": types_index,
        "enums": enums_index,
    }


def _detect_domain(schema: USRSchema, config: Config) -> str | None:
    """Derive domain from schema metadata or return None.

    If the schema's metadata contains a ``source_file`` key, the domain
    is derived from the relative path between ``config.input_dir`` and
    the source file's parent directory.  For example, if ``input_dir``
    is ``schemas/`` and ``source_file`` is ``schemas/execution/order.py``,
    the domain is ``"execution"``.

    Returns None when no domain can be determined (flat layout).
    """
    source_file = schema.metadata.get("source_file")
    if not source_file:
        return None

    from pathlib import Path

    source_path = Path(source_file)
    try:
        input_dir = Path(config.input_dir).resolve()
        relative = source_path.resolve().relative_to(input_dir)
    except ValueError:
        return None

    # If the file is directly under input_dir (no subdirectory), no domain.
    parts = relative.parent.parts
    if not parts:
        return None

    return "/".join(parts)


def _render_field_type(usr_field: USRField) -> str:
    """Render a human-readable type string for a USR field."""
    if usr_field.type == FieldType.ENUM:
        return usr_field.enum_name or "enum"
    if usr_field.type == FieldType.NESTED_SCHEMA:
        return usr_field.nested_schema or "object"
    if usr_field.type in (FieldType.LIST, FieldType.SET, FieldType.FROZENSET):
        container = usr_field.type.value
        if usr_field.inner_type:
            inner = _render_field_type(usr_field.inner_type)
            return f"{container}[{inner}]"
        return container
    if usr_field.type == FieldType.OPTIONAL:
        if usr_field.inner_type:
            inner = _render_field_type(usr_field.inner_type)
            return f"optional[{inner}]"
        return "optional"
    if usr_field.type == FieldType.DICT:
        if usr_field.inner_type:
            inner = _render_field_type(usr_field.inner_type)
            return f"dict[string, {inner}]"
        return "dict"
    if usr_field.type == FieldType.UNION:
        if usr_field.union_types:
            parts = [_render_field_type(ut) for ut in usr_field.union_types]
            return f"union[{', '.join(parts)}]"
        return "union"
    if usr_field.type == FieldType.LITERAL:
        if usr_field.literal_values:
            return f"literal[{', '.join(repr(v) for v in usr_field.literal_values)}]"
        return "literal"
    return usr_field.type.value


def _build_field_entry(usr_field: USRField) -> dict[str, Any]:
    """Build a registry field entry dict from a USRField."""
    return {
        "type": _render_field_type(usr_field),
        "required": not usr_field.optional,
        "description": usr_field.description or "",
    }


def _extract_enum_ref(usr_field: USRField) -> str | None:
    """Extract enum name referenced by a field, if any."""
    if usr_field.type == FieldType.ENUM and usr_field.enum_name:
        return usr_field.enum_name
    if usr_field.inner_type:
        return _extract_enum_ref(usr_field.inner_type)
    for ut in usr_field.union_types:
        ref = _extract_enum_ref(ut)
        if ref:
            return ref
    return None


def _extract_nested_ref(usr_field: USRField) -> str | None:
    """Extract nested schema name referenced by a field, if any."""
    if usr_field.type == FieldType.NESTED_SCHEMA and usr_field.nested_schema:
        return usr_field.nested_schema
    if usr_field.inner_type:
        return _extract_nested_ref(usr_field.inner_type)
    for ut in usr_field.union_types:
        ref = _extract_nested_ref(ut)
        if ref:
            return ref
    return None


def _serialize_value(val: Any) -> Any:
    """Ensure a value is JSON-serializable."""
    if isinstance(val, (str, int, float, bool, type(None))):
        return val
    return str(val)
