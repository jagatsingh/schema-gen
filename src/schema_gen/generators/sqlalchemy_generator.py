"""Generator to create SQLAlchemy 2.0 models from USR schemas"""

from datetime import datetime
from enum import Enum
from pathlib import Path

from jinja2 import Template

from ..core.usr import FieldType, USRField, USRSchema
from .base import BaseGenerator


class SqlAlchemyGenerator(BaseGenerator):
    """Generates SQLAlchemy 2.0 models from USR schemas"""

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
        """Generate __init__.py content for the sqlalchemy package."""
        lines = ['"""Generated SQLAlchemy models"""\n']
        lines.append("from ._base import Base")

        for schema in schemas:
            lines.append(f"from .{schema.name.lower()}_models import {schema.name}")

        lines.append("\n__all__ = [")
        lines.append('    "Base",')
        for schema in schemas:
            lines.append(f'    "{schema.name}",')
        lines.append("]")

        return "\n".join(lines) + "\n"

    def get_extra_files(
        self, schemas: list[USRSchema], output_dir: Path
    ) -> dict[str, str]:
        """Generate _base.py for shared SQLAlchemy Base."""
        base_content = (
            '"""Shared SQLAlchemy Base - AUTO-GENERATED"""\n\n'
            "from sqlalchemy.orm import DeclarativeBase\n\n\n"
            "class Base(DeclarativeBase):\n"
            "    pass\n"
        )
        return {"_base.py": base_content}

    def generate_model(self, schema: USRSchema, variant: str | None = None) -> str:
        """Generate a SQLAlchemy model for a schema variant

        Args:
            schema: USR schema to generate from
            variant: Specific variant to generate, or None for full schema

        Returns:
            Generated SQLAlchemy model code
        """
        fields = schema.get_variant_fields(variant) if variant else schema.fields

        # Determine the model name and table name
        model_name = schema.name
        table_name = self._to_snake_case(schema.name)

        if variant:
            model_name = self._variant_to_class_name(schema.name, variant)
            table_name = f"{table_name}_{variant}"

        # Generate column definitions
        column_definitions = []
        imports = {"sqlalchemy"}
        relationships = []

        for field in fields:
            if field.relationship:
                rel_def, rel_imports = self._generate_relationship_definition(field)
                relationships.append(rel_def)
                imports.update(rel_imports)
            else:
                col_def, col_imports = self._generate_column_definition(field)
                column_definitions.append(col_def)
                imports.update(col_imports)

        return self.template.render(
            model_name=model_name,
            table_name=table_name,
            schema_name=schema.name,
            variant_name=variant,
            description=schema.description,
            imports=sorted(imports),
            columns=column_definitions,
            relationships=relationships,
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC"),
        )

    def generate_file(self, schema: USRSchema) -> str:
        """Generate a complete file with SQLAlchemy model

        Args:
            schema: USR schema to generate from

        Returns:
            Complete file content with model
        """
        all_imports = {"sqlalchemy", "sqlalchemy.orm"}
        all_columns = []
        all_relationships = []

        # Generate base model
        base_fields = schema.fields
        for field in base_fields:
            if field.relationship:
                rel_def, rel_imports = self._generate_relationship_definition(field)
                all_relationships.append(rel_def)
                all_imports.update(rel_imports)
            else:
                col_def, col_imports = self._generate_column_definition(field)
                all_columns.append(col_def)
                all_imports.update(col_imports)

        # Generate complete file
        return self._generate_complete_file(
            schema.name, all_imports, all_columns, all_relationships, schema.description
        )

    def _generate_column_definition(self, field: USRField) -> tuple[str, set[str]]:
        """Generate a single column definition using SQLAlchemy 2.0 Mapped[] style

        Returns:
            Tuple of (column_definition_code, required_imports)
        """
        imports = set()

        # Get SQLAlchemy type info: (sql_type_str_or_None, python_type)
        sql_type, python_type = self._get_sqlalchemy_type(field, imports)

        # Determine Mapped type annotation
        if field.optional and not field.primary_key:
            mapped_type = f"Mapped[{python_type} | None]"
        else:
            mapped_type = f"Mapped[{python_type}]"

        # Build mapped_column parameters
        column_params = []

        # SQL type goes first if explicitly needed
        if sql_type:
            column_params.append(sql_type)

        # Primary key
        if field.primary_key:
            column_params.append("primary_key=True")

        # (nullable is implicit from Mapped[T] vs Mapped[T | None], so we skip it)

        # Unique constraint
        if field.unique:
            column_params.append("unique=True")

        # Index
        if field.index:
            column_params.append("index=True")

        # Auto increment
        if field.auto_increment:
            column_params.append("autoincrement=True")

        # Default value
        if field.default is not None:
            if isinstance(field.default, Enum):
                column_params.append(f'default="{field.default.value}"')
            elif isinstance(field.default, str):
                column_params.append(f'default="{field.default}"')
            else:
                column_params.append(f"default={field.default}")

        # Foreign key
        if field.foreign_key:
            column_params.append(f'ForeignKey("{field.foreign_key}")')
            imports.add("sqlalchemy.ForeignKey")

        # Server defaults for timestamps
        if field.auto_now_add:
            imports.add("sqlalchemy.func")
            column_params.append("server_default=func.now()")

        if field.auto_now:
            imports.add("sqlalchemy.func")
            column_params.append("server_default=func.now()")
            column_params.append("onupdate=func.now()")

        # Build column definition
        params_str = ", ".join(column_params) if column_params else ""
        column_def = f"    {field.name}: {mapped_type} = mapped_column({params_str})"

        return column_def, imports

    def _generate_relationship_definition(
        self, field: USRField
    ) -> tuple[str, set[str]]:
        """Generate a relationship definition

        Returns:
            Tuple of (relationship_definition_code, required_imports)
        """
        imports = {"sqlalchemy.orm.relationship"}

        rel_params = []
        rel_params.append(f'"{field.nested_schema}"')

        if field.back_populates:
            rel_params.append(f'back_populates="{field.back_populates}"')

        if field.cascade:
            rel_params.append(f'cascade="{field.cascade}"')

        relationship_def = f"    {field.name} = relationship({', '.join(rel_params)})"

        return relationship_def, imports

    def _get_sqlalchemy_type(
        self, field: USRField, imports: set
    ) -> tuple[str | None, str]:
        """Get the SQLAlchemy column type and Python type for a field.

        Returns:
            Tuple of (sql_type_str_or_None, mapped_python_type).
            When sql_type is None, mapped_column() infers the SQL type from Mapped[T].
        """

        if field.type == FieldType.STRING:
            if field.max_length:
                return f"String({field.max_length})", "str"
            else:
                imports.add("sqlalchemy.Text")
                return "Text", "str"

        elif field.type == FieldType.INTEGER:
            return None, "int"

        elif field.type == FieldType.FLOAT:
            return None, "float"

        elif field.type == FieldType.BOOLEAN:
            return None, "bool"

        elif field.type == FieldType.DATETIME:
            imports.add("datetime.datetime")
            return None, "datetime"

        elif field.type == FieldType.DATE:
            imports.add("datetime.date")
            return None, "date"

        elif field.type == FieldType.UUID:
            imports.add("sqlalchemy.Uuid")
            return "Uuid", "uuid.UUID"

        elif field.type == FieldType.DECIMAL:
            imports.add("sqlalchemy.Numeric")
            precision = field.target_config.get("sqlalchemy", {}).get("precision", 10)
            scale = field.target_config.get("sqlalchemy", {}).get("scale", 2)
            return f"Numeric({precision}, {scale})", "Decimal"

        elif (
            field.type in (FieldType.SET, FieldType.FROZENSET)
            or field.type == FieldType.TUPLE
            or field.type == FieldType.JSON
        ):
            imports.add("sqlalchemy.JSON")
            return "JSON", "Any"

        elif field.type == FieldType.ENUM:
            # Use String with length based on max enum value length
            if field.enum_values:
                max_len = max(len(str(v)) for v in field.enum_values)
                return f"String({max(max_len, 20)})", "str"
            return "String(50)", "str"

        else:
            # Default to String for unknown types
            return "String(255)", "str"

    def _variant_to_class_name(self, schema_name: str, variant_name: str) -> str:
        """Convert variant name to PascalCase class name"""
        parts = variant_name.split("_")
        variant_pascal = "".join(word.capitalize() for word in parts)
        return f"{schema_name}{variant_pascal}"

    def _to_snake_case(self, name: str) -> str:
        """Convert PascalCase to snake_case"""
        import re

        s1 = re.sub("(.)([A-Z][a-z]+)", r"\1_\2", name)
        return re.sub("([a-z0-9])([A-Z])", r"\1_\2", s1).lower()

    def _generate_complete_file(
        self,
        schema_name: str,
        imports: set,
        columns: list[str],
        relationships: list[str],
        description: str,
    ) -> str:
        """Generate complete file with header, imports, and model"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")

        lines = [
            '"""',
            "AUTO-GENERATED FILE - DO NOT EDIT MANUALLY",
            f"Generated from: {schema_name}",
            f"Generated at: {timestamp}",
            "Generator: schema-gen SQLAlchemy generator",
            "",
            "To regenerate this file, run:",
            "    schema-gen generate --target sqlalchemy",
            "",
            "Changes to this file will be overwritten.",
            '"""',
            "",
        ]

        # Collect stdlib imports needed
        needs_datetime = False
        needs_date = False
        needs_uuid = False
        needs_decimal = False
        needs_any = False

        for imp in imports:
            if imp == "datetime.datetime":
                needs_datetime = True
            elif imp == "datetime.date":
                needs_date = True

        # Also scan columns for type hints
        for col in columns:
            if "uuid.UUID" in col:
                needs_uuid = True
            if "Decimal" in col:
                needs_decimal = True
            if "Any" in col:
                needs_any = True
            if "datetime" in col and "Mapped[datetime" in col:
                needs_datetime = True
            if "Mapped[date" in col and "Mapped[datetime" not in col:
                needs_date = True

        # Add stdlib imports
        datetime_parts = []
        if needs_datetime:
            datetime_parts.append("datetime")
        if needs_date:
            datetime_parts.append("date")
        if datetime_parts:
            lines.append(f"from datetime import {', '.join(sorted(datetime_parts))}")
        if needs_decimal:
            lines.append("from decimal import Decimal")
        if needs_uuid:
            lines.append("import uuid")
        if needs_any:
            lines.append("from typing import Any")

        # Build needed SQLAlchemy type imports (only types explicitly used in mapped_column)
        sa_type_imports = set()
        for col in columns:
            for type_name in [
                "String",
                "Text",
                "Numeric",
                "JSON",
                "Uuid",
            ]:
                if (
                    type_name + "(" in col
                    or type_name + ")" in col
                    or type_name + "," in col
                ):
                    sa_type_imports.add(type_name)
                # Also catch bare type_name at the end of mapped_column params
                if f"mapped_column({type_name})" in col:
                    sa_type_imports.add(type_name)

        # Add func if used
        needs_func = any("func.now()" in col for col in columns)
        if needs_func:
            sa_type_imports.add("func")

        # Add ForeignKey if used
        for imp in sorted(imports):
            if imp == "sqlalchemy.ForeignKey":
                sa_type_imports.add("ForeignKey")

        if sa_type_imports:
            lines.append(f"from sqlalchemy import {', '.join(sorted(sa_type_imports))}")
        lines.append("from sqlalchemy.orm import Mapped, mapped_column, relationship")

        lines.append("from ._base import Base")
        lines.append("")
        lines.append("")

        # Add model class
        table_name = self._to_snake_case(schema_name)
        lines.append(f"class {schema_name}(Base):")
        lines.append(f'    __tablename__ = "{table_name}"')

        if description:
            lines.append('    """')
            lines.append(f"    {description}")
            lines.append('    """')

        lines.append("")

        # Add columns
        for column in columns:
            lines.append(column)

        # Add relationships
        if relationships:
            lines.append("")
            lines.append("    # Relationships")
            for relationship in relationships:
                lines.append(relationship)

        return "\n".join(lines)

    def _get_template(self) -> str:
        """Get the Jinja2 template for SQLAlchemy 2.0 models"""
        return '''"""
AUTO-GENERATED FILE - DO NOT EDIT MANUALLY
Generated from: {{ schema_name }}{% if variant_name %} ({{ variant_name }} variant){% endif %}
Generated at: {{ timestamp }}
Generator: schema-gen SQLAlchemy generator

To regenerate this file, run:
    schema-gen generate --target sqlalchemy

Changes to this file will be overwritten.
"""

from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
{% for imp in imports %}
{%- if imp.startswith('sqlalchemy.') and imp != 'sqlalchemy' and imp != 'sqlalchemy.orm' %}
from sqlalchemy import {{ imp.replace('sqlalchemy.', '') }}
{%- endif %}
{%- endfor %}


class Base(DeclarativeBase):
    pass


class {{ model_name }}(Base):
    __tablename__ = "{{ table_name }}"
{%- if description %}
    """
    {{ description }}
    """
{%- endif %}

{% for column_def in columns %}
{{ column_def }}
{%- endfor %}
{%- if relationships %}

    # Relationships
{%- for rel_def in relationships %}
{{ rel_def }}
{%- endfor %}
{%- endif %}'''
