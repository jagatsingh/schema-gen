"""Generator to create Pathway schemas from USR schemas"""

from datetime import datetime
from pathlib import Path

from jinja2 import Template

from ..core.usr import FieldType, USRField, USRSchema
from .base import BaseGenerator


class PathwayGenerator(BaseGenerator):
    """Generates Pathway table schemas from USR schemas"""

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
        """Generate __init__.py content for the pathway package."""
        lines = ['"""Generated Pathway models"""\n']

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
        """Generate a Pathway table schema for a schema variant

        Args:
            schema: USR schema to generate from
            variant: Specific variant to generate, or None for full schema

        Returns:
            Generated Pathway table schema code
        """
        fields = schema.get_variant_fields(variant) if variant else schema.fields

        # Determine the class name
        class_name = schema.name
        if variant:
            class_name = self._variant_to_class_name(schema.name, variant)

        # Generate column definitions
        column_definitions = []
        imports = {"pathway"}

        for field in fields:
            col_def, col_imports = self._generate_column_definition(field)
            column_definitions.append(col_def)
            imports.update(col_imports)

        return self.template.render(
            class_name=class_name,
            schema_name=schema.name,
            variant_name=variant,
            description=schema.description,
            imports=sorted(imports),
            columns=column_definitions,
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC"),
        )

    def generate_file(self, schema: USRSchema) -> str:
        """Generate a complete file with Pathway table schema

        Args:
            schema: USR schema to generate from

        Returns:
            Complete file content with table schema
        """
        all_imports = {"pathway"}
        all_columns = []
        all_schemas = []

        # Generate base schema
        base_fields = schema.fields
        for field in base_fields:
            col_def, col_imports = self._generate_column_definition(field)
            all_columns.append(col_def)
            all_imports.update(col_imports)

        # Generate base table schema
        base_schema = self._generate_single_schema(
            schema.name, schema.description, all_columns, is_base_schema=True
        )
        all_schemas.append(base_schema)

        # Generate variants
        for variant_name in schema.variants:
            variant_fields = schema.get_variant_fields(variant_name)
            variant_columns = []

            for field in variant_fields:
                col_def, col_imports = self._generate_column_definition(field)
                variant_columns.append(col_def)
                all_imports.update(col_imports)

            variant_class_name = self._variant_to_class_name(schema.name, variant_name)
            variant_schema = self._generate_single_schema(
                variant_class_name,
                schema.description,
                variant_columns,
                is_base_schema=False,
            )
            all_schemas.append(variant_schema)

        # Generate complete file
        return self._generate_complete_file(schema.name, all_imports, all_schemas)

    def _generate_column_definition(self, field: USRField) -> tuple[str, set[str]]:
        """Generate a single column definition

        Returns:
            Tuple of (column_definition_code, required_imports)
        """
        imports = set()

        # Get Pathway column type
        pathway_type = self._get_pathway_type(field, imports)

        # Build column definition (using non-generic syntax for compatibility)
        col_def = f"    {field.name}: pw.ColumnExpression  # {pathway_type}"

        # Add description as comment
        if field.description:
            col_def += f"  # {field.description}"

        return col_def, imports

    def _get_pathway_type(self, field: USRField, imports: set) -> str:
        """Get the Pathway type for a field"""

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
            if field.inner_type:
                inner_type = self._get_pathway_type(field.inner_type, imports)
                return f"list[{inner_type}]"
            else:
                return "list"

        elif field.type == FieldType.SET:
            if field.inner_type:
                inner_type = self._get_pathway_type(field.inner_type, imports)
                return f"set[{inner_type}]"
            else:
                return "set"

        elif field.type == FieldType.FROZENSET:
            if field.inner_type:
                inner_type = self._get_pathway_type(field.inner_type, imports)
                return f"frozenset[{inner_type}]"
            else:
                return "frozenset"

        elif field.type == FieldType.TUPLE:
            return "tuple"

        elif field.type == FieldType.DICT:
            return "dict"

        elif field.type == FieldType.UNION:
            if field.union_types:
                imports.add("typing")
                union_types = [
                    self._get_pathway_type(ut, imports) for ut in field.union_types
                ]
                return f"typing.Union[{', '.join(union_types)}]"
            else:
                return "typing.Any"

        elif field.type == FieldType.ENUM:
            return "str"  # Enum values as strings

        elif field.type == FieldType.NESTED_SCHEMA:
            # For nested schemas, use the schema name
            return field.nested_schema

        else:
            imports.add("typing")
            return "typing.Any"

    def _variant_to_class_name(self, schema_name: str, variant_name: str) -> str:
        """Convert variant name to PascalCase class name"""
        parts = variant_name.split("_")
        variant_pascal = "".join(word.capitalize() for word in parts)
        return f"{schema_name}{variant_pascal}"

    def _generate_single_schema(
        self,
        class_name: str,
        description: str,
        columns: list[str],
        is_base_schema: bool = False,
    ) -> str:
        """Generate a single Pathway table schema definition"""
        lines = []

        lines.append(f"class {class_name}(pw.Table):")

        if description:
            lines.append('    """')
            lines.append(f"    {description}")
            lines.append('    """')

        # Add columns
        for column in columns:
            lines.append(column)

        if not columns:
            lines.append("    pass")

        return "\n".join(lines)

    def _generate_complete_file(
        self, schema_name: str, imports: set, schemas: list[str]
    ) -> str:
        """Generate complete file with header, imports, and all schemas"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")

        lines = [
            '"""',
            "AUTO-GENERATED FILE - DO NOT EDIT MANUALLY",
            f"Generated from: {schema_name}",
            f"Generated at: {timestamp}",
            "Generator: schema-gen Pathway generator",
            "",
            "To regenerate this file, run:",
            "    schema-gen generate --target pathway",
            "",
            "Changes to this file will be overwritten.",
            '"""',
            "",
        ]

        # Add imports
        lines.append("import pathway as pw")

        # Add additional imports
        additional_imports = []
        for imp in sorted(imports):
            if imp not in ["pathway"]:
                if imp in ["datetime", "uuid", "decimal", "typing"]:
                    additional_imports.append(f"import {imp}")
                else:
                    additional_imports.append(f"from {imp}")

        for imp_line in additional_imports:
            lines.append(imp_line)

        lines.append("")
        lines.append("")

        # Add schemas
        for i, schema in enumerate(schemas):
            if i > 0:
                lines.append("")
                lines.append("")
            lines.append(schema)

        return "\n".join(lines)

    def _get_template(self) -> str:
        """Get the Jinja2 template for Pathway schemas"""
        return '''"""
AUTO-GENERATED FILE - DO NOT EDIT MANUALLY
Generated from: {{ schema_name }}{% if variant_name %} ({{ variant_name }} variant){% endif %}
Generated at: {{ timestamp }}
Generator: schema-gen Pathway generator

To regenerate this file, run:
    schema-gen generate --target pathway

Changes to this file will be overwritten.
"""

import pathway as pw
{% for imp in imports %}
{%- if imp not in ['pathway'] %}
import {{ imp }}
{%- endif %}
{%- endfor %}


class {{ class_name }}(pw.Table):
{%- if description %}
    """
    {{ description }}
    """
{%- endif %}
{% for column_def in columns %}
{{ column_def }}
{%- endfor %}
{%- if not columns %}
    pass
{%- endif %}'''
