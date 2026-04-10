"""Generator to create human-readable Markdown documentation from USR schemas."""

from enum import Enum
from pathlib import Path
from typing import Any

from ..core.config import Config
from ..core.usr import FieldType, USREnum, USRField, USRSchema
from .base import BaseGenerator

_DEFAULT_TITLE = "Schema Reference"


class DocsGenerator(BaseGenerator):
    """Generates Markdown documentation from USR schemas."""

    def __init__(self, config: Config | None = None) -> None:
        super().__init__(config=config)
        self._docs_cfg: dict[str, Any] = (
            getattr(config, "docs", None) or {} if config is not None else {}
        )

    @property
    def file_extension(self) -> str:
        return ".md"

    @property
    def generates_index_file(self) -> bool:
        return True

    index_filename: str = "index.md"

    def get_schema_filename(self, schema: USRSchema) -> str:
        return f"{schema.name.lower()}.md"

    def generate_model(self, schema: USRSchema, variant: str | None = None) -> str:
        return self.generate_file(schema)

    def generate_file(self, schema: USRSchema) -> str:
        lines: list[str] = []

        # Title + description
        lines.append(f"# {schema.name}")
        lines.append("")
        if schema.description:
            lines.append(f"> {schema.description}")
            lines.append("")

        # Fields table
        if schema.fields:
            lines.append("## Fields")
            lines.append("")
            lines.append("| Field | Type | Required | Default | Description |")
            lines.append("|-------|------|----------|---------|-------------|")
            for field in schema.fields:
                type_str = _render_type(field)
                required = "yes" if _is_required(field) else "no"
                default = _render_default(field)
                desc = field.description or ""
                lines.append(
                    f"| {field.name} | {type_str} | {required} | {default} | {desc} |"
                )
            lines.append("")

        # Enums section
        if schema.enums:
            lines.append("## Enums")
            lines.append("")
            for enum_def in schema.enums:
                lines.append(f"### {enum_def.name}")
                lines.append("")
                lines.append("| Name | Value |")
                lines.append("|------|-------|")
                for member_name, member_value in enum_def.values:
                    lines.append(f"| {member_name} | {member_value} |")
                lines.append("")

        # Variants section
        if schema.variants:
            lines.append("## Variants")
            lines.append("")
            for variant_name, variant_fields in schema.variants.items():
                parts = variant_name.split("_")
                variant_title = "".join(w.capitalize() for w in parts)
                lines.append(f"### {schema.name}{variant_title}")
                lines.append("")
                lines.append(f"Fields: {', '.join(variant_fields)}")
                lines.append("")

        # Cross-references
        nested_refs = _collect_nested_refs(schema)
        if nested_refs:
            lines.append("## Related Types")
            lines.append("")
            for ref_name in sorted(nested_refs):
                lines.append(f"- [{ref_name}]({ref_name.lower()}.md)")
            lines.append("")

        return "\n".join(lines)

    def generate_index(self, schemas: list[USRSchema], output_dir: Path) -> str | None:
        title = self._docs_cfg.get("title", _DEFAULT_TITLE)
        lines: list[str] = []

        lines.append(f"# {title}")
        lines.append("")

        # Schemas table
        if schemas:
            lines.append("## Schemas")
            lines.append("")
            lines.append("| Type | Description | Fields |")
            lines.append("|------|-------------|--------|")
            for schema in sorted(schemas, key=lambda s: s.name):
                link = f"[{schema.name}]({schema.name.lower()}.md)"
                desc = schema.description or ""
                lines.append(f"| {link} | {desc} | {len(schema.fields)} |")
            lines.append("")

        # Enums table (de-duplicated across schemas)
        all_enums: dict[str, tuple[USREnum, list[str]]] = {}
        for schema in schemas:
            for enum_def in schema.enums:
                if enum_def.name not in all_enums:
                    all_enums[enum_def.name] = (enum_def, [])
                all_enums[enum_def.name][1].append(schema.name)

        if all_enums:
            lines.append("## Enums")
            lines.append("")
            lines.append("| Enum | Values | Used By |")
            lines.append("|------|--------|---------|")
            for enum_name in sorted(all_enums):
                enum_def, used_by = all_enums[enum_name]
                values = ", ".join(str(v) for _, v in enum_def.values)
                if len(values) > 60:
                    values = values[:57] + "..."
                used_by_str = ", ".join(sorted(used_by))
                lines.append(f"| {enum_name} | {values} | {used_by_str} |")
            lines.append("")

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_TYPE_NAMES: dict[FieldType, str] = {
    FieldType.STRING: "string",
    FieldType.INTEGER: "integer",
    FieldType.FLOAT: "float",
    FieldType.BOOLEAN: "boolean",
    FieldType.DATETIME: "datetime",
    FieldType.DATE: "date",
    FieldType.TIME: "time",
    FieldType.UUID: "uuid",
    FieldType.DECIMAL: "decimal",
    FieldType.JSON: "json",
    FieldType.BYTES: "bytes",
}


