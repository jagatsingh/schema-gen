"""Generator to create Kotlin data classes from USR schemas"""

from datetime import datetime

from ..core.usr import FieldType, USRField, USRSchema
from .base import BaseGenerator


class KotlinGenerator(BaseGenerator):
    """Generates Kotlin data classes from USR schemas"""

    def __init__(self, default_package: str = "com.example.models"):
        self.default_package = default_package

    @property
    def file_extension(self) -> str:
        return ".kt"

    def get_schema_filename(self, schema: USRSchema) -> str:
        return f"{schema.name}.kt"

    def generate_model(self, schema: USRSchema, variant: str | None = None) -> str:
        """Generate a single Kotlin data class for a schema variant

        Args:
            schema: USR schema to generate from
            variant: Specific variant to generate, or None for full schema

        Returns:
            Generated Kotlin data class code
        """
        fields = schema.get_variant_fields(variant) if variant else schema.fields

        # Determine the class name
        class_name = schema.name
        if variant:
            class_name = self._variant_to_class_name(schema.name, variant)

        return self._generate_single_data_class(class_name, schema.description, fields)

    def generate_file(self, schema: USRSchema) -> str:
        """Generate a complete Kotlin file with all data class variants

        Args:
            schema: USR schema to generate from

        Returns:
            Complete Kotlin file content with all data classes
        """
        lines = []

        # Add file header
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")
        lines.extend(
            [
                "/**",
                " * AUTO-GENERATED FILE - DO NOT EDIT MANUALLY",
                f" * Generated from: {schema.name}",
                f" * Generated at: {timestamp}",
                " * Generator: schema-gen Kotlin generator",
                " *",
                " * To regenerate this file, run:",
                " *     schema-gen generate --target kotlin",
                " *",
                " * Changes to this file will be overwritten.",
                " */",
            ]
        )

        # Add package declaration
        package_name = schema.target_config.get("kotlin", {}).get(
            "package", self.default_package
        )
        lines.extend(["", f"package {package_name}", ""])

        # Add imports
        imports = self._get_required_imports(schema)
        for import_stmt in imports:
            lines.append(import_stmt)
        if imports:
            lines.append("")

        # Generate base data class
        base_class = self._generate_single_data_class(
            schema.name, schema.description, schema.fields, is_base_class=True
        )
        lines.append(base_class)
        lines.append("")

        # Generate variants
        for variant_name in schema.variants:
            variant_fields = schema.get_variant_fields(variant_name)
            variant_class_name = self._variant_to_class_name(schema.name, variant_name)
            variant_class = self._generate_single_data_class(
                variant_class_name, schema.description, variant_fields
            )
            lines.append(variant_class)
            lines.append("")

        return "\n".join(lines).rstrip() + "\n"

    def _generate_single_data_class(
        self,
        class_name: str,
        description: str,
        fields: list[USRField],
        is_base_class: bool = False,
    ) -> str:
        """Generate a single Kotlin data class definition"""
        lines = []

        if description:
            lines.extend(["/**", f" * {description}", " */"])

        # Add serialization annotations if needed
        lines.append("@Serializable")

        # Data class declaration
        if not fields:
            lines.append(f"data class {class_name}()")
            return "\n".join(lines)

        lines.append(f"data class {class_name}(")

        # Generate constructor parameters
        for i, field in enumerate(fields):
            param_def = self._generate_parameter_definition(field)
            separator = "," if i < len(fields) - 1 else ""
            # Split parameter and comment to avoid syntax errors
            if "  // " in param_def:
                param_part, comment_part = param_def.split("  // ", 1)
                lines.append(f"    {param_part}{separator}  // {comment_part}")
            else:
                lines.append(f"    {param_def}{separator}")

        lines.append(")")

        return "\n".join(lines)

    def _generate_parameter_definition(self, field: USRField) -> str:
        """Generate Kotlin constructor parameter definition"""

        # Get Kotlin type
        kotlin_type = self._get_kotlin_type(field)

        # Build parameter definition
        annotations = []

        # JSON property annotation - add @SerialName when the Kotlin property name
        # (camelCase) differs from the original field name (snake_case)
        kotlin_name = self._to_camel_case(field.name)
        if kotlin_name != field.name:
            annotations.append(f'@SerialName("{field.name}")')

        # Validation annotations
        if field.type == FieldType.STRING:
            if field.min_length is not None or field.max_length is not None:
                # Kotlin doesn't have built-in validation like Java, but we can add custom ones
                pass

        # Default value
        default_value = ""
        if field.default is not None:
            from enum import Enum as PyEnum

            if isinstance(field.default, PyEnum):
                default_value = f' = "{field.default.value}"'
            elif isinstance(field.default, str):
                default_value = f' = "{field.default}"'
            elif isinstance(field.default, bool):
                # Use Kotlin boolean literals
                default_value = f" = {'true' if field.default else 'false'}"
            elif isinstance(field.default, list):
                # Use Kotlin list initialization
                if field.default == []:
                    default_value = " = emptyList()"
                else:
                    # For non-empty lists, format properly
                    if all(isinstance(x, str) for x in field.default):
                        list_items = ", ".join(f'"{x}"' for x in field.default)
                        default_value = f" = listOf({list_items})"
                    else:
                        list_items = ", ".join(str(x) for x in field.default)
                        default_value = f" = listOf({list_items})"
            else:
                default_value = f" = {field.default}"
        elif field.optional:
            default_value = " = null"
        elif field.type == FieldType.LIST and not field.optional:
            # Non-optional lists should have empty list as default
            default_value = " = emptyList()"
        elif field.type in (FieldType.SET, FieldType.FROZENSET) and not field.optional:
            # Non-optional sets should have empty set as default
            default_value = " = emptySet()"

        # Build complete parameter
        annotation_str = " ".join(annotations) + " " if annotations else ""
        prop_name = self._to_camel_case(field.name)
        param = f"{annotation_str}val {prop_name}: {kotlin_type}{default_value}"

        # Add comment if description exists
        if field.description:
            param += f"  // {field.description}"

        return param

    def _get_kotlin_type(self, field: USRField) -> str:
        """Get the Kotlin type for a field"""

        base_type = ""

        if field.type == FieldType.STRING:
            base_type = "String"

        elif field.type == FieldType.INTEGER:
            # Choose based on size constraints
            if field.max_value is not None and field.max_value <= 2147483647:
                base_type = "Int"
            else:
                base_type = "Long"

        elif field.type == FieldType.FLOAT:
            base_type = "Double"  # or Float for less precision

        elif field.type == FieldType.BOOLEAN:
            base_type = "Boolean"

        elif field.type == FieldType.DATETIME:
            base_type = "Instant"  # kotlinx.datetime

        elif field.type == FieldType.DATE:
            base_type = "LocalDate"  # kotlinx.datetime

        elif field.type == FieldType.UUID:
            base_type = "String"  # Kotlin doesn't have built-in UUID, often use String

        elif field.type == FieldType.DECIMAL:
            base_type = "BigDecimal"

        elif field.type == FieldType.LIST:
            if field.inner_type:
                inner_type = self._get_kotlin_type(field.inner_type)
                base_type = f"List<{inner_type}>"
            else:
                base_type = "List<Any>"

        elif field.type in (FieldType.SET, FieldType.FROZENSET):
            if field.inner_type:
                inner_type = self._get_kotlin_type(field.inner_type)
                base_type = f"Set<{inner_type}>"
            else:
                base_type = "Set<Any>"

        elif field.type == FieldType.TUPLE:
            if field.union_types:
                inner_types = [self._get_kotlin_type(ut) for ut in field.union_types]
                if len(inner_types) == 2:
                    base_type = f"Pair<{inner_types[0]}, {inner_types[1]}>"
                elif len(inner_types) == 3:
                    base_type = (
                        f"Triple<{inner_types[0]}, {inner_types[1]}, {inner_types[2]}>"
                    )
                else:
                    base_type = "List<Any>"
            else:
                base_type = "List<Any>"

        elif field.type == FieldType.DICT:
            base_type = "Map<String, Any>"

        elif field.type == FieldType.UNION:
            if field.union_types:
                # Kotlin uses sealed classes for unions, but for simplicity use Any
                base_type = "Any"
            else:
                base_type = "Any"

        elif field.type == FieldType.LITERAL:
            if field.literal_values:
                # Could generate an enum, but for simplicity use base type
                if all(isinstance(v, str) for v in field.literal_values):
                    base_type = "String"
                elif all(isinstance(v, int) for v in field.literal_values):
                    base_type = "Int"
                else:
                    base_type = "Any"
            else:
                base_type = "String"

        elif field.type == FieldType.ENUM:
            base_type = "String"  # Enum values serialized as strings

        elif field.type == FieldType.NESTED_SCHEMA:
            base_type = field.nested_schema

        else:
            base_type = "Any"

        # Handle nullable types
        if field.optional:
            base_type += "?"

        return base_type

    def _get_required_imports(self, schema: USRSchema) -> list[str]:
        """Get required import statements"""
        imports = set()

        # Kotlinx serialization
        imports.add("import kotlinx.serialization.Serializable")

        def check_field_imports(field: USRField):
            if field.type == FieldType.DATETIME:
                imports.add("import kotlinx.datetime.Instant")
            elif field.type == FieldType.DATE:
                imports.add("import kotlinx.datetime.LocalDate")
            elif field.type == FieldType.DECIMAL:
                imports.add("import java.math.BigDecimal")
            elif (
                field.type == FieldType.LIST
                and field.inner_type
                or field.type in (FieldType.SET, FieldType.FROZENSET)
                and field.inner_type
            ):
                check_field_imports(field.inner_type)
            # Add SerialName import if any field needs a camelCase mapping
            if self._to_camel_case(field.name) != field.name:
                imports.add("import kotlinx.serialization.SerialName")

        for field in schema.fields:
            check_field_imports(field)

        return sorted(imports)

    def _to_camel_case(self, snake_str: str) -> str:
        """Convert snake_case string to camelCase"""
        parts = snake_str.split("_")
        if len(parts) == 1:
            return snake_str
        return parts[0] + "".join(word.capitalize() for word in parts[1:])

    def _variant_to_class_name(self, schema_name: str, variant_name: str) -> str:
        """Convert variant name to PascalCase class name"""
        parts = variant_name.split("_")
        variant_pascal = "".join(word.capitalize() for word in parts)
        return f"{schema_name}{variant_pascal}"
