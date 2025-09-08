"""Generator to create JSON Schema from USR schemas"""

import json
from datetime import datetime
from typing import Any

from ..core.usr import FieldType, USRField, USRSchema


class JsonSchemaGenerator:
    """Generates JSON Schema definitions from USR schemas"""

    def generate_model(self, schema: USRSchema, variant: str | None = None) -> str:
        """Generate a JSON Schema for a schema variant

        Args:
            schema: USR schema to generate from
            variant: Specific variant to generate, or None for full schema

        Returns:
            Generated JSON Schema as JSON string
        """
        fields = schema.get_variant_fields(variant) if variant else schema.fields

        # Determine the schema title
        schema_title = schema.name
        if variant:
            schema_title = self._variant_to_schema_title(schema.name, variant)

        # Build JSON Schema object
        json_schema = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": f"https://example.com/schemas/{schema_title.lower()}.json",
            "title": schema_title,
            "type": "object",
            "properties": {},
            "required": [],
        }

        if schema.description:
            json_schema["description"] = schema.description

        # Add properties and required fields
        for field in fields:
            field_schema = self._generate_field_schema(field)
            json_schema["properties"][field.name] = field_schema

            if not field.optional and field.default is None:
                json_schema["required"].append(field.name)

        # Remove empty required array
        if not json_schema["required"]:
            del json_schema["required"]

        return json.dumps(json_schema, indent=2)

    def generate_file(self, schema: USRSchema) -> str:
        """Generate a complete JSON file with all schema variants

        Args:
            schema: USR schema to generate from

        Returns:
            Complete JSON Schema file content
        """
        # For JSON Schema, we'll create a definitions-based schema with all variants
        json_schema = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": f"https://example.com/schemas/{schema.name.lower()}.json",
            "title": f"{schema.name} Schema Collection",
            "description": f"Auto-generated JSON Schema for {schema.name} and its variants",
            "$defs": {},
        }

        # Add base schema
        base_fields = schema.fields
        base_schema = self._generate_schema_definition(
            schema.name, schema.description, base_fields
        )
        json_schema["$defs"][schema.name] = base_schema

        # Add variants
        for variant_name in schema.variants:
            variant_fields = schema.get_variant_fields(variant_name)
            variant_title = self._variant_to_schema_title(schema.name, variant_name)
            variant_schema = self._generate_schema_definition(
                variant_title, schema.description, variant_fields
            )
            json_schema["$defs"][variant_title] = variant_schema

        # Set the main schema to reference the base schema
        json_schema["$ref"] = f"#/$defs/{schema.name}"

        # Add header comment as a special property (will be formatted in file generation)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")
        json_schema["_meta"] = {
            "generator": "schema-gen JSON Schema generator",
            "generated_from": schema.name,
            "generated_at": timestamp,
            "note": "AUTO-GENERATED FILE - DO NOT EDIT MANUALLY",
        }

        return json.dumps(json_schema, indent=2)

    def _generate_schema_definition(
        self, title: str, description: str, fields: list[USRField]
    ) -> dict[str, Any]:
        """Generate a schema definition object"""
        schema_def = {
            "type": "object",
            "title": title,
            "properties": {},
            "required": [],
        }

        if description:
            schema_def["description"] = description

        for field in fields:
            field_schema = self._generate_field_schema(field)
            schema_def["properties"][field.name] = field_schema

            if not field.optional and field.default is None:
                schema_def["required"].append(field.name)

        # Remove empty required array
        if not schema_def["required"]:
            del schema_def["required"]

        return schema_def

    def _generate_field_schema(self, field: USRField) -> dict[str, Any]:
        """Generate a JSON Schema property definition for a field"""
        field_schema = {}

        # Get base JSON Schema type
        self._add_type_info(field, field_schema)

        # Add description
        if field.description:
            field_schema["description"] = field.description

        # Add default value
        if field.default is not None:
            field_schema["default"] = field.default

        # Add validation constraints
        self._add_validation_constraints(field, field_schema)

        return field_schema

    def _add_type_info(self, field: USRField, field_schema: dict[str, Any]):
        """Add type information to field schema"""

        if field.type == FieldType.STRING:
            field_schema["type"] = "string"
            if field.format_type == "email":
                field_schema["format"] = "email"
            elif field.format_type == "uri":
                field_schema["format"] = "uri"
            elif field.format_type == "uuid":
                field_schema["format"] = "uuid"

        elif field.type == FieldType.INTEGER:
            field_schema["type"] = "integer"

        elif field.type == FieldType.FLOAT:
            field_schema["type"] = "number"

        elif field.type == FieldType.BOOLEAN:
            field_schema["type"] = "boolean"

        elif field.type == FieldType.DATETIME:
            field_schema["type"] = "string"
            field_schema["format"] = "date-time"

        elif field.type == FieldType.DATE:
            field_schema["type"] = "string"
            field_schema["format"] = "date"

        elif field.type == FieldType.UUID:
            field_schema["type"] = "string"
            field_schema["format"] = "uuid"

        elif field.type == FieldType.LIST:
            field_schema["type"] = "array"
            if field.inner_type:
                item_schema = {}
                self._add_type_info(field.inner_type, item_schema)
                field_schema["items"] = item_schema

        elif field.type == FieldType.DICT:
            field_schema["type"] = "object"
            field_schema["additionalProperties"] = True

        elif field.type == FieldType.UNION:
            if field.union_types:
                union_schemas = []
                for union_type in field.union_types:
                    union_schema = {}
                    self._add_type_info(union_type, union_schema)
                    union_schemas.append(union_schema)
                field_schema["anyOf"] = union_schemas

        elif field.type == FieldType.LITERAL:
            if field.literal_values:
                field_schema["enum"] = field.literal_values
                # Infer type from literal values
                if all(isinstance(v, str) for v in field.literal_values):
                    field_schema["type"] = "string"
                elif all(isinstance(v, int) for v in field.literal_values):
                    field_schema["type"] = "integer"
                elif all(isinstance(v, int | float) for v in field.literal_values):
                    field_schema["type"] = "number"

        elif field.type == FieldType.NESTED_SCHEMA:
            field_schema["$ref"] = f"#/$defs/{field.nested_schema}"

        else:
            # Default to allowing any type
            pass

    def _add_validation_constraints(
        self, field: USRField, field_schema: dict[str, Any]
    ):
        """Add validation constraints to field schema"""

        if field.type == FieldType.STRING:
            if field.min_length is not None:
                field_schema["minLength"] = field.min_length
            if field.max_length is not None:
                field_schema["maxLength"] = field.max_length
            if field.regex_pattern:
                field_schema["pattern"] = field.regex_pattern

        elif field.type in [FieldType.INTEGER, FieldType.FLOAT]:
            if field.min_value is not None:
                field_schema["minimum"] = field.min_value
            if field.max_value is not None:
                field_schema["maximum"] = field.max_value

        elif field.type == FieldType.LIST:
            if field.min_length is not None:
                field_schema["minItems"] = field.min_length
            if field.max_length is not None:
                field_schema["maxItems"] = field.max_length

    def _variant_to_schema_title(self, schema_name: str, variant_name: str) -> str:
        """Convert variant name to schema title"""
        parts = variant_name.split("_")
        variant_pascal = "".join(word.capitalize() for word in parts)
        return f"{schema_name}{variant_pascal}"
