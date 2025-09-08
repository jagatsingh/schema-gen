"""Generator to create Python TypedDict from USR schemas"""

from typing import List, Dict, Any, Optional
from jinja2 import Template
from datetime import datetime
from ..core.usr import USRSchema, USRField, FieldType


class TypedDictGenerator:
    """Generates Python TypedDict definitions from USR schemas"""
    
    def __init__(self):
        self.template = Template(self._get_template())
    
    def generate_model(self, schema: USRSchema, variant: Optional[str] = None) -> str:
        """Generate a TypedDict for a schema variant
        
        Args:
            schema: USR schema to generate from
            variant: Specific variant to generate, or None for full schema
            
        Returns:
            Generated TypedDict code
        """
        fields = schema.get_variant_fields(variant) if variant else schema.fields
        
        # Determine the class name
        class_name = schema.name
        if variant:
            class_name = self._variant_to_class_name(schema.name, variant)
        
        # Generate field definitions
        field_definitions = []
        imports = set(['typing_extensions'])
        
        # Determine if we need total=False (for optional fields)
        has_optional_fields = any(field.optional or field.default is not None for field in fields)
        
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
            has_optional_fields=has_optional_fields,
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")
        )
    
    def generate_file(self, schema: USRSchema) -> str:
        """Generate a complete file with all TypedDict variants
        
        Args:
            schema: USR schema to generate from
            
        Returns:
            Complete file content with all TypedDicts
        """
        all_imports = set(['typing_extensions'])
        all_typeddicts = []
        
        # Generate base TypedDict
        base_fields = schema.fields
        base_field_defs = []
        base_has_optional = any(field.optional or field.default is not None for field in base_fields)
        
        for field in base_fields:
            field_def, field_imports = self._generate_field_definition(field)
            base_field_defs.append(field_def)
            all_imports.update(field_imports)
        
        base_typeddict = self._generate_single_typeddict(
            schema.name, schema.description, base_field_defs, 
            base_has_optional, is_base_class=True
        )
        all_typeddicts.append(base_typeddict)
        
        # Generate variants
        for variant_name in schema.variants.keys():
            variant_fields = schema.get_variant_fields(variant_name)
            variant_field_defs = []
            variant_has_optional = any(field.optional or field.default is not None for field in variant_fields)
            
            for field in variant_fields:
                field_def, field_imports = self._generate_field_definition(field)
                variant_field_defs.append(field_def)
                all_imports.update(field_imports)
            
            variant_class_name = self._variant_to_class_name(schema.name, variant_name)
            variant_typeddict = self._generate_single_typeddict(
                variant_class_name, schema.description, variant_field_defs,
                variant_has_optional, is_base_class=False
            )
            all_typeddicts.append(variant_typeddict)
        
        # Generate complete file
        return self._generate_complete_file(schema.name, all_imports, all_typeddicts)
    
    def _generate_field_definition(self, field: USRField) -> tuple[str, set[str]]:
        """Generate a single field definition
        
        Returns:
            Tuple of (field_definition_code, required_imports)
        """
        imports = set()
        
        # Get Python type annotation
        type_annotation = self._get_python_type(field, imports)
        
        # Build field definition
        field_def = f'    {field.name}: {type_annotation}'
        
        # Add description as comment
        if field.description:
            field_def += f'  # {field.description}'
        
        return field_def, imports
    
    def _get_python_type(self, field: USRField, imports: set) -> str:
        """Get the Python type annotation for a field"""
        
        base_type = ""
        
        if field.type == FieldType.STRING:
            base_type = 'str'
        
        elif field.type == FieldType.INTEGER:
            base_type = 'int'
        
        elif field.type == FieldType.FLOAT:
            base_type = 'float'
        
        elif field.type == FieldType.BOOLEAN:
            base_type = 'bool'
        
        elif field.type == FieldType.DATETIME:
            imports.add('datetime')
            base_type = 'datetime.datetime'
        
        elif field.type == FieldType.DATE:
            imports.add('datetime') 
            base_type = 'datetime.date'
        
        elif field.type == FieldType.UUID:
            imports.add('uuid')
            base_type = 'uuid.UUID'
        
        elif field.type == FieldType.DECIMAL:
            imports.add('decimal')
            base_type = 'decimal.Decimal'
        
        elif field.type == FieldType.LIST:
            imports.add('typing')
            if field.inner_type:
                inner_type = self._get_python_type(field.inner_type, imports)
                base_type = f'List[{inner_type}]'
            else:
                base_type = 'List[Any]'
        
        elif field.type == FieldType.DICT:
            imports.add('typing')
            base_type = 'Dict[str, Any]'
        
        elif field.type == FieldType.UNION:
            imports.add('typing')
            if field.union_types:
                union_types = [self._get_python_type(ut, imports) for ut in field.union_types]
                base_type = f'Union[{", ".join(union_types)}]'
            else:
                base_type = 'Any'
        
        elif field.type == FieldType.LITERAL:
            imports.add('typing')
            if field.literal_values:
                values = [f'"{v}"' if isinstance(v, str) else str(v) for v in field.literal_values]
                base_type = f'Literal[{", ".join(values)}]'
            else:
                base_type = 'str'
        
        elif field.type == FieldType.NESTED_SCHEMA:
            # For nested schemas, use forward reference
            base_type = f'"{field.nested_schema}"'
        
        else:
            imports.add('typing')
            base_type = 'Any'
        
        # Handle optional fields
        if field.optional:
            imports.add('typing')
            return f'NotRequired[{base_type}]'
        
        return base_type
    
    def _variant_to_class_name(self, schema_name: str, variant_name: str) -> str:
        """Convert variant name to PascalCase class name"""
        parts = variant_name.split('_')
        variant_pascal = ''.join(word.capitalize() for word in parts)
        return f"{schema_name}{variant_pascal}"
    
    def _generate_single_typeddict(self, class_name: str, description: str, 
                                  field_defs: List[str], has_optional_fields: bool,
                                  is_base_class: bool = False) -> str:
        """Generate a single TypedDict definition"""
        lines = []
        
        # TypedDict with total parameter for optional fields
        if has_optional_fields:
            lines.append(f'class {class_name}(TypedDict, total=False):')
        else:
            lines.append(f'class {class_name}(TypedDict):')
        
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
    
    def _generate_complete_file(self, schema_name: str, imports: set, typeddicts: List[str]) -> str:
        """Generate complete file with header, imports, and all TypedDicts"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")
        
        lines = [
            '"""',
            'AUTO-GENERATED FILE - DO NOT EDIT MANUALLY',
            f'Generated from: {schema_name}',
            f'Generated at: {timestamp}',
            'Generator: schema-gen TypedDict generator',
            '',
            'To regenerate this file, run:',
            '    schema-gen generate --target typeddict',
            '',
            'Changes to this file will be overwritten.',
            '"""',
            ''
        ]
        
        # Add imports
        lines.append("from typing_extensions import TypedDict, NotRequired")
        
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
                typing_imports.extend(['List', 'Dict', 'Any', 'Union', 'Literal'])
        
        # Add typing import if needed
        if typing_imports:
            lines.append(f"from typing import {', '.join(sorted(set(typing_imports)))}")
        
        # Add other imports
        for imp_line in set(other_imports):
            lines.append(imp_line)
        
        lines.append("")
        lines.append("")
        
        # Add TypedDicts
        for i, typeddict in enumerate(typeddicts):
            if i > 0:
                lines.append("")
                lines.append("")
            lines.append(typeddict)
        
        return "\n".join(lines)
    
    def _get_template(self) -> str:
        """Get the Jinja2 template for TypedDicts"""
        return '''"""
AUTO-GENERATED FILE - DO NOT EDIT MANUALLY
Generated from: {{ schema_name }}{% if variant_name %} ({{ variant_name }} variant){% endif %}
Generated at: {{ timestamp }}
Generator: schema-gen TypedDict generator

To regenerate this file, run:
    schema-gen generate --target typeddict

Changes to this file will be overwritten.
"""

from typing_extensions import TypedDict, NotRequired
{% set typing_imports = [] %}
{% for imp in imports %}
{%- if imp.startswith('datetime') %}
import datetime
{%- elif imp.startswith('uuid') %}
import uuid
{%- elif imp.startswith('decimal') %}
from decimal import Decimal
{%- elif imp == 'typing' %}
{% set _ = typing_imports.extend(['List', 'Dict', 'Any', 'Union', 'Literal']) %}
{%- endif %}
{%- endfor %}
{% if typing_imports %}from typing import {{ typing_imports|unique|sort|join(', ') }}{% endif %}


class {{ class_name }}(TypedDict{% if has_optional_fields %}, total=False{% endif %}):
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