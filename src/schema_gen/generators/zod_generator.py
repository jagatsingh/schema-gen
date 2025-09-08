"""Generator to create Zod schemas from USR schemas"""

from typing import List, Dict, Any, Optional
from jinja2 import Template
from datetime import datetime
from ..core.usr import USRSchema, USRField, FieldType


class ZodGenerator:
    """Generates Zod schemas (TypeScript/JavaScript) from USR schemas"""
    
    def __init__(self):
        self.template = Template(self._get_template())
    
    def generate_model(self, schema: USRSchema, variant: Optional[str] = None) -> str:
        """Generate a Zod schema for a schema variant
        
        Args:
            schema: USR schema to generate from
            variant: Specific variant to generate, or None for full schema
            
        Returns:
            Generated Zod schema code (TypeScript)
        """
        fields = schema.get_variant_fields(variant) if variant else schema.fields
        
        # Determine the schema name
        schema_name = schema.name
        if variant:
            schema_name = self._variant_to_schema_name(schema.name, variant)
        
        # Generate field definitions
        field_definitions = []
        
        for field in fields:
            field_def = self._generate_field_definition(field)
            field_definitions.append(field_def)
        
        return self.template.render(
            schema_name=schema_name,
            base_schema_name=schema.name,
            variant_name=variant,
            description=schema.description,
            fields=field_definitions,
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
        
        # Generate base schema (all fields)
        variants['base'] = self.generate_model(schema)
        
        # Generate specific variants
        for variant_name in schema.variants.keys():
            variants[variant_name] = self.generate_model(schema, variant_name)
        
        return variants
    
    def generate_file(self, schema: USRSchema) -> str:
        """Generate a complete TypeScript file with all variants for a schema
        
        Args:
            schema: USR schema to generate from
            
        Returns:
            Complete file content with all schemas
        """
        all_schemas = []
        all_types = []
        
        # Generate base schema
        base_fields = schema.fields
        base_field_defs = []
        
        for field in base_fields:
            field_def = self._generate_field_definition(field)
            base_field_defs.append(field_def)
        
        base_schema = self._generate_single_schema(
            schema.name, schema.description, base_field_defs, is_base_schema=True
        )
        all_schemas.append(base_schema)
        
        # Generate base TypeScript type
        base_type = self._generate_typescript_type(schema.name, base_fields)
        all_types.append(base_type)
        
        # Generate variants
        for variant_name in schema.variants.keys():
            variant_fields = schema.get_variant_fields(variant_name)
            variant_field_defs = []
            
            for field in variant_fields:
                field_def = self._generate_field_definition(field)
                variant_field_defs.append(field_def)
            
            variant_schema_name = self._variant_to_schema_name(schema.name, variant_name)
            variant_schema = self._generate_single_schema(
                variant_schema_name, schema.description, variant_field_defs,
                is_base_schema=False
            )
            all_schemas.append(variant_schema)
            
            # Generate variant TypeScript type
            variant_type = self._generate_typescript_type(variant_schema_name, variant_fields)
            all_types.append(variant_type)
        
        # Generate complete file
        return self._generate_complete_file(schema.name, all_schemas, all_types)
    
    def _generate_field_definition(self, field: USRField) -> str:
        """Generate a single field definition for Zod
        
        Returns:
            Field definition code
        """
        # Get base Zod type
        zod_type = self._get_zod_type(field)
        
        # Add validation rules
        validations = []
        
        if field.type == FieldType.STRING:
            if field.min_length is not None:
                validations.append(f'.min({field.min_length})')
            if field.max_length is not None:
                validations.append(f'.max({field.max_length})')
            if field.regex_pattern:
                validations.append(f'.regex(/{field.regex_pattern}/)')
            if field.format_type == 'email':
                validations.append('.email()')
            elif field.format_type == 'url':
                validations.append('.url()')
            elif field.format_type == 'uuid':
                validations.append('.uuid()')
        
        elif field.type in [FieldType.INTEGER, FieldType.FLOAT]:
            if field.min_value is not None:
                validations.append(f'.min({field.min_value})')
            if field.max_value is not None:
                validations.append(f'.max({field.max_value})')
        
        # Build complete field definition
        field_def = f'  {field.name}: {zod_type}{"".join(validations)}'
        
        # Add optional if needed
        if field.optional:
            field_def += '.optional()'
        
        # Add default value
        if field.default is not None:
            if isinstance(field.default, str):
                field_def += f'.default("{field.default}")'
            else:
                field_def += f'.default({str(field.default).lower() if isinstance(field.default, bool) else field.default})'
        
        # Add description as comment
        if field.description:
            field_def += f', // {field.description}'
        
        return field_def
    
    def _get_zod_type(self, field: USRField) -> str:
        """Get the Zod type for a field"""
        
        if field.type == FieldType.STRING:
            return 'z.string()'
        
        elif field.type == FieldType.INTEGER:
            return 'z.number().int()'
        
        elif field.type == FieldType.FLOAT:
            return 'z.number()'
        
        elif field.type == FieldType.BOOLEAN:
            return 'z.boolean()'
        
        elif field.type == FieldType.DATETIME:
            return 'z.date()'
        
        elif field.type == FieldType.DATE:
            return 'z.date()'
        
        elif field.type == FieldType.UUID:
            return 'z.string().uuid()'
        
        elif field.type == FieldType.LIST:
            if field.inner_type:
                inner_zod_type = self._get_zod_type(field.inner_type)
                return f'z.array({inner_zod_type})'
            else:
                return 'z.array(z.any())'
        
        elif field.type == FieldType.DICT:
            return 'z.record(z.any())'
        
        elif field.type == FieldType.UNION:
            if field.union_types:
                union_types = [self._get_zod_type(ut) for ut in field.union_types]
                return f'z.union([{", ".join(union_types)}])'
            else:
                return 'z.any()'
        
        elif field.type == FieldType.LITERAL:
            if field.literal_values:
                values = [f'"{v}"' if isinstance(v, str) else str(v) for v in field.literal_values]
                return f'z.enum([{", ".join(values)}])'
            else:
                return 'z.string()'
        
        elif field.type == FieldType.NESTED_SCHEMA:
            # For nested schemas, reference the schema by name
            return f'{field.nested_schema}Schema'
        
        else:
            return 'z.any()'
    
    def _variant_to_schema_name(self, schema_name: str, variant_name: str) -> str:
        """Convert variant name to PascalCase schema name"""
        parts = variant_name.split('_')
        variant_pascal = ''.join(word.capitalize() for word in parts)
        return f"{schema_name}{variant_pascal}"
    
    def _generate_single_schema(self, schema_name: str, description: str, 
                               field_defs: List[str], is_base_schema: bool = False) -> str:
        """Generate a single Zod schema definition"""
        lines = []
        
        if description:
            lines.append(f'/**')
            lines.append(f' * {description}')
            lines.append(f' */')
        
        lines.append(f'export const {schema_name}Schema = z.object({{')
        
        for field_def in field_defs:
            lines.append(field_def)
        
        lines.append('});')
        
        return '\n'.join(lines)
    
    def _generate_typescript_type(self, schema_name: str, fields: List[USRField]) -> str:
        """Generate TypeScript type definition"""
        return f'export type {schema_name} = z.infer<typeof {schema_name}Schema>;'
    
    def _get_typescript_type(self, field: USRField) -> str:
        """Get TypeScript type for a field (for type generation)"""
        
        if field.type == FieldType.STRING:
            return 'string'
        elif field.type == FieldType.INTEGER:
            return 'number'
        elif field.type == FieldType.FLOAT:
            return 'number'
        elif field.type == FieldType.BOOLEAN:
            return 'boolean'
        elif field.type == FieldType.DATETIME:
            return 'Date'
        elif field.type == FieldType.DATE:
            return 'Date'
        elif field.type == FieldType.UUID:
            return 'string'
        elif field.type == FieldType.LIST:
            if field.inner_type:
                inner_type = self._get_typescript_type(field.inner_type)
                return f'{inner_type}[]'
            else:
                return 'any[]'
        elif field.type == FieldType.DICT:
            return 'Record<string, any>'
        elif field.type == FieldType.UNION:
            if field.union_types:
                union_types = [self._get_typescript_type(ut) for ut in field.union_types]
                return ' | '.join(union_types)
            else:
                return 'any'
        elif field.type == FieldType.LITERAL:
            if field.literal_values:
                values = [f'"{v}"' if isinstance(v, str) else str(v) for v in field.literal_values]
                return ' | '.join(values)
            else:
                return 'string'
        elif field.type == FieldType.NESTED_SCHEMA:
            return field.nested_schema
        else:
            return 'any'
    
    def _generate_complete_file(self, schema_name: str, schemas: List[str], types: List[str]) -> str:
        """Generate complete TypeScript file with header, imports, and all schemas"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")
        
        lines = [
            '/**',
            ' * AUTO-GENERATED FILE - DO NOT EDIT MANUALLY',
            f' * Generated from: {schema_name}',
            f' * Generated at: {timestamp}',
            ' * Generator: schema-gen Zod generator',
            ' *',
            ' * To regenerate this file, run:',
            ' *     schema-gen generate --target zod',
            ' *',
            ' * Changes to this file will be overwritten.',
            ' */',
            '',
            "import { z } from 'zod';",
            '',
        ]
        
        # Add schemas
        for i, schema in enumerate(schemas):
            if i > 0:
                lines.append('')
            lines.append(schema)
        
        lines.append('')
        
        # Add TypeScript types
        for type_def in types:
            lines.append(type_def)
        
        return '\n'.join(lines)
    
    def _get_template(self) -> str:
        """Get the Jinja2 template for Zod schemas"""
        return '''/**
 * AUTO-GENERATED FILE - DO NOT EDIT MANUALLY
 * Generated from: {{ base_schema_name }}{% if variant_name %} ({{ variant_name }} variant){% endif %}
 * Generated at: {{ timestamp }}
 * Generator: schema-gen Zod generator
 *
 * To regenerate this file, run:
 *     schema-gen generate --target zod
 *
 * Changes to this file will be overwritten.
 */

import { z } from 'zod';

{%- if description %}
/**
 * {{ description }}
 */
{%- endif %}
export const {{ schema_name }}Schema = z.object({
{%- for field_def in fields %}
{{ field_def }}
{%- endfor %}
});

export type {{ schema_name }} = z.infer<typeof {{ schema_name }}Schema>;'''