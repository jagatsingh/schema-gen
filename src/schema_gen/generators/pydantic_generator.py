"""Generator to create Pydantic models from USR schemas"""

from typing import List, Dict, Any, Optional
from jinja2 import Template
from datetime import datetime
from ..core.usr import USRSchema, USRField, FieldType


class PydanticGenerator:
    """Generates Pydantic models from USR schemas"""
    
    def __init__(self):
        self.template = Template(self._get_template())
    
    def generate_model(self, schema: USRSchema, variant: Optional[str] = None) -> str:
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
        imports = set(['pydantic', 'typing'])
        
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
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")
        )
    
    def generate_all_variants(self, schema: USRSchema) -> Dict[str, str]:
        """Generate all variants for a schema
        
        Args:
            schema: USR schema to generate variants for
            
        Returns:
            Dictionary mapping variant names to generated code
        """
        variants = {}
        
        # Generate base model (all fields)
        variants['base'] = self.generate_model(schema)
        
        # Generate specific variants
        for variant_name in schema.variants.keys():
            variants[variant_name] = self.generate_model(schema, variant_name)
        
        return variants
    
    def _variant_to_class_name(self, schema_name: str, variant_name: str) -> str:
        """Convert variant name to PascalCase class name"""
        # Convert snake_case to PascalCase
        parts = variant_name.split('_')
        variant_pascal = ''.join(word.capitalize() for word in parts)
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
                field_params.append(f'default={field.default}')
        elif field.optional and not field_params:
            field_params.append('default=None')
        elif not field.optional and not field_params:
            field_params.append('...')  # Required field marker
        
        # Validation parameters
        if field.min_length is not None:
            field_params.append(f'min_length={field.min_length}')
        if field.max_length is not None:
            field_params.append(f'max_length={field.max_length}')
        if field.min_value is not None:
            field_params.append(f'ge={field.min_value}')  # greater or equal
        if field.max_value is not None:
            field_params.append(f'le={field.max_value}')  # less or equal
        if field.regex_pattern:
            field_params.append(f'regex=r"{field.regex_pattern}"')
        
        # Description
        if field.description:
            field_params.append(f'description="{field.description}"')
        
        # Pydantic-specific configurations
        pydantic_config = field.target_config.get('pydantic', {})
        for key, value in pydantic_config.items():
            if isinstance(value, str):
                field_params.append(f'{key}="{value}"')
            else:
                field_params.append(f'{key}={value}')
        
        # Build field definition
        if field_params:
            imports.add('pydantic.Field')
            field_def = f'    {field.name}: {type_annotation} = Field({", ".join(field_params)})'
        else:
            field_def = f'    {field.name}: {type_annotation}'
        
        return field_def, imports
    
    def _get_pydantic_type(self, field: USRField, imports: set) -> str:
        """Get the Pydantic type annotation for a field"""
        
        if field.type == FieldType.STRING:
            if field.format_type == 'email':
                imports.add('pydantic.EmailStr')
                return 'EmailStr'
            return 'str'
        
        elif field.type == FieldType.INTEGER:
            return 'int'
        
        elif field.type == FieldType.FLOAT:
            return 'float'
        
        elif field.type == FieldType.BOOLEAN:
            return 'bool'
        
        elif field.type == FieldType.DATETIME:
            imports.add('datetime.datetime')
            return 'datetime'
        
        elif field.type == FieldType.DATE:
            imports.add('datetime.date')
            return 'date'
        
        elif field.type == FieldType.UUID:
            imports.add('uuid.UUID')
            return 'UUID'
        
        elif field.type == FieldType.DECIMAL:
            imports.add('decimal.Decimal')
            return 'Decimal'
        
        elif field.type == FieldType.LIST:
            if field.inner_type:
                inner_type = self._get_pydantic_type(field.inner_type, imports)
                return f'List[{inner_type}]'
            return 'List[Any]'
        
        elif field.type == FieldType.DICT:
            return 'Dict[str, Any]'
        
        elif field.type == FieldType.OPTIONAL:
            if field.inner_type:
                inner_type = self._get_pydantic_type(field.inner_type, imports)
                return f'Optional[{inner_type}]'
            return 'Optional[Any]'
        
        elif field.type == FieldType.UNION:
            if field.union_types:
                union_types = [self._get_pydantic_type(ut, imports) for ut in field.union_types]
                return f'Union[{", ".join(union_types)}]'
            return 'Any'
        
        elif field.type == FieldType.LITERAL:
            if field.literal_values:
                values = [f'"{v}"' if isinstance(v, str) else str(v) for v in field.literal_values]
                imports.add('typing.Literal')
                return f'Literal[{", ".join(values)}]'
            return 'str'
        
        elif field.type == FieldType.NESTED_SCHEMA:
            # For nested schemas, use forward reference
            return f'"{field.nested_schema}"'
        
        else:
            return 'Any'
    
    def _needs_config(self, fields: List[USRField]) -> bool:
        """Check if the model needs a Config class"""
        # Check if any field has database relationships
        return any(field.relationship is not None for field in fields)
    
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
{% endfor %}
{%- if has_config %}

    class Config:
        from_attributes = True
{%- endif %}'''