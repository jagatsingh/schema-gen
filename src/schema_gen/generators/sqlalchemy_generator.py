"""Generator to create SQLAlchemy models from USR schemas"""

from datetime import datetime

from jinja2 import Template

from ..core.usr import FieldType, USRField, USRSchema


class SqlAlchemyGenerator:
    """Generates SQLAlchemy models from USR schemas"""

    def __init__(self):
        self.template = Template(self._get_template())

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
        """Generate a single column definition

        Returns:
            Tuple of (column_definition_code, required_imports)
        """
        imports = set()

        # Get SQLAlchemy column type
        column_type = self._get_sqlalchemy_type(field, imports)

        # Build column parameters
        column_params = []

        # Primary key
        if field.primary_key:
            column_params.append("primary_key=True")

        # Nullable
        if not field.optional and not field.primary_key:
            column_params.append("nullable=False")

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
            if isinstance(field.default, str):
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

        # Build column definition
        params_str = ", ".join(column_params) if column_params else ""
        column_def = f"    {field.name} = Column({column_type}"
        if params_str:
            column_def += f", {params_str}"
        column_def += ")"

        imports.add("sqlalchemy.Column")

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

    def _get_sqlalchemy_type(self, field: USRField, imports: set) -> str:
        """Get the SQLAlchemy column type for a field"""

        if field.type == FieldType.STRING:
            if field.max_length:
                return f"String({field.max_length})"
            else:
                imports.add("sqlalchemy.Text")
                return "Text"

        elif field.type == FieldType.INTEGER:
            return "Integer"

        elif field.type == FieldType.FLOAT:
            return "Float"

        elif field.type == FieldType.BOOLEAN:
            return "Boolean"

        elif field.type == FieldType.DATETIME:
            imports.add("sqlalchemy.DateTime")
            return "DateTime"

        elif field.type == FieldType.DATE:
            imports.add("sqlalchemy.Date")
            return "Date"

        elif field.type == FieldType.UUID:
            imports.add("sqlalchemy.dialects.postgresql")
            return "UUID"

        elif field.type == FieldType.DECIMAL:
            imports.add("sqlalchemy.Numeric")
            precision = field.target_config.get("sqlalchemy", {}).get("precision", 10)
            scale = field.target_config.get("sqlalchemy", {}).get("scale", 2)
            return f"Numeric({precision}, {scale})"

        elif field.type == FieldType.JSON:
            imports.add("sqlalchemy.JSON")
            return "JSON"

        else:
            # Default to String for unknown types
            return "String(255)"

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

        # Add imports
        lines.append(
            "from sqlalchemy import Column, Integer, String, Boolean, DateTime, Float"
        )
        lines.append("from sqlalchemy.ext.declarative import declarative_base")
        lines.append("from sqlalchemy.orm import relationship")

        # Add additional imports
        additional_imports = []
        for imp in sorted(imports):
            if imp.startswith("sqlalchemy.") and imp not in [
                "sqlalchemy",
                "sqlalchemy.orm",
            ]:
                module = imp.replace("sqlalchemy.", "")
                additional_imports.append(f"from sqlalchemy import {module}")

        for imp_line in additional_imports:
            lines.append(imp_line)

        lines.append("")
        lines.append("Base = declarative_base()")
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
        """Get the Jinja2 template for SQLAlchemy models"""
        return '''"""
AUTO-GENERATED FILE - DO NOT EDIT MANUALLY
Generated from: {{ schema_name }}{% if variant_name %} ({{ variant_name }} variant){% endif %}
Generated at: {{ timestamp }}
Generator: schema-gen SQLAlchemy generator

To regenerate this file, run:
    schema-gen generate --target sqlalchemy

Changes to this file will be overwritten.
"""

from sqlalchemy import Column, Integer, String, Boolean, DateTime, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
{% for imp in imports %}
{%- if imp.startswith('sqlalchemy.') and imp != 'sqlalchemy' and imp != 'sqlalchemy.orm' %}
from sqlalchemy import {{ imp.replace('sqlalchemy.', '') }}
{%- endif %}
{%- endfor %}

Base = declarative_base()


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
