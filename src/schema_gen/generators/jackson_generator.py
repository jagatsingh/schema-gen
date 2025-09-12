"""Generator to create Java classes with Jackson annotations from USR schemas"""

from datetime import datetime

from ..core.usr import FieldType, USRField, USRSchema


class JacksonGenerator:
    """Generates Java classes with Jackson JSON annotations from USR schemas"""

    def generate_model(self, schema: USRSchema, variant: str | None = None) -> str:
        """Generate a single Java class for a schema variant

        Args:
            schema: USR schema to generate from
            variant: Specific variant to generate, or None for full schema

        Returns:
            Generated Java class code
        """
        fields = schema.get_variant_fields(variant) if variant else schema.fields

        # Determine the class name
        class_name = schema.name
        if variant:
            class_name = self._variant_to_class_name(schema.name, variant)

        return self._generate_single_class(
            class_name, schema.description, fields, is_base_class=(variant is None)
        )

    def generate_file(self, schema: USRSchema) -> str:
        """Generate a complete Java file with all class variants

        Args:
            schema: USR schema to generate from

        Returns:
            Complete Java file content with all classes
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
                " * Generator: schema-gen Jackson generator",
                " *",
                " * To regenerate this file, run:",
                " *     schema-gen generate --target jackson",
                " *",
                " * Changes to this file will be overwritten.",
                " */",
                "",
            ]
        )

        # Add package declaration
        package_name = f"com.example.{schema.name.lower()}"
        lines.append(f"package {package_name};")
        lines.append("")

        # Add imports
        imports = self._get_required_imports(schema)
        for import_stmt in imports:
            lines.append(import_stmt)
        lines.append("")

        # Generate base class
        base_class = self._generate_single_class(
            schema.name, schema.description, schema.fields, is_base_class=True
        )
        lines.append(base_class)
        lines.append("")

        # Generate variants
        for variant_name in schema.variants:
            variant_fields = schema.get_variant_fields(variant_name)
            variant_class_name = self._variant_to_class_name(schema.name, variant_name)
            variant_class = self._generate_single_class(
                variant_class_name, schema.description, variant_fields
            )
            lines.append(variant_class)
            lines.append("")

        return "\n".join(lines).rstrip() + "\n"

    def _generate_single_class(
        self,
        class_name: str,
        description: str,
        fields: list[USRField],
        is_base_class: bool = False,
    ) -> str:
        """Generate a single Java class definition"""
        lines = []

        if description:
            lines.extend(["/**", f" * {description}", " */"])

        # Only the base class should be public, variants should be package-private
        visibility = "public " if is_base_class else ""
        lines.extend(
            [
                "@JsonInclude(JsonInclude.Include.NON_NULL)",
                "@JsonPropertyOrder({"
                + ", ".join(f'"{f.name}"' for f in fields)
                + "})",
                f"{visibility}class {class_name} {{",
            ]
        )

        # Generate fields with annotations
        for field in fields:
            field_def = self._generate_field_definition(field)
            lines.extend([""] + field_def)

        # Generate constructors
        lines.extend(["", "    // Constructors"])
        lines.append(f"    public {class_name}() {{}}")

        if fields:
            lines.append("")
            constructor_params = []
            constructor_assignments = []
            for field in fields:
                java_type = self._get_java_type(field)
                constructor_params.append(f"{java_type} {field.name}")
                constructor_assignments.append(
                    f"        this.{field.name} = {field.name};"
                )

            lines.append(f"    public {class_name}({', '.join(constructor_params)}) {{")
            lines.extend(constructor_assignments)
            lines.append("    }")

        # Generate getters and setters
        lines.extend(["", "    // Getters and Setters"])
        for field in fields:
            getter_setter = self._generate_getter_setter(field)
            lines.extend([""] + getter_setter)

        lines.append("}")

        return "\n".join(lines)

    def _generate_field_definition(self, field: USRField) -> list[str]:
        """Generate Java field definition with Jackson annotations"""
        lines = []

        if field.description:
            lines.extend(["    /**", f"     * {field.description}", "     */"])

        # Jackson annotations
        annotations = [f'    @JsonProperty("{field.name}")']

        if field.format_type == "date-time":
            annotations.append(
                "    @JsonFormat(shape = JsonFormat.Shape.STRING, pattern = \"yyyy-MM-dd'T'HH:mm:ss.SSSZ\")"
            )
        elif field.format_type == "date":
            annotations.append(
                '    @JsonFormat(shape = JsonFormat.Shape.STRING, pattern = "yyyy-MM-dd")'
            )

        # Validation annotations
        if not field.optional and field.default is None:
            annotations.append("    @NotNull")

        if field.type == FieldType.STRING:
            validation_parts = []
            if field.min_length is not None:
                validation_parts.append(f"min = {field.min_length}")
            if field.max_length is not None:
                validation_parts.append(f"max = {field.max_length}")
            if validation_parts:
                annotations.append(f"    @Size({', '.join(validation_parts)})")

            if field.format_type == "email":
                annotations.append("    @Email")

        elif field.type in [FieldType.INTEGER, FieldType.FLOAT]:
            if field.min_value is not None:
                # For integer fields, use the value directly
                # For float fields, convert to int for @Min annotation compatibility
                min_val = (
                    int(field.min_value)
                    if field.type == FieldType.FLOAT
                    else field.min_value
                )
                annotations.append(f"    @Min(value = {min_val})")
            if field.max_value is not None:
                # Same conversion for max value
                max_val = (
                    int(field.max_value)
                    if field.type == FieldType.FLOAT
                    else field.max_value
                )
                annotations.append(f"    @Max({max_val})")

        lines.extend(annotations)

        # Field declaration
        java_type = self._get_java_type(field)
        field_declaration = f"    private {java_type} {field.name};"
        lines.append(field_declaration)

        return lines

    def _generate_getter_setter(self, field: USRField) -> list[str]:
        """Generate getter and setter methods"""
        lines = []
        java_type = self._get_java_type(field)
        capitalized_name = field.name.capitalize()

        # Getter
        lines.extend(
            [
                f"    public {java_type} get{capitalized_name}() {{",
                f"        return {field.name};",
                "    }",
            ]
        )

        # Setter
        lines.extend(
            [
                "",
                f"    public void set{capitalized_name}({java_type} {field.name}) {{",
                f"        this.{field.name} = {field.name};",
                "    }",
            ]
        )

        return lines

    def _get_java_type(self, field: USRField) -> str:
        """Get the Java type for a field"""

        base_type = ""

        if field.type == FieldType.STRING:
            base_type = "String"

        elif field.type == FieldType.INTEGER:
            # Use Integer for nullable, int for primitives
            base_type = "Integer" if field.optional else "int"

        elif field.type == FieldType.FLOAT:
            base_type = "Double" if field.optional else "double"

        elif field.type == FieldType.BOOLEAN:
            base_type = "Boolean" if field.optional else "boolean"

        elif field.type == FieldType.DATETIME:
            base_type = "Instant"  # or LocalDateTime

        elif field.type == FieldType.DATE:
            base_type = "LocalDate"

        elif field.type == FieldType.UUID:
            base_type = "UUID"

        elif field.type == FieldType.DECIMAL:
            base_type = "BigDecimal"

        elif field.type == FieldType.LIST:
            if field.inner_type:
                inner_type = self._get_java_type(field.inner_type)
                base_type = f"List<{inner_type}>"
            else:
                base_type = "List<Object>"

        elif field.type == FieldType.DICT:
            base_type = "Map<String, Object>"

        elif field.type == FieldType.NESTED_SCHEMA:
            base_type = field.nested_schema

        else:
            base_type = "Object"

        return base_type

    def _get_required_imports(self, schema: USRSchema) -> list[str]:
        """Get required import statements"""
        imports = set()

        # Jackson imports
        imports.add("import com.fasterxml.jackson.annotation.JsonInclude;")
        imports.add("import com.fasterxml.jackson.annotation.JsonProperty;")
        imports.add("import com.fasterxml.jackson.annotation.JsonPropertyOrder;")

        # Check if we need format annotations
        has_date_fields = any(
            f.type in [FieldType.DATE, FieldType.DATETIME] for f in schema.fields
        )
        if has_date_fields:
            imports.add("import com.fasterxml.jackson.annotation.JsonFormat;")

        # Validation imports
        imports.add("import javax.validation.constraints.NotNull;")

        has_string_validation = any(
            f.type == FieldType.STRING and (f.min_length or f.max_length)
            for f in schema.fields
        )
        if has_string_validation:
            imports.add("import javax.validation.constraints.Size;")

        has_email_validation = any(f.format_type == "email" for f in schema.fields)
        if has_email_validation:
            imports.add("import javax.validation.constraints.Email;")

        has_numeric_validation = any(
            f.type in [FieldType.INTEGER, FieldType.FLOAT]
            and (f.min_value or f.max_value)
            for f in schema.fields
        )
        if has_numeric_validation:
            imports.add("import javax.validation.constraints.Min;")
            imports.add("import javax.validation.constraints.Max;")

        # Java type imports
        def check_field_imports(field: USRField):
            if field.type == FieldType.DATETIME:
                imports.add("import java.time.Instant;")
            elif field.type == FieldType.DATE:
                imports.add("import java.time.LocalDate;")
            elif field.type == FieldType.UUID:
                imports.add("import java.util.UUID;")
            elif field.type == FieldType.DECIMAL:
                imports.add("import java.math.BigDecimal;")
            elif field.type == FieldType.LIST:
                imports.add("import java.util.List;")
                if field.inner_type:
                    check_field_imports(field.inner_type)
            elif field.type == FieldType.DICT:
                imports.add("import java.util.Map;")

        for field in schema.fields:
            check_field_imports(field)

        return sorted(imports)

    def _variant_to_class_name(self, schema_name: str, variant_name: str) -> str:
        """Convert variant name to PascalCase class name"""
        parts = variant_name.split("_")
        variant_pascal = "".join(word.capitalize() for word in parts)
        return f"{schema_name}{variant_pascal}"
