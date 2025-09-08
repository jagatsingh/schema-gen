"""Generator to create Python dataclasses from USR schemas"""

from typing import List, Dict, Any, Optional
from jinja2 import Template
from datetime import datetime
from ..core.usr import USRSchema, USRField, FieldType


class DataclassesGenerator:
    """Generates Python dataclasses from USR schemas"""
    
    def __init__(self):
        self.template = Template(self._get_template())
    
    def generate_model(self, schema: USRSchema, variant: Optional[str] = None) -> str:
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
        
        # Generate field definitions
        field_definitions = []
        imports = set(['dataclasses'])
        
        for field in fields:
            field_def, field_imports = self._generate_field_definition(field)
            field_definitions.append(field_def)
            imports.update(field_imports)
        
        return self.template.render(
            class_name=class_name,
            schema_name=schema.name,
            variant_name=variant,
            description=schema.description,
            imports=sorted(imports),
            fields=field_definitions,
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")
        )
    
    def generate_file(self, schema: USRSchema) -> str:
        """Generate a complete file with all dataclass variants
        
        Args:
            schema: USR schema to generate from
            
        Returns:
            Complete file content with all dataclasses
        """
        all_imports = set(['dataclasses'])
        all_dataclasses = []
        
        # Generate base dataclass
        base_fields = schema.fields
        base_field_defs = []
        
        for field in base_fields:
            field_def, field_imports = self._generate_field_definition(field)
            base_field_defs.append(field_def)
            all_imports.update(field_imports)
        
        base_dataclass = self._generate_single_dataclass(
            schema.name, schema.description, base_field_defs, is_base_class=True
        )
        all_dataclasses.append(base_dataclass)
        
        # Generate variants
        for variant_name in schema.variants.keys():
            variant_fields = schema.get_variant_fields(variant_name)
            variant_field_defs = []
            
            for field in variant_fields:
                field_def, field_imports = self._generate_field_definition(field)
                variant_field_defs.append(field_def)
                all_imports.update(field_imports)
            
            variant_class_name = self._variant_to_class_name(schema.name, variant_name)
            variant_dataclass = self._generate_single_dataclass(
                variant_class_name, schema.description, variant_field_defs,
                is_base_class=False
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
            if isinstance(field.default, str):
                field_def = f'    {field.name}: {type_annotation} = "{field.default}"'
            else:
                default_value = str(field.default).lower() if isinstance(field.default, bool) else field.default
                field_def = f'    {field.name}: {type_annotation} = {default_value}'
        elif field.optional:
            field_def = f'    {field.name}: {type_annotation} = None'
        elif field.default_factory is not None:
            imports.add('dataclasses.field')
            field_def = f'    {field.name}: {type_annotation} = field(default_factory={field.default_factory.__name__})'
        else:
            field_def = f'    {field.name}: {type_annotation}'
        
        # Add description as comment
        if field.description:
            field_def += f'  # {field.description}'
        
        return field_def, imports
    
    def _get_python_type(self, field: USRField, imports: set) -> str:
        """Get the Python type annotation for a field"""
        
        if field.type == FieldType.STRING:
            return 'str'
        
        elif field.type == FieldType.INTEGER:
            return 'int'
        
        elif field.type == FieldType.FLOAT:
            return 'float'
        
        elif field.type == FieldType.BOOLEAN:
            return 'bool'
        
        elif field.type == FieldType.DATETIME:
            imports.add('datetime')
            return 'datetime.datetime'
        
        elif field.type == FieldType.DATE:
            imports.add('datetime') 
            return 'datetime.date'
        
        elif field.type == FieldType.UUID:
            imports.add('uuid')
            return 'uuid.UUID'
        
        elif field.type == FieldType.DECIMAL:
            imports.add('decimal')
            return 'decimal.Decimal'
        
        elif field.type == FieldType.LIST:
            imports.add('typing')
            if field.inner_type:
                inner_type = self._get_python_type(field.inner_type, imports)
                return f'list[{inner_type}]'
            else:
                return 'list[Any]'
        
        elif field.type == FieldType.DICT:
            imports.add('typing')
            return 'dict[str, Any]'
        
        elif field.type == FieldType.UNION:
            imports.add('typing')
            if field.union_types:
                union_types = [self._get_python_type(ut, imports) for ut in field.union_types]
                return f'Union[{", ".join(union_types)}]'
            else:
                return 'Any'
        
        elif field.type == FieldType.LITERAL:
            imports.add('typing')
            if field.literal_values:
                values = [f'"{v}"' if isinstance(v, str) else str(v) for v in field.literal_values]
                return f'Literal[{", ".join(values)}]'
            else:
                return 'str'
        
        elif field.type == FieldType.NESTED_SCHEMA:
            # For nested schemas, use forward reference
            return f'"{field.nested_schema}"'
        
        else:
            imports.add('typing')
            return 'Any'
        
        # Handle optional wrapper
        if field.optional and not field.type == FieldType.UNION:
            imports.add('typing')
            base_type = self._get_python_type(field, imports) if field.optional else type_annotation
            return f'Optional[{base_type}]'
        
        return type_annotation
    
    def _variant_to_class_name(self, schema_name: str, variant_name: str) -> str:
        """Convert variant name to PascalCase class name"""
        parts = variant_name.split('_')
        variant_pascal = ''.join(word.capitalize() for word in parts)
        return f"{schema_name}{variant_pascal}"
    
    def _generate_single_dataclass(self, class_name: str, description: str, 
                                  field_defs: List[str], is_base_class: bool = False) -> str:
        """Generate a single dataclass definition"""
        lines = []
        
        lines.append('@dataclass')
        lines.append(f'class {class_name}:')
        
        if description:
            lines.append(f'    """')
            lines.append(f'    {description}')
            lines.append(f'    """')
        
        # Add fields
        for field_def in field_defs:
            lines.append(field_def)
        
        if not field_defs:
            lines.append('    pass')
        
        return '\n'.join(lines)
    
    def _generate_complete_file(self, schema_name: str, imports: set, dataclasses: List[str]) -> str:
        """Generate complete file with header, imports, and all dataclasses"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")
        
        lines = [
            '"""',
            'AUTO-GENERATED FILE - DO NOT EDIT MANUALLY',
            f'Generated from: {schema_name}',
            f'Generated at: {timestamp}',
            'Generator: schema-gen Dataclasses generator',
            '',
            'To regenerate this file, run:',
            '    schema-gen generate --target dataclasses',
            '',
            'Changes to this file will be overwritten.',
            '"""',
            ''
        ]
        
        # Add imports
        lines.append("from dataclasses import dataclass")
        if 'dataclasses.field' in imports:
            lines.append("from dataclasses import field")
        
        # Add typing imports
        typing_imports = []
        other_imports = []
        
        for imp in sorted(imports):
            if imp.startswith('datetime'):
                other_imports.append(f"import datetime")
            elif imp.startswith('uuid'):
                other_imports.append("import uuid") 
            elif imp.startswith('decimal'):
                other_imports.append("from decimal import Decimal")
            elif imp == 'typing':
                typing_imports.extend(['Optional', 'List', 'Dict', 'Any', 'Union', 'Literal'])
        
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