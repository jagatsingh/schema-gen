"""Generator to create Pydantic models from USR schemas"""

from datetime import datetime
from typing import Any

from jinja2 import Template

from ..core.usr import FieldType, USRField, USRSchema


class PydanticGenerator:
    """Generates Pydantic models from USR schemas"""

    def __init__(self):
        self.template = Template(self._get_template())

    def generate_model(self, schema: USRSchema, variant: str | None = None) -> str:
        """Generate a Pydantic model for a schema variant

        Args:
            schema: USR schema to generate from
            variant: Specific variant to generate, or None for full schema

        Returns:
            Generated Pydantic model code
        """
        fields = schema.get_variant_fields(variant) if variant else schema.fields

        # Determine the model name
        model_name = schema.name
        if variant:
            model_name = self._variant_to_class_name(schema.name, variant)

        # Generate field definitions
        field_definitions = []
        imports = {"pydantic", "typing"}

        for field in fields:
            field_def, field_imports = self._generate_field_definition(field)
            field_definitions.append(field_def)
            imports.update(field_imports)

        return self.template.render(
            model_name=model_name,
            schema_name=schema.name,
            variant_name=variant,
            description=schema.description,
            imports=sorted(imports),
            fields=field_definitions,
            has_config=self._needs_config(fields),
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC"),
        )

    def generate_all_variants(self, schema: USRSchema) -> dict[str, str]:
        """Generate all variants for a schema

        Args:
            schema: USR schema to generate variants for

        Returns:
            Dictionary mapping variant names to generated code
        """
        variants = {}

        # Generate base model (all fields)
        variants["base"] = self.generate_model(schema)

        # Generate specific variants
        for variant_name in schema.variants:
            variants[variant_name] = self.generate_model(schema, variant_name)

        return variants

    def generate_file(self, schema: USRSchema) -> str:
        """Generate a complete file with all variants for a schema

        Args:
            schema: USR schema to generate from

        Returns:
            Complete file content with all models
        """
        # Collect all imports needed
        all_imports = {"pydantic"}
        all_fields = []
        all_models = []

        # Generate base model
        base_fields = schema.fields
        for field in base_fields:
            field_def, field_imports = self._generate_field_definition(field)
            all_fields.append(field_def)
            all_imports.update(field_imports)

        # Extract pydantic-specific custom code
        pydantic_custom_code = schema.custom_code.get("pydantic", {})

        base_model = self._generate_single_model(
            schema.name,
            schema.description,
            all_fields,
            self._needs_config(base_fields),
            is_base_model=True,
            custom_code=pydantic_custom_code,
        )
        all_models.append(base_model)

        # Generate variants (without custom code)
        for variant_name in schema.variants:
            variant_fields = schema.get_variant_fields(variant_name)
            variant_field_defs = []

            for field in variant_fields:
                field_def, field_imports = self._generate_field_definition(field)
                variant_field_defs.append(field_def)
                all_imports.update(field_imports)

            variant_model_name = self._variant_to_class_name(schema.name, variant_name)
            variant_model = self._generate_single_model(
                variant_model_name,
                schema.description,
                variant_field_defs,
                self._needs_config(variant_fields),
                is_base_model=False,  # Variants don't get custom code
            )
            all_models.append(variant_model)

        # Generate complete file
        return self._generate_complete_file(
            schema.name, all_imports, all_models, pydantic_custom_code
        )

    def _variant_to_class_name(self, schema_name: str, variant_name: str) -> str:
        """Convert variant name to PascalCase class name"""
        # Convert snake_case to PascalCase
        parts = variant_name.split("_")
        variant_pascal = "".join(word.capitalize() for word in parts)
        return f"{schema_name}{variant_pascal}"

    def _generate_field_definition(self, field: USRField) -> tuple[str, set[str]]:
        """Generate a single field definition

        Returns:
            Tuple of (field_definition_code, required_imports)
        """
        imports = set()

        # Generate type annotation
        type_annotation = self._get_pydantic_type(field, imports)

        # Generate Field() definition
        field_params = []

        # Default value
        if field.default is not None:
            if isinstance(field.default, str):
                field_params.append(f'default="{field.default}"')
            else:
                field_params.append(f"default={field.default}")
        elif field.optional and not field_params:
            field_params.append("default=None")
        elif not field.optional and not field_params:
            field_params.append("...")  # Required field marker

        # Validation parameters
        if field.min_length is not None:
            field_params.append(f"min_length={field.min_length}")
        if field.max_length is not None:
            field_params.append(f"max_length={field.max_length}")
        if field.min_value is not None:
            field_params.append(f"ge={field.min_value}")  # greater or equal
        if field.max_value is not None:
            field_params.append(f"le={field.max_value}")  # less or equal
        if field.regex_pattern:
            field_params.append(f'regex=r"{field.regex_pattern}"')

        # Description
        if field.description:
            field_params.append(f'description="{field.description}"')

        # Pydantic-specific configurations
        pydantic_config = field.target_config.get("pydantic", {})
        for key, value in pydantic_config.items():
            if isinstance(value, str):
                field_params.append(f'{key}="{value}"')
            else:
                field_params.append(f"{key}={value}")

        # Build field definition
        if field_params:
            imports.add("pydantic.Field")
            field_def = f"    {field.name}: {type_annotation} = Field({', '.join(field_params)})"
        else:
            field_def = f"    {field.name}: {type_annotation}"

        return field_def, imports

    def _get_pydantic_type(self, field: USRField, imports: set) -> str:
        """Get the Pydantic type annotation for a field"""

        # For optional fields, get the base type from inner_type first
        if field.optional and field.inner_type:
            inner_type = self._get_pydantic_type(field.inner_type, imports)
            imports.add("typing")
            return f"Optional[{inner_type}]"

        base_type = ""

        if field.type == FieldType.STRING:
            if field.format_type == "email":
                imports.add("pydantic.EmailStr")
                base_type = "EmailStr"
            else:
                base_type = "str"

        elif field.type == FieldType.INTEGER:
            base_type = "int"

        elif field.type == FieldType.FLOAT:
            base_type = "float"

        elif field.type == FieldType.BOOLEAN:
            base_type = "bool"

        elif field.type == FieldType.DATETIME:
            imports.add("datetime.datetime")
            base_type = "datetime"

        elif field.type == FieldType.DATE:
            imports.add("datetime.date")
            base_type = "date"

        elif field.type == FieldType.UUID:
            imports.add("uuid.UUID")
            base_type = "UUID"

        elif field.type == FieldType.DECIMAL:
            imports.add("decimal.Decimal")
            base_type = "Decimal"

        elif field.type == FieldType.LIST:
            imports.add("typing")
            if field.inner_type:
                inner_type = self._get_pydantic_type(field.inner_type, imports)
                base_type = f"List[{inner_type}]"
            else:
                base_type = "List[Any]"

        elif field.type == FieldType.DICT:
            imports.add("typing")
            base_type = "Dict[str, Any]"

        elif field.type == FieldType.UNION:
            imports.add("typing")
            if field.union_types:
                union_types = [
                    self._get_pydantic_type(ut, imports) for ut in field.union_types
                ]
                base_type = f"Union[{', '.join(union_types)}]"
            else:
                base_type = "Any"

        elif field.type == FieldType.LITERAL:
            if field.literal_values:
                values = [
                    f'"{v}"' if isinstance(v, str) else str(v)
                    for v in field.literal_values
                ]
                imports.add("typing.Literal")
                base_type = f"Literal[{', '.join(values)}]"
            else:
                base_type = "str"

        elif field.type == FieldType.NESTED_SCHEMA:
            # For nested schemas, use forward reference
            base_type = f'"{field.nested_schema}"'

        else:
            imports.add("typing")
            base_type = "Any"

        return base_type

    def _needs_config(self, fields: list[USRField]) -> bool:
        """Check if the model needs a Config class"""
        # Check if any field has database relationships
        return any(field.relationship is not None for field in fields)

    def _generate_single_model(
        self,
        model_name: str,
        description: str,
        field_defs: list[str],
        has_config: bool,
        is_base_model: bool = False,
        custom_code: dict[str, Any] = None,
    ) -> str:
        """Generate a single model class definition"""
        lines = [f"class {model_name}(BaseModel):"]

        if description:
            lines.append(f'    """{description}"""')

        # Add fields
        for field_def in field_defs:
            lines.append(field_def)

        # Add custom code only to base model
        if is_base_model and custom_code:
            if custom_code.get("raw_code"):
                lines.append("")
                lines.append("    # Custom validators")
                # Indent the custom code properly - ensure all lines have proper indentation
                raw_code_lines = custom_code["raw_code"].strip().split("\n")
                for code_line in raw_code_lines:
                    if code_line.strip():  # Skip empty lines
                        # If line already starts with proper indentation, use as is
                        # Otherwise, add 4 spaces for class method indentation
                        if code_line.startswith("    "):
                            lines.append(code_line)
                        else:
                            lines.append("    " + code_line)
                    else:
                        lines.append("")

            if custom_code.get("methods"):
                lines.append("")
                lines.append("    # Custom methods")
                # Indent the custom methods properly - ensure all lines have proper indentation
                methods_lines = custom_code["methods"].strip().split("\n")
                for method_line in methods_lines:
                    if method_line.strip():  # Skip empty lines
                        # If line already starts with proper indentation, use as is
                        # Otherwise, add 4 spaces for class method indentation
                        if method_line.startswith("    "):
                            lines.append(method_line)
                        else:
                            lines.append("    " + method_line)
                    else:
                        lines.append("")

        # Add config if needed
        if has_config:
            lines.append("")
            lines.append("    class Config:")
            lines.append("        from_attributes = True")

        return "\n".join(lines)

    def _generate_complete_file(
        self,
        schema_name: str,
        imports: set,
        models: list[str],
        custom_code: dict[str, Any] = None,
    ) -> str:
        """Generate complete file with header, imports, and all models"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")
        custom_code = custom_code or {}

        lines = [
            '"""',
            "AUTO-GENERATED FILE - DO NOT EDIT MANUALLY",
            f"Generated from: {schema_name}",
            f"Generated at: {timestamp}",
            "Generator: schema-gen Pydantic generator",
            "",
            "To regenerate this file, run:",
            "    schema-gen generate --target pydantic",
            "",
            "Changes to this file will be overwritten.",
            '"""',
            "",
        ]

        # Add custom imports from Meta.imports
        custom_imports = custom_code.get("imports", [])

        # Add imports
        pydantic_imports = ["BaseModel"]
        if "pydantic.Field" in imports:
            pydantic_imports.append("Field")
        lines.append(f"from pydantic import {', '.join(pydantic_imports)}")

        if "pydantic.EmailStr" in imports:
            lines.append("from pydantic import EmailStr")

        # Add typing imports
        typing_imports = []
        other_imports = []

        for imp in sorted(imports):
            if imp.startswith("datetime"):
                other_imports.append(f"from datetime import {imp.split('.')[-1]}")
            elif imp.startswith("uuid"):
                other_imports.append("import uuid")
            elif imp.startswith("decimal"):
                other_imports.append("from decimal import Decimal")
            elif imp == "typing":
                typing_imports.extend(["Optional", "List", "Dict", "Any", "Union"])
            elif imp == "typing.Literal":
                typing_imports.append("Literal")

        # Add typing import if needed
        if typing_imports:
            lines.append(f"from typing import {', '.join(sorted(set(typing_imports)))}")

        # Add other imports
        for imp_line in other_imports:
            lines.append(imp_line)

        # Add custom imports
        for custom_import in custom_imports:
            lines.append(custom_import)

        lines.append("")
        lines.append("")

        # Add models
        for i, model in enumerate(models):
            if i > 0:
                lines.append("")
                lines.append("")
            lines.append(model)

        return "\n".join(lines)

    def _get_template(self) -> str:
        """Get the Jinja2 template for Pydantic models"""
        return '''"""
AUTO-GENERATED FILE - DO NOT EDIT MANUALLY
Generated from: {{ schema_name }}{% if variant_name %} ({{ variant_name }} variant){% endif %}
Generated at: {{ timestamp }}
Generator: schema-gen Pydantic generator

To regenerate this file, run:
    schema-gen generate --target pydantic

Changes to this file will be overwritten.
"""

from pydantic import BaseModel{% if 'pydantic.Field' in imports %}, Field{% endif %}
{% if 'pydantic.EmailStr' in imports %}from pydantic import EmailStr{% endif %}
{% for imp in imports %}
{%- if imp.startswith('datetime') %}
from datetime import {{ imp.split('.')[-1] }}
{%- elif imp.startswith('uuid') %}
import uuid
{%- elif imp.startswith('decimal') %}
from decimal import Decimal
{%- elif imp == 'typing' %}
from typing import Optional, List, Dict, Any, Union
{%- elif imp == 'typing.Literal' %}
from typing import Literal
{%- endif %}
{%- endfor %}


class {{ model_name }}(BaseModel):
{%- if description %}
    """{{ description }}"""
{%- endif %}
{% for field_def in fields %}
{{ field_def }}
{%- endfor %}
{%- if has_config %}

    class Config:
        from_attributes = True
{%- endif %}'''