def _render_type(field: USRField) -> str:
    """Render a human-readable type string for a field."""
    if field.type == FieldType.ENUM:
        return field.enum_name or "enum"
    if field.type == FieldType.NESTED_SCHEMA:
        name = field.nested_schema or "object"
        return f"[{name}]({name.lower()}.md)"
    if field.type == FieldType.LIST:
        inner = _render_type(field.inner_type) if field.inner_type else "any"
        return f"list[{inner}]"
    if field.type in (FieldType.SET, FieldType.FROZENSET):
        inner = _render_type(field.inner_type) if field.inner_type else "any"
        return f"set[{inner}]"
    if field.type == FieldType.DICT:
        if field.inner_type:
            val = _render_type(field.inner_type)
            return f"dict[string, {val}]"
        return "dict[string, any]"
    if field.type == FieldType.UNION:
        if field.union_types:
            parts = [_render_type(ut) for ut in field.union_types]
            return " | ".join(parts)
        return "union"
    if field.type == FieldType.OPTIONAL:
        inner = _render_type(field.inner_type) if field.inner_type else "any"
        return f"{inner} | null"
    if field.type == FieldType.LITERAL:
        if field.literal_values:
            return "literal[" + ", ".join(repr(v) for v in field.literal_values) + "]"
        return "literal"
    if field.type == FieldType.TUPLE:
        if field.union_types:
            parts = [_render_type(ut) for ut in field.union_types]
            return f"tuple[{', '.join(parts)}]"
        return "tuple"
    return _TYPE_NAMES.get(field.type, str(field.type.value).lower())


def _is_required(field: USRField) -> bool:
    """Return True if the field is required (no default, not optional)."""
    return (
        not field.optional and field.default is None and field.default_factory is None
    )


def _render_default(field: USRField) -> str:
    """Render the default value for display."""
    if field.default_factory is not None:
        name = getattr(field.default_factory, "__name__", repr(field.default_factory))
        return f"{name}()"
    if field.default is None and field.optional:
        return "None"
    if field.default is None:
        return "---"
    if isinstance(field.default, Enum):
        return f"{field.default.__class__.__name__}.{field.default.name}"
    if isinstance(field.default, str):
        return f'"{field.default}"'
    return str(field.default)


def _collect_nested_refs(schema: USRSchema) -> set[str]:
    """Collect names of nested schema types referenced by this schema."""
    refs: set[str] = set()
    for field in schema.fields:
        _collect_refs_from_field(field, refs)
    return refs - {schema.name}  # Exclude self-references


def _collect_refs_from_field(field: USRField, refs: set[str]) -> None:
    if field.type == FieldType.NESTED_SCHEMA and field.nested_schema:
        refs.add(field.nested_schema)
    if field.inner_type:
        _collect_refs_from_field(field.inner_type, refs)
    if field.union_types:
        for ut in field.union_types:
            _collect_refs_from_field(ut, refs)
