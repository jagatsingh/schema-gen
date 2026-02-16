"""Generator to create Python dataclasses from USR schemas"""

from datetime import datetime
from pathlib import Path

from jinja2 import Template

from ..core.usr import FieldType, USRField, USRSchema
from .base import BaseGenerator


class DataclassesGenerator(BaseGenerator):
    """Generates Python dataclasses from USR schemas"""

    def __init__(self):
        self.template = Template(self._get_template())

    @property
    def file_extension(self) -> str:
        return ".py"

    @property
    def generates_index_file(self) -> bool:
        return True

    def get_schema_filename(self, schema: USRSchema) -> str:
        return f"{schema.name.lower()}_models.py"

    def generate_index(self, schemas: list[USRSchema], output_dir: Path) -> str | None:
        """Generate __init__.py content for the dataclasses package."""
        lines = ['"""Generated Dataclasses models"""\n']

        for schema in schemas:
            base_class = schema.name
            variant_classes = [
                self._variant_to_class_name(schema.name, v) for v in schema.variants
            ]
            all_classes = [base_class] + variant_classes
            lines.append(
                f"from .{schema.name.lower()}_models import {', '.join(all_classes)}"
            )

        lines.append("\n__all__ = [")
        for schema in schemas:
            base_class = schema.name
            variant_classes = [
                self._variant_to_class_name(schema.name, v) for v in schema.variants
            ]
            all_classes = [f'"{c}"' for c in [base_class] + variant_classes]
            lines.append(f"    {', '.join(all_classes)},")
        lines.append("]")

        return "\n".join(lines) + "\n"

    def generate_model(self, schema: USRSchema, variant: str | None = None) -> str:
        """Generate a dataclass for a schema variant

        Args:
            schema: USR schema to generate from
            variant: Specific variant to generate, or None for full schema

        Returns:
            Generated dataclass code
        """
        fields = schema.get_variant_fields(variant) if variant else schema.fields

        # Determine the class name
        class_name = schema.name
        if variant:
            class_name = self._variant_to_class_name(schema.name, variant)

        # Generate field definitions with proper ordering
        # Required fields must come before optional/default fields in dataclasses
        required_fields = []
        optional_fields = []
        imports = {"dataclasses"}

        for field in fields:
            field_def, field_imports = self._generate_field_definition(field)
            imports.update(field_imports)

            # Check if field has default value, is optional, has default_factory, is a datetime field, or auto_now/auto_now_add
            if (
                field.default is not None
                or field.optional
                or field.default_factory is not None
                or field.type == FieldType.DATETIME
                or (hasattr(field, "auto_now_add") and field.auto_now_add)
                or (hasattr(field, "auto_now") and field.auto_now)
            ):
                optional_fields.append(field_def)
            else:
                required_fields.append(field_def)

        # Combine required fields first, then optional fields
        field_definitions = required_fields + optional_fields

        return self.template.render(
            class_name=class_name,
            schema_name=schema.name,
            variant_name=variant,
            description=schema.description,
            imports=sorted(imports),
            fields=field_definitions,
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC"),
        )

    def generate_file(self, schema: USRSchema) -> str:
        """Generate a complete file with all dataclass variants

        Args:
            schema: USR schema to generate from

        Returns:
            Complete file content with all dataclasses
        """
        all_imports = {"dataclasses"}
        all_dataclasses = []

        # Generate base dataclass with proper field ordering
        base_fields = schema.fields
        base_required_fields = []
        base_optional_fields = []

        for field in base_fields:
            field_def, field_imports = self._generate_field_definition(field)
            all_imports.update(field_imports)

            # Check if field has default value, is optional, has default_factory, is a datetime field, or auto_now/auto_now_add
            if (
                field.default is not None
                or field.optional
                or field.default_factory is not None
                or field.type == FieldType.DATETIME
                or (hasattr(field, "auto_now_add") and field.auto_now_add)
                or (hasattr(field, "auto_now") and field.auto_now)
            ):
                base_optional_fields.append(field_def)
            else:
                base_required_fields.append(field_def)

        # Combine required fields first, then optional fields
        base_field_defs = base_required_fields + base_optional_fields

        base_dataclass = self._generate_single_dataclass(
            schema.name, schema.description, base_field_defs, is_base_class=True
        )
        all_dataclasses.append(base_dataclass)

        # Generate variants with proper field ordering
        for variant_name in schema.variants:
            variant_fields = schema.get_variant_fields(variant_name)
            variant_required_fields = []
            variant_optional_fields = []

            for field in variant_fields:
                field_def, field_imports = self._generate_field_definition(field)
                all_imports.update(field_imports)

                # Check if field has default value, is optional, has default_factory, is a datetime field, or auto_now/auto_now_add
                if (
                    field.default is not None
                    or field.optional
                    or field.default_factory is not None
                    or field.type == FieldType.DATETIME
                    or (hasattr(field, "auto_now_add") and field.auto_now_add)
                    or (hasattr(field, "auto_now") and field.auto_now)
                ):
                    variant_optional_fields.append(field_def)
                else:
                    variant_required_fields.append(field_def)

            # Combine required fields first, then optional fields
            variant_field_defs = variant_required_fields + variant_optional_fields

            variant_class_name = self._variant_to_class_name(schema.name, variant_name)
            variant_dataclass = self._generate_single_dataclass(
                variant_class_name,
                schema.description,
                variant_field_defs,
                is_base_class=False,
            )
            all_dataclasses.append(variant_dataclass)

        # Generate complete file
        return self._generate_complete_file(schema.name, all_imports, all_dataclasses)

    def _generate_field_definition(self, field: USRField) -> tuple[str, set[str]]:
        """Generate a single field definition

        Returns:
            Tuple of (field_definition_code, required_imports)
        """
        imports = set()

        # Get Python type annotation
        type_annotation = self._get_python_type(field, imports)

        # Build field definition
        if field.default is not None:
            from enum import Enum as PyEnum

            if isinstance(field.default, PyEnum):
                field_def = (
                    f'    {field.name}: {type_annotation} = "{field.default.value}"'
                )
            elif isinstance(field.default, str):
                field_def = f'    {field.name}: {type_annotation} = "{field.default}"'
            else:
                default_value = (
                    str(field.default)  # Python booleans are already "True"/"False"
                    if isinstance(field.default, bool)
                    else field.default
                )
                field_def = f"    {field.name}: {type_annotation} = {default_value}"
        elif field.optional:
            field_def = f"    {field.name}: {type_annotation} = None"
        elif field.default_factory is not None:
            imports.add("dataclasses.field")
            field_def = f"    {field.name}: {type_annotation} = field(default_factory={field.default_factory.__name__})"
        elif hasattr(field, "auto_now_add") and field.auto_now_add:
            # Handle auto_now_add fields for datetime types
            imports.add("dataclasses.field")
            if field.type == FieldType.DATETIME:
                imports.add("datetime")
                field_def = f"    {field.name}: {type_annotation} = field(default_factory=datetime.datetime.now)"
            elif field.type == FieldType.DATE:
                imports.add("datetime")
                field_def = f"    {field.name}: {type_annotation} = field(default_factory=datetime.date.today)"
            else:
                # Fallback for other types with auto_now_add
                field_def = f"    {field.name}: {type_annotation}"
        elif hasattr(field, "auto_now") and field.auto_now:
            # Handle auto_now fields similarly
            imports.add("dataclasses.field")
            if field.type == FieldType.DATETIME:
                imports.add("datetime")
                field_def = f"    {field.name}: {type_annotation} = field(default_factory=datetime.datetime.now)"
            elif field.type == FieldType.DATE:
                imports.add("datetime")
                field_def = f"    {field.name}: {type_annotation} = field(default_factory=datetime.date.today)"
            else:
                # Fallback for other types with auto_now
                field_def = f"    {field.name}: {type_annotation}"
        elif field.type == FieldType.DATETIME:
            # Special handling for datetime fields without defaults - give them a default factory
            imports.add("dataclasses.field")
            imports.add("datetime")
            field_def = f"    {field.name}: {type_annotation} = field(default_factory=datetime.datetime.now)"
        else:
            field_def = f"    {field.name}: {type_annotation}"

        # Add description as comment
        if field.description:
            field_def += f"  # {field.description}"

        return field_def, imports

    def _get_python_type(self, field: USRField, imports: set) -> str:
        """Get the Python type annotation for a field"""

        if field.type == FieldType.STRING:
            return "str"

        elif field.type == FieldType.INTEGER:
            return "int"

        elif field.type == FieldType.FLOAT:
            return "float"

        elif field.type == FieldType.BOOLEAN:
            return "bool"

        elif field.type == FieldType.DATETIME:
            imports.add("datetime")
            return "datetime.datetime"

        elif field.type == FieldType.DATE:
            imports.add("datetime")
            return "datetime.date"

        elif field.type == FieldType.UUID:
            imports.add("uuid")
            return "uuid.UUID"

        elif field.type == FieldType.DECIMAL:
            imports.add("decimal")
            return "decimal.Decimal"

        elif field.type == FieldType.LIST:
            imports.add("typing")
            if field.inner_type:
                inner_type = self._get_python_type(field.inner_type, imports)
                return f"list[{inner_type}]"
            else:
                return "list[Any]"

        elif field.type == FieldType.SET:
            imports.add("typing")
            if field.inner_type:
                inner_type = self._get_python_type(field.inner_type, imports)
                return f"set[{inner_type}]"
            else:
                return "set[Any]"

        elif field.type == FieldType.FROZENSET:
            imports.add("typing")
            if field.inner_type:
                inner_type = self._get_python_type(field.inner_type, imports)
                return f"frozenset[{inner_type}]"
            else:
                return "frozenset[Any]"

        elif field.type == FieldType.TUPLE:
            if field.union_types:
                inner_types = [
                    self._get_python_type(ut, imports) for ut in field.union_types
                ]
                return f"tuple[{', '.join(inner_types)}]"
            else:
                return "tuple[()]"

        elif field.type == FieldType.DICT:
            imports.add("typing")
            return "dict[str, Any]"

        elif field.type == FieldType.UNION:
            imports.add("typing")
            if field.union_types:
                union_types = [
                    self._get_python_type(ut, imports) for ut in field.union_types
                ]
                return f"Union[{', '.join(union_types)}]"
            else:
                return "Any"

        elif field.type == FieldType.LITERAL:
            imports.add("typing")
            if field.literal_values:
                values = [
                    f'"{v}"' if isinstance(v, str) else str(v)
                    for v in field.literal_values
                ]
                return f"Literal[{', '.join(values)}]"
            else:
                return "str"

        elif field.type == FieldType.ENUM:
            type_annotation = "str"  # Enum values as strings

        elif field.type == FieldType.NESTED_SCHEMA:
            # For nested schemas, use forward reference
            type_annotation = f'"{field.nested_schema}"'

        else:
            imports.add("typing")
            type_annotation = "Any"

        # Handle optional wrapper
        if field.optional and field.type != FieldType.UNION:
            imports.add("typing")
            return f"Optional[{type_annotation}]"

        return type_annotation

    def _variant_to_class_name(self, schema_name: str, variant_name: str) -> str:
        """Convert variant name to PascalCase class name"""
        parts = variant_name.split("_")
        variant_pascal = "".join(word.capitalize() for word in parts)
        return f"{schema_name}{variant_pascal}"

    def _generate_single_dataclass(
        self,
        class_name: str,
        description: str,
        field_defs: list[str],
        is_base_class: bool = False,
    ) -> str:
        """Generate a single dataclass definition"""
        lines = []

        lines.append("@dataclass")
        lines.append(f"class {class_name}:")

        if description:
            lines.append('    """')
            lines.append(f"    {description}")
            lines.append('    """')

        # Add fields
        for field_def in field_defs:
            lines.append(field_def)

        if not field_defs:
            lines.append("    pass")

        return "\n".join(lines)

    def _generate_complete_file(
        self, schema_name: str, imports: set, dataclasses: list[str]
    ) -> str:
        """Generate complete file with header, imports, and all dataclasses"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")

        lines = [
            '"""',
            "AUTO-GENERATED FILE - DO NOT EDIT MANUALLY",
            f"Generated from: {schema_name}",
            f"Generated at: {timestamp}",
            "Generator: schema-gen Dataclasses generator",
            "",
            "To regenerate this file, run:",
            "    schema-gen generate --target dataclasses",
            "",
            "Changes to this file will be overwritten.",
            '"""',
            "",
        ]

        # Add imports
        lines.append("from dataclasses import dataclass")
        if "dataclasses.field" in imports:
            lines.append("from dataclasses import field")

        # Add typing imports
        typing_imports = []
        other_imports = []

        for imp in sorted(imports):
            if imp.startswith("datetime"):
                other_imports.append("import datetime")
            elif imp.startswith("uuid"):
                other_imports.append("import uuid")
            elif imp.startswith("decimal"):
                other_imports.append("from decimal import Decimal")
            elif imp == "typing":
                typing_imports.extend(
                    ["Optional", "List", "Dict", "Any", "Union", "Literal"]
                )

        # Add typing import if needed
        if typing_imports:
            lines.append(f"from typing import {', '.join(sorted(set(typing_imports)))}")

        # Add other imports
        for imp_line in set(other_imports):
            lines.append(imp_line)

        lines.append("")
        lines.append("")

        # Add dataclasses
        for i, dataclass in enumerate(dataclasses):
            if i > 0:
                lines.append("")
                lines.append("")
            lines.append(dataclass)

        return "\n".join(lines)

    def _get_template(self) -> str:
        """Get the Jinja2 template for dataclasses"""
        return '''"""
AUTO-GENERATED FILE - DO NOT EDIT MANUALLY
Generated from: {{ schema_name }}{% if variant_name %} ({{ variant_name }} variant){% endif %}
Generated at: {{ timestamp }}
Generator: schema-gen Dataclasses generator

To regenerate this file, run:
    schema-gen generate --target dataclasses

Changes to this file will be overwritten.
"""

from dataclasses import dataclass
{% if 'dataclasses.field' in imports %}from dataclasses import field{% endif %}
{% set typing_imports = [] %}
{% for imp in imports %}
{%- if imp.startswith('datetime') %}
import datetime
{%- elif imp.startswith('uuid') %}
import uuid
{%- elif imp.startswith('decimal') %}
from decimal import Decimal
{%- elif imp == 'typing' %}
{% set _ = typing_imports.extend(['Optional', 'List', 'Dict', 'Any', 'Union', 'Literal']) %}
{%- endif %}
{%- endfor %}
{% if typing_imports %}from typing import {{ typing_imports|unique|sort|join(', ') }}{% endif %}


@dataclass
class {{ class_name }}:
{%- if description %}
    """
    {{ description }}
    """
{%- endif %}
{% for field_def in fields %}
{{ field_def }}
{%- endfor %}
{%- if not fields %}
    pass
{%- endif %}'''
