"""Generator to create GraphQL schema from USR schemas"""

from datetime import datetime

from ..core.usr import FieldType, USRField, USRSchema
from .base import BaseGenerator


class GraphQLGenerator(BaseGenerator):
    """Generates GraphQL schema definitions from USR schemas"""

    @property
    def file_extension(self) -> str:
        return ".graphql"

    def generate_model(self, schema: USRSchema, variant: str | None = None) -> str:
        """Generate a GraphQL type for a schema variant

        Args:
            schema: USR schema to generate from
            variant: Specific variant to generate, or None for full schema

        Returns:
            Generated GraphQL type definition
        """
        fields = schema.get_variant_fields(variant) if variant else schema.fields

        # Determine the type name
        type_name = schema.name
        if variant:
            type_name = self._variant_to_type_name(schema.name, variant)

        # Generate field definitions
        field_definitions = []

        for field in fields:
            field_def = self._generate_field_definition(field)
            field_definitions.append(field_def)

        # Build type definition
        lines = []

        if schema.description:
            lines.append('"""')
            lines.append(f"{schema.description}")
            lines.append('"""')

        lines.append(f"type {type_name} {{")

        for field_def in field_definitions:
            lines.append(f"  {field_def}")

        lines.append("}")

        return "\n".join(lines)

    def generate_file(self, schema: USRSchema) -> str:
        """Generate a complete GraphQL schema file with all variants

        Args:
            schema: USR schema to generate from

        Returns:
            Complete GraphQL schema file content
        """
        lines = []

        # Add header comment
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")
        lines.extend(
            [
                "# AUTO-GENERATED FILE - DO NOT EDIT MANUALLY",
                f"# Generated from: {schema.name}",
                f"# Generated at: {timestamp}",
                "# Generator: schema-gen GraphQL generator",
                "#",
                "# To regenerate this file, run:",
                "#     schema-gen generate --target graphql",
                "#",
                "# Changes to this file will be overwritten.",
                "",
            ]
        )

        # Add custom scalars if needed
        scalars = self._get_required_scalars(schema)
        for scalar in scalars:
            lines.append(f"scalar {scalar}")

        if scalars:
            lines.append("")

        # Generate base type
        base_fields = schema.fields
        base_type = self._generate_single_type(
            schema.name, schema.description, base_fields, is_base_type=True
        )
        lines.append(base_type)
        lines.append("")

        # Generate variants
        for variant_name in schema.variants:
            variant_fields = schema.get_variant_fields(variant_name)
            variant_type_name = self._variant_to_type_name(schema.name, variant_name)
            variant_type = self._generate_single_type(
                variant_type_name, schema.description, variant_fields
            )
            lines.append(variant_type)
            lines.append("")

        # Generate input types (for mutations)
        input_types = self._generate_input_types(schema)
        for input_type in input_types:
            lines.append(input_type)
            lines.append("")

        return "\n".join(lines).rstrip() + "\n"

    def _generate_field_definition(self, field: USRField) -> str:
        """Generate a GraphQL field definition"""

        # Get GraphQL type
        graphql_type = self._get_graphql_type(field)

        # Add nullability
        if not field.optional and field.default is None:
            graphql_type += "!"

        # Build field definition
        field_def = f"{field.name}: {graphql_type}"

        # Add description as comment
        if field.description:
            field_def += f"  # {field.description}"

        return field_def

    def _get_graphql_type(self, field: USRField) -> str:
        """Get the GraphQL type for a field"""

        if field.type == FieldType.STRING:
            if field.format_type in ["email", "uri", "uuid"]:
                return "String"  # Could use custom scalars
            return "String"

        elif field.type == FieldType.INTEGER:
            return "Int"

        elif field.type == FieldType.FLOAT:
            return "Float"

        elif field.type == FieldType.BOOLEAN:
            return "Boolean"

        elif field.type == FieldType.DATETIME:
            return "DateTime"  # Custom scalar

        elif field.type == FieldType.DATE:
            return "Date"  # Custom scalar

        elif field.type == FieldType.UUID:
            return "UUID"  # Custom scalar

        elif field.type == FieldType.DECIMAL:
            return "Decimal"  # Custom scalar

        elif field.type == FieldType.LIST or field.type in (
            FieldType.SET,
            FieldType.FROZENSET,
        ):
            if field.inner_type:
                inner_type = self._get_graphql_type(field.inner_type)
                return f"[{inner_type}]"
            else:
                return "[String]"  # Default to string array

        elif field.type == FieldType.TUPLE:
            # GraphQL has no native tuple type; fallback to list
            if field.union_types and len(field.union_types) == 1:
                inner_type = self._get_graphql_type(field.union_types[0])
                return f"[{inner_type}]"
            return "[String]"

        elif field.type == FieldType.DICT:
            return "JSON"  # Custom scalar for arbitrary objects

        elif field.type == FieldType.UNION:
            if field.union_types and len(field.union_types) > 1:
                # GraphQL unions require named types, so we'd need to define them
                # For now, use String as fallback
                return "String"
            elif field.union_types and len(field.union_types) == 1:
                return self._get_graphql_type(field.union_types[0])
            else:
                return "String"

        elif field.type == FieldType.LITERAL:
            if field.literal_values:
                # Could create an enum type
                enum_name = f"{field.name.capitalize()}Enum"
                return enum_name
            else:
                return "String"

        elif field.type == FieldType.ENUM:
            return "String"  # Enum values as strings

        elif field.type == FieldType.NESTED_SCHEMA:
            return field.nested_schema

        else:
            return "String"  # Default fallback

    def _variant_to_type_name(self, schema_name: str, variant_name: str) -> str:
        """Convert variant name to GraphQL type name"""
        parts = variant_name.split("_")
        variant_pascal = "".join(word.capitalize() for word in parts)
        return f"{schema_name}{variant_pascal}"

    def _generate_single_type(
        self,
        type_name: str,
        description: str,
        fields: list[USRField],
        is_base_type: bool = False,
    ) -> str:
        """Generate a single GraphQL type definition"""
        lines = []

        if description:
            lines.append('"""')
            lines.append(description)
            lines.append('"""')

        lines.append(f"type {type_name} {{")

        for field in fields:
            field_def = self._generate_field_definition(field)
            lines.append(f"  {field_def}")

        lines.append("}")

        return "\n".join(lines)

    def _generate_input_types(self, schema: USRSchema) -> list[str]:
        """Generate input types for mutations"""
        input_types = []

        # Generate input type for base schema (for creating)
        create_fields = [
            f for f in schema.fields if not f.primary_key and not f.auto_increment
        ]
        if create_fields:
            input_type = self._generate_input_type(
                f"{schema.name}Input", "Input for creating/updating", create_fields
            )
            input_types.append(input_type)

        # Generate input types for variants that could be used for creation
        for variant_name in schema.variants:
            if "create" in variant_name.lower() or "input" in variant_name.lower():
                variant_fields = schema.get_variant_fields(variant_name)
                variant_input_name = (
                    self._variant_to_type_name(schema.name, variant_name) + "Input"
                )
                variant_input = self._generate_input_type(
                    variant_input_name, f"Input for {variant_name}", variant_fields
                )
                input_types.append(variant_input)

        return input_types

    def _generate_input_type(
        self, input_name: str, description: str, fields: list[USRField]
    ) -> str:
        """Generate a GraphQL input type definition"""
        lines = []

        lines.append('"""')
        lines.append(description)
        lines.append('"""')
        lines.append(f"input {input_name} {{")

        for field in fields:
            graphql_type = self._get_graphql_type(field)
            # Input fields are generally optional unless explicitly required
            if not field.optional and field.default is None and not field.primary_key:
                graphql_type += "!"

            field_def = f"  {field.name}: {graphql_type}"
            if field.description:
                field_def += f"  # {field.description}"
            lines.append(field_def)

        lines.append("}")

        return "\n".join(lines)

    def _get_required_scalars(self, schema: USRSchema) -> list[str]:
        """Get list of custom scalars needed for this schema"""
        scalars = set()

        def check_field(field: USRField):
            if field.type == FieldType.DATETIME:
                scalars.add("DateTime")
            elif field.type == FieldType.DATE:
                scalars.add("Date")
            elif field.type == FieldType.UUID:
                scalars.add("UUID")
            elif field.type == FieldType.DECIMAL:
                scalars.add("Decimal")
            elif field.type == FieldType.DICT:
                scalars.add("JSON")
            elif (
                field.type in (FieldType.LIST, FieldType.SET, FieldType.FROZENSET)
                and field.inner_type
            ):
                check_field(field.inner_type)
            elif field.type == FieldType.UNION and field.union_types:
                for union_type in field.union_types:
                    check_field(union_type)

        for field in schema.fields:
            check_field(field)

        return sorted(scalars)
