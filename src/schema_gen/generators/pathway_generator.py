"""Generator to create Pathway schemas from USR schemas"""

from typing import List, Dict, Any, Optional
from jinja2 import Template
from datetime import datetime
from ..core.usr import USRSchema, USRField, FieldType


class PathwayGenerator:
    """Generates Pathway table schemas from USR schemas"""
    
    def __init__(self):
        self.template = Template(self._get_template())
    
    def generate_model(self, schema: USRSchema, variant: Optional[str] = None) -> str:
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
        imports = set(['pathway'])
        
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
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")
        )
    
    def generate_file(self, schema: USRSchema) -> str:
        """Generate a complete file with Pathway table schema
        
        Args:
            schema: USR schema to generate from
            
        Returns:
            Complete file content with table schema
        """
        all_imports = set(['pathway'])
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
        for variant_name in schema.variants.keys():
            variant_fields = schema.get_variant_fields(variant_name)
            variant_columns = []
            
            for field in variant_fields:
                col_def, col_imports = self._generate_column_definition(field)
                variant_columns.append(col_def)
                all_imports.update(col_imports)
            
            variant_class_name = self._variant_to_class_name(schema.name, variant_name)
            variant_schema = self._generate_single_schema(
                variant_class_name, schema.description, variant_columns,
                is_base_schema=False
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
        
        # Build column definition
        col_def = f'    {field.name}: pw.ColumnExpression[{pathway_type}]'
        
        # Add description as comment
        if field.description:
            col_def += f'  # {field.description}'
        
        return col_def, imports
    
    def _get_pathway_type(self, field: USRField, imports: set) -> str:
        """Get the Pathway type for a field"""
        
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
            if field.inner_type:
                inner_type = self._get_pathway_type(field.inner_type, imports)
                return f'list[{inner_type}]'
            else:
                return 'list'
        
        elif field.type == FieldType.DICT:
            return 'dict'
        
        elif field.type == FieldType.UNION:
            if field.union_types:
                imports.add('typing')
                union_types = [self._get_pathway_type(ut, imports) for ut in field.union_types]
                return f'typing.Union[{", ".join(union_types)}]'
            else:
                return 'typing.Any'
        
        elif field.type == FieldType.NESTED_SCHEMA:
            # For nested schemas, use the schema name
            return field.nested_schema
        
        else:
            imports.add('typing')
            return 'typing.Any'
    
    def _variant_to_class_name(self, schema_name: str, variant_name: str) -> str:
        """Convert variant name to PascalCase class name"""
        parts = variant_name.split('_')
        variant_pascal = ''.join(word.capitalize() for word in parts)
        return f"{schema_name}{variant_pascal}"
    
    def _generate_single_schema(self, class_name: str, description: str, 
                               columns: List[str], is_base_schema: bool = False) -> str:
        """Generate a single Pathway table schema definition"""
        lines = []
        
        lines.append(f'class {class_name}(pw.Table):')
        
        if description:
            lines.append(f'    """')
            lines.append(f'    {description}')
            lines.append(f'    """')
        
        # Add columns
        for column in columns:
            lines.append(column)
        
        if not columns:
            lines.append('    pass')
        
        return '\n'.join(lines)
    
    def _generate_complete_file(self, schema_name: str, imports: set, schemas: List[str]) -> str:
        """Generate complete file with header, imports, and all schemas"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")
        
        lines = [
            '"""',
            'AUTO-GENERATED FILE - DO NOT EDIT MANUALLY',
            f'Generated from: {schema_name}',
            f'Generated at: {timestamp}',
            'Generator: schema-gen Pathway generator',
            '',
            'To regenerate this file, run:',
            '    schema-gen generate --target pathway',
            '',
            'Changes to this file will be overwritten.',
            '"""',
            ''
        ]
        
        # Add imports
        lines.append("import pathway as pw")
        
        # Add additional imports
        additional_imports = []
        for imp in sorted(imports):
            if imp not in ['pathway']:
                if imp in ['datetime', 'uuid', 'decimal', 'typing']:
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