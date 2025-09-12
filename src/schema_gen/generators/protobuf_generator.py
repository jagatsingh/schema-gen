"""Generator to create Protocol Buffers schemas from USR schemas"""

from datetime import datetime

from ..core.usr import FieldType, USRField, USRSchema


class ProtobufGenerator:
    """Generates Protocol Buffers (.proto) definitions from USR schemas"""

    def generate_model(self, schema: USRSchema, variant: str | None = None) -> str:
        """Generate a Protobuf message for a schema variant

        Args:
            schema: USR schema to generate from
            variant: Specific variant to generate, or None for full schema

        Returns:
            Generated Protobuf message definition
        """
        fields = schema.get_variant_fields(variant) if variant else schema.fields

        # Determine the message name
        message_name = schema.name
        if variant:
            message_name = self._variant_to_message_name(schema.name, variant)

        # Generate field definitions
        field_definitions = []
        field_number = 1

        for field in fields:
            field_def = self._generate_field_definition(field, field_number)
            field_definitions.append(field_def)
            field_number += 1

        # Build message definition
        lines = []

        if schema.description:
            lines.append(f"// {schema.description}")

        lines.append(f"message {message_name} {{")

        for field_def in field_definitions:
            lines.append(f"  {field_def}")

        lines.append("}")

        return "\n".join(lines)

    def generate_file(self, schema: USRSchema) -> str:
        """Generate a complete .proto file with all message variants

        Args:
            schema: USR schema to generate from

        Returns:
            Complete .proto file content
        """
        lines = []

        # Add proto file header
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")
        lines.extend(
            [
                "// AUTO-GENERATED FILE - DO NOT EDIT MANUALLY",
                f"// Generated from: {schema.name}",
                f"// Generated at: {timestamp}",
                "// Generator: schema-gen Protobuf generator",
                "//",
                "// To regenerate this file, run:",
                "//     schema-gen generate --target protobuf",
                "//",
                "// Changes to this file will be overwritten.",
                "",
                'syntax = "proto3";',
                "",
                f"package {schema.name.lower()};",
                "",
            ]
        )

        # Add imports if needed
        imports = self._get_required_imports(schema)
        for import_stmt in imports:
            lines.append(import_stmt)

        if imports:
            lines.append("")

        # Generate base message
        base_fields = schema.fields
        base_message = self._generate_single_message(
            schema.name, schema.description, base_fields, is_base_message=True
        )
        lines.append(base_message)
        lines.append("")

        # Generate variants
        for variant_name in schema.variants:
            variant_fields = schema.get_variant_fields(variant_name)
            variant_message_name = self._variant_to_message_name(
                schema.name, variant_name
            )
            variant_message = self._generate_single_message(
                variant_message_name, schema.description, variant_fields
            )
            lines.append(variant_message)
            lines.append("")

        # Add service definition if appropriate
        service_def = self._generate_service_definition(schema)
        if service_def:
            lines.append(service_def)

        return "\n".join(lines).rstrip() + "\n"

    def _generate_field_definition(self, field: USRField, field_number: int) -> str:
        """Generate a Protobuf field definition"""

        # Get Protobuf type
        proto_type = self._get_protobuf_type(field)

        # Handle repeated fields (lists)
        field_modifier = ""
        if field.type == FieldType.LIST:
            field_modifier = "repeated "
            # For repeated fields, get the inner type
            if field.inner_type:
                proto_type = self._get_protobuf_type(field.inner_type)
            else:
                proto_type = "string"  # Default
        elif field.optional:
            field_modifier = "optional "

        # Build field definition
        field_def = f"{field_modifier}{proto_type} {field.name} = {field_number};"

        # Add comment if description exists
        if field.description:
            field_def += f"  // {field.description}"

        return field_def

    def _get_protobuf_type(self, field: USRField) -> str:
        """Get the Protobuf type for a field"""

        if field.type == FieldType.STRING:
            return "string"

        elif field.type == FieldType.INTEGER:
            # Choose appropriate int type based on constraints
            if field.min_value is not None and field.min_value >= 0:
                if field.max_value is not None and field.max_value <= 4294967295:
                    return "uint32"
                else:
                    return "uint64"
            else:
                if field.max_value is not None and field.max_value <= 2147483647:
                    return "int32"
                else:
                    return "int64"

        elif field.type == FieldType.FLOAT:
            return "double"  # or 'float' for less precision

        elif field.type == FieldType.BOOLEAN:
            return "bool"

        elif field.type == FieldType.DATETIME:
            return "google.protobuf.Timestamp"

        elif field.type == FieldType.DATE:
            return "google.type.Date"

        elif field.type == FieldType.UUID:
            return "string"  # UUIDs are typically strings in protobuf

        elif field.type == FieldType.DECIMAL:
            return "double"  # or use google.type.Money for currency

        elif field.type == FieldType.LIST:
            # This should be handled in _generate_field_definition with 'repeated'
            if field.inner_type:
                return self._get_protobuf_type(field.inner_type)
            return "string"

        elif field.type == FieldType.DICT:
            # Protobuf maps: map<key_type, value_type>
            return "map<string, string>"  # Default to string->string map

        elif field.type == FieldType.UNION:
            # Protobuf doesn't have unions, use oneof or Any
            return "google.protobuf.Any"

        elif field.type == FieldType.LITERAL:
            # Convert to enum
            if field.literal_values:
                enum_name = f"{field.name.capitalize()}Enum"
                return enum_name
            return "string"

        elif field.type == FieldType.NESTED_SCHEMA:
            return field.nested_schema

        else:
            return "string"  # Default fallback

    def _variant_to_message_name(self, schema_name: str, variant_name: str) -> str:
        """Convert variant name to PascalCase message name"""
        parts = variant_name.split("_")
        variant_pascal = "".join(word.capitalize() for word in parts)
        return f"{schema_name}{variant_pascal}"

    def _generate_single_message(
        self,
        message_name: str,
        description: str,
        fields: list[USRField],
        is_base_message: bool = False,
    ) -> str:
        """Generate a single Protobuf message definition"""
        lines = []

        if description:
            lines.append(f"// {description}")

        lines.append(f"message {message_name} {{")

        # Generate enums first (for literal fields)
        enums = self._generate_enums_for_message(fields)
        for enum_def in enums:
            lines.append(f"  {enum_def}")
            lines.append("")

        # Generate fields
        field_number = 1
        for field in fields:
            field_def = self._generate_field_definition(field, field_number)
            lines.append(f"  {field_def}")
            field_number += 1

        lines.append("}")

        return "\n".join(lines)

    def _generate_enums_for_message(self, fields: list[USRField]) -> list[str]:
        """Generate enum definitions for literal fields"""
        enums = []

        for field in fields:
            if field.type == FieldType.LITERAL and field.literal_values:
                enum_name = f"{field.name.capitalize()}Enum"
                enum_lines = [f"enum {enum_name} {{"]

                for i, value in enumerate(field.literal_values):
                    enum_value_name = (
                        str(value).upper().replace(" ", "_").replace("-", "_")
                    )
                    enum_lines.append(f"  {enum_value_name} = {i};")

                enum_lines.append("}")
                enums.append("\n".join(enum_lines))

        return enums

    def _get_required_imports(self, schema: USRSchema) -> list[str]:
        """Get required import statements"""
        imports = []

        def check_field(field: USRField):
            if field.type == FieldType.DATETIME:
                imports.append('import "google/protobuf/timestamp.proto";')
            elif field.type == FieldType.DATE:
                imports.append('import "google/type/date.proto";')
            elif field.type == FieldType.UNION:
                imports.append('import "google/protobuf/any.proto";')
            elif field.type == FieldType.LIST and field.inner_type:
                check_field(field.inner_type)
            elif field.type == FieldType.UNION and field.union_types:
                for union_type in field.union_types:
                    check_field(union_type)

        for field in schema.fields:
            check_field(field)

        # Check if we need google.protobuf.Empty for service definitions
        if self._has_service_definition(schema):
            imports.append('import "google/protobuf/empty.proto";')

        return sorted(set(imports))

    def _has_service_definition(self, schema: USRSchema) -> bool:
        """Check if schema will generate a service definition"""
        # Only generate service for schemas that have CRUD-like variants
        crud_variants = []
        for variant_name in schema.variants:
            if any(
                crud in variant_name.lower()
                for crud in ["create", "update", "get", "list", "delete"]
            ):
                crud_variants.append(variant_name)
        return len(crud_variants) > 0

    def _generate_service_definition(self, schema: USRSchema) -> str | None:
        """Generate gRPC service definition if appropriate"""
        # Only generate service for schemas that have CRUD-like variants
        crud_variants = []
        for variant_name in schema.variants:
            if any(
                crud in variant_name.lower()
                for crud in ["create", "update", "get", "list", "delete"]
            ):
                crud_variants.append(variant_name)

        if not crud_variants:
            return None

        lines = []
        lines.append(f"// gRPC service for {schema.name}")
        lines.append(f"service {schema.name}Service {{")

        # Generate common CRUD operations
        if any("create" in v.lower() for v in crud_variants):
            create_variant = next(
                (v for v in crud_variants if "create" in v.lower()), None
            )
            if create_variant:
                create_msg = self._variant_to_message_name(schema.name, create_variant)
                lines.append(
                    f"  rpc Create{schema.name}({create_msg}) returns ({schema.name});"
                )

        lines.append(
            f"  rpc Get{schema.name}(Get{schema.name}Request) returns ({schema.name});"
        )
        lines.append(
            f"  rpc List{schema.name}(List{schema.name}Request) returns (List{schema.name}Response);"
        )

        if any("update" in v.lower() for v in crud_variants):
            update_variant = next(
                (v for v in crud_variants if "update" in v.lower()), None
            )
            if update_variant:
                update_msg = self._variant_to_message_name(schema.name, update_variant)
                lines.append(
                    f"  rpc Update{schema.name}({update_msg}) returns ({schema.name});"
                )

        lines.append(
            f"  rpc Delete{schema.name}(Delete{schema.name}Request) returns (google.protobuf.Empty);"
        )
        lines.append("}")

        # Add helper request/response messages
        lines.append("")
        lines.append(f"message Get{schema.name}Request {{")
        # Find ID field
        id_field = next(
            (f for f in schema.fields if f.primary_key or f.name.lower() == "id"), None
        )
        if id_field:
            id_type = self._get_protobuf_type(id_field)
            lines.append(f"  {id_type} id = 1;")
        lines.append("}")

        lines.append("")
        lines.append(f"message List{schema.name}Request {{")
        lines.append("  int32 page_size = 1;")
        lines.append("  string page_token = 2;")
        lines.append("}")

        lines.append("")
        lines.append(f"message List{schema.name}Response {{")
        lines.append(f"  repeated {schema.name} {schema.name.lower()}s = 1;")
        lines.append("  string next_page_token = 2;")
        lines.append("}")

        lines.append("")
        lines.append(f"message Delete{schema.name}Request {{")
        if id_field:
            id_type = self._get_protobuf_type(id_field)
            lines.append(f"  {id_type} id = 1;")
        lines.append("}")

        return "\n".join(lines)
