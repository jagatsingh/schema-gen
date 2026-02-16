"""Generator to create Apache Avro schemas from USR schemas"""

import json
from datetime import datetime
from typing import Any

from ..core.usr import FieldType, USRField, USRSchema
from .base import BaseGenerator


class AvroGenerator(BaseGenerator):
    """Generates Apache Avro schema definitions from USR schemas"""

    @property
    def file_extension(self) -> str:
        return ".avsc"

    def generate_model(self, schema: USRSchema, variant: str | None = None) -> str:
        """Generate an Avro schema for a schema variant

        Args:
            schema: USR schema to generate from
            variant: Specific variant to generate, or None for full schema

        Returns:
            Generated Avro schema as JSON string
        """
        fields = schema.get_variant_fields(variant) if variant else schema.fields

        # Determine the record name
        record_name = schema.name
        if variant:
            record_name = self._variant_to_record_name(schema.name, variant)

        # Build Avro record schema
        avro_schema = {
            "type": "record",
            "name": record_name,
            "namespace": f"com.example.{schema.name.lower()}",
            "fields": [],
        }

        if schema.description:
            avro_schema["doc"] = schema.description

        # Add fields
        for field in fields:
            field_def = self._generate_field_definition(field)
            avro_schema["fields"].append(field_def)

        return json.dumps(avro_schema, indent=2)

    def generate_file(self, schema: USRSchema) -> str:
        """Generate a complete Avro schema file with all record variants

        Args:
            schema: USR schema to generate from

        Returns:
            Complete Avro schema file content (JSON)
        """
        # For Avro, we'll create a schema collection with all variants
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")

        schema_collection = {
            "_meta": {
                "generator": "schema-gen Avro generator",
                "generated_from": schema.name,
                "generated_at": timestamp,
                "note": "AUTO-GENERATED FILE - DO NOT EDIT MANUALLY",
            },
            "schemas": [],
        }

        # Generate base record
        base_record = self._generate_record_schema(
            schema.name, schema.description, schema.fields, is_base_record=True
        )
        schema_collection["schemas"].append(base_record)

        # Generate variants
        for variant_name in schema.variants:
            variant_fields = schema.get_variant_fields(variant_name)
            variant_record_name = self._variant_to_record_name(
                schema.name, variant_name
            )
            variant_record = self._generate_record_schema(
                variant_record_name, schema.description, variant_fields
            )
            schema_collection["schemas"].append(variant_record)

        return json.dumps(schema_collection, indent=2)

    def _generate_record_schema(
        self,
        record_name: str,
        description: str,
        fields: list[USRField],
        is_base_record: bool = False,
    ) -> dict[str, Any]:
        """Generate a single Avro record schema"""
        record_schema = {
            "type": "record",
            "name": record_name,
            "namespace": f"com.example.{record_name.lower()}",
            "fields": [],
        }

        if description:
            record_schema["doc"] = description

        # Add fields
        for field in fields:
            field_def = self._generate_field_definition(field)
            record_schema["fields"].append(field_def)

        return record_schema

    def _generate_field_definition(self, field: USRField) -> dict[str, Any]:
        """Generate an Avro field definition"""

        # Get Avro type
        avro_type = self._get_avro_type(field)

        # Build field definition
        field_def = {"name": field.name, "type": avro_type}

        # Add documentation
        if field.description:
            field_def["doc"] = field.description

        # Add default value if present
        if field.default is not None:
            from enum import Enum as PyEnum

            default_val = (
                field.default.value
                if isinstance(field.default, PyEnum)
                else field.default
            )
            field_def["default"] = default_val
        elif field.optional:
            # For optional fields without defaults, set default to null
            field_def["default"] = None

        # Add aliases if needed (for schema evolution)
        aliases = field.metadata.get("avro_aliases", [])
        if aliases:
            field_def["aliases"] = aliases

        return field_def

    def _get_avro_type(self, field: USRField) -> Any:
        """Get the Avro type for a field"""

        base_type = self._get_base_avro_type(field)

        # Handle optional fields (union with null)
        if field.optional:
            if isinstance(base_type, list):
                # Already a union, ensure null is present and comes first
                if "null" not in base_type:
                    return ["null"] + base_type
                elif base_type[0] != "null":
                    # null exists but not first — move it to front
                    reordered = ["null"] + [t for t in base_type if t != "null"]
                    return reordered
                return base_type
            else:
                # Make it a union with null first
                return ["null", base_type]

        return base_type

    def _get_base_avro_type(self, field: USRField) -> Any:
        """Get the base Avro type (without null union)"""

        if field.type == FieldType.STRING:
            return "string"

        elif field.type == FieldType.INTEGER:
            # Choose int or long based on constraints
            if (
                field.max_value is not None
                and field.max_value <= 2147483647
                and field.min_value is not None
                and field.min_value >= -2147483648
            ):
                return "int"
            else:
                return "long"

        elif field.type == FieldType.FLOAT:
            return "double"  # or "float" for less precision

        elif field.type == FieldType.BOOLEAN:
            return "boolean"

        elif field.type == FieldType.DATETIME:
            # Use logical types for timestamps
            return {"type": "long", "logicalType": "timestamp-millis"}

        elif field.type == FieldType.DATE:
            return {"type": "int", "logicalType": "date"}

        elif field.type == FieldType.UUID:
            return {"type": "string", "logicalType": "uuid"}

        elif field.type == FieldType.DECIMAL:
            # Decimal logical type
            precision = field.target_config.get("avro", {}).get("precision", 10)
            scale = field.target_config.get("avro", {}).get("scale", 2)
            return {
                "type": "bytes",
                "logicalType": "decimal",
                "precision": precision,
                "scale": scale,
            }

        elif field.type == FieldType.LIST or field.type in (
            FieldType.SET,
            FieldType.FROZENSET,
        ):
            item_type = "string"  # default
            if field.inner_type:
                item_type = self._get_base_avro_type(field.inner_type)

            return {"type": "array", "items": item_type}

        elif field.type == FieldType.TUPLE:
            # Avro has no tuple type; best-effort array with union of inner types
            if field.union_types:
                inner_types = []
                for ut in field.union_types:
                    avro_type = self._get_base_avro_type(ut)
                    if avro_type not in inner_types:
                        inner_types.append(avro_type)
                if len(inner_types) == 1:
                    items_type = inner_types[0]
                else:
                    items_type = inner_types
                return {"type": "array", "items": items_type}
            return {"type": "array", "items": "string"}

        elif field.type == FieldType.DICT:
            return {"type": "map", "values": "string"}  # Could be made configurable

        elif field.type == FieldType.UNION:
            if field.union_types:
                union_types = []
                for union_type in field.union_types:
                    avro_type = self._get_base_avro_type(union_type)
                    union_types.append(avro_type)
                return union_types
            else:
                return "string"

        elif field.type == FieldType.LITERAL:
            if field.literal_values:
                # Create an enum
                enum_name = f"{field.name.capitalize()}Enum"
                return {
                    "type": "enum",
                    "name": enum_name,
                    "symbols": [
                        str(v).replace(" ", "_").replace("-", "_")
                        for v in field.literal_values
                    ],
                }
            else:
                return "string"

        elif field.type == FieldType.ENUM:
            if field.enum_values:
                return {
                    "type": "enum",
                    "name": field.enum_name or f"{field.name.capitalize()}Enum",
                    "symbols": [str(v) for v in field.enum_values],
                }
            return "string"

        elif field.type == FieldType.NESTED_SCHEMA:
            # Reference to another record
            return field.nested_schema

        else:
            return "string"  # Default fallback

    def _variant_to_record_name(self, schema_name: str, variant_name: str) -> str:
        """Convert variant name to PascalCase record name"""
        parts = variant_name.split("_")
        variant_pascal = "".join(word.capitalize() for word in parts)
        return f"{schema_name}{variant_pascal}"

    def generate_single_schema(
        self, schema: USRSchema, variant: str | None = None
    ) -> dict[str, Any]:
        """Generate a single Avro schema as a Python dict (useful for programmatic use)"""
        fields = schema.get_variant_fields(variant) if variant else schema.fields

        record_name = schema.name
        if variant:
            record_name = self._variant_to_record_name(schema.name, variant)

        avro_schema = {
            "type": "record",
            "name": record_name,
            "namespace": f"com.example.{schema.name.lower()}",
            "fields": [],
        }

        if schema.description:
            avro_schema["doc"] = schema.description

        for field in fields:
            field_def = self._generate_field_definition(field)
            avro_schema["fields"].append(field_def)

        return avro_schema
