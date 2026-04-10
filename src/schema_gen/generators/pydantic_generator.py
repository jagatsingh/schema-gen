"""Generator to create Pydantic models from USR schemas"""

from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from jinja2 import Template

from ..core.config import Config
from ..core.usr import FieldType, USREnum, USRField, USRSchema
from .base import BaseGenerator

#: Pydantic ``ConfigDict`` keys honored by ``Config.pydantic``. Any other
#: keys are ignored (and must NOT cause ``_needs_config`` to return True,
#: otherwise an unrelated schema would grow a spurious ``model_config``
#: block).
_SUPPORTED_PYDANTIC_CONFIG_KEYS: tuple[str, ...] = (
    "extra",
    "validate_assignment",
    "frozen",
    "strict",
    "str_strip_whitespace",
    "populate_by_name",
)


class PydanticGenerator(BaseGenerator):
    """Generates Pydantic models from USR schemas"""

    def __init__(self, config: Config | None = None) -> None:
        super().__init__(config=config)
        self.template = Template(self._get_template())
        #: Set of enum names that have been extracted to ``_enums.py``.
        #: Populated by ``get_extra_files()`` before ``generate_file()``
        #: is called so that per-schema files can import instead of
        #: re-declaring the enum inline.
        self._shared_enum_names: set[str] = set()

    def _get_model_config_line(self) -> str:
        """Build the ``model_config = ConfigDict(...)`` line.

        Honors keys in ``Config.pydantic`` such as ``extra``,
        ``validate_assignment``, ``frozen``, ``strict``,
        ``str_strip_whitespace`` and ``populate_by_name``. When no
        Pydantic config is supplied, falls back to the historical
        hardcoded output (``from_attributes=True`` only) so existing
        callers see no change.
        """
        cfg_items: list[str] = ["from_attributes=True"]
        pyd_cfg: dict[str, Any] = {}
        if self.config is not None and getattr(self.config, "pydantic", None):
            pyd_cfg = self.config.pydantic
        for key in _SUPPORTED_PYDANTIC_CONFIG_KEYS:
            if key in pyd_cfg:
                val = pyd_cfg[key]
                if isinstance(val, str):
                    # Use Python repr so embedded quotes, backslashes, and
                    # newlines round-trip as valid source code.
                    cfg_items.append(f"{key}={val!r}")
                else:
                    cfg_items.append(f"{key}={val}")
        return f"    model_config = ConfigDict({', '.join(cfg_items)})"

    @property
    def file_extension(self) -> str:
        return ".py"

    @property
    def generates_index_file(self) -> bool:
        return True

    def get_schema_filename(self, schema: USRSchema) -> str:
        return f"{schema.name.lower()}_models.py"

    def get_extra_files(
        self, schemas: list[USRSchema], output_dir: Path
    ) -> dict[str, str]:
        """Emit ``_enums.py`` containing all enums across all schemas.

        Enums are de-duplicated by name so that multiple schemas referencing
        the same enum (e.g. ``OptionType``) share a single definition.
        Per-schema files import from ``._enums`` instead of declaring enums
        inline, which prevents duplicate class definitions across modules.
        """
        # Collect unique enums across all schemas (first-seen wins).
        seen: dict[str, USREnum] = {}
        for schema in schemas:
            for enum_def in schema.enums:
                if enum_def.name not in seen:
                    seen[enum_def.name] = enum_def
                elif enum_def.values != seen[enum_def.name].values:
                    raise ValueError(
                        f"Enum name collision: '{enum_def.name}' is defined "
                        f"with different members in multiple schemas. "
                        f"First: {seen[enum_def.name].values}, "
                        f"second: {enum_def.values}"
                    )

        if not seen:
            self._shared_enum_names = set()
            return {}

        self._shared_enum_names = set(seen.keys())

        # Build _enums.py content
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")
        lines = [
            '"""',
            "AUTO-GENERATED FILE - DO NOT EDIT MANUALLY",
            "Shared enum definitions for generated Pydantic models",
            f"Generated at: {timestamp}",
            "Generator: schema-gen Pydantic generator",
            "",
            "To regenerate this file, run:",
            "    schema-gen generate --target pydantic",
            "",
            "Changes to this file will be overwritten.",
            '"""',
            "",
            "from enum import Enum",
            "",
        ]

        for enum_def in seen.values():
            lines.append("")
            if enum_def.value_type is not None:
                mixin_name = enum_def.value_type.__name__
                lines.append(f"class {enum_def.name}({mixin_name}, Enum):")
            else:
                lines.append(f"class {enum_def.name}(Enum):")
            for member_name, member_value in enum_def.values:
                if isinstance(member_value, str):
                    lines.append(f'    {member_name} = "{member_value}"')
                else:
                    lines.append(f"    {member_name} = {member_value}")

            # Inject custom methods from PydanticMeta
            enum_meta = (enum_def.custom_code or {}).get("pydantic", {}) or {}
            methods_src = (enum_meta.get("methods") or "").strip()
            if methods_src:
                lines.append("")
                for method_line in methods_src.splitlines():
                    if method_line.strip():
                        lines.append(f"    {method_line}")
                    else:
                        lines.append("")

        lines.append("")
        return {"_enums.py": "\n".join(lines) + "\n"}

    def generate_index(self, schemas: list[USRSchema], output_dir: Path) -> str | None:
        """Generate __init__.py content for the pydantic package."""
        lines = ['"""Generated Pydantic models"""\n']

        # Import shared enums from _enums module (de-duplicated)
        if self._shared_enum_names:
            sorted_enums = sorted(self._shared_enum_names)
            lines.append(f"from ._enums import {', '.join(sorted_enums)}")

        for schema in schemas:
            # Enum classes now come from _enums, so only import models
            base_class = schema.name
            variant_classes = [
                self._variant_to_class_name(schema.name, v) for v in schema.variants
            ]
            model_classes = [base_class] + variant_classes
            lines.append(
                f"from .{schema.name.lower()}_models import {', '.join(model_classes)}"
            )

        # Build __all__ with enums first, then models
        all_names: list[str] = sorted(self._shared_enum_names)
        for schema in schemas:
            base_class = schema.name
            variant_classes = [
                self._variant_to_class_name(schema.name, v) for v in schema.variants
            ]
            all_names.extend([base_class] + variant_classes)

        lines.append("\n__all__ = [")
        for name in all_names:
            lines.append(f'    "{name}",')
        lines.append("]")

        return "\n".join(lines) + "\n"

    def generate_model(self, schema: USRSchema, variant: str | None = None) -> str:
        """Generate a Pydantic model for a schema variant

        Args:
            schema: USR schema to generate from
            variant: Specific variant to generate, or None for full schema

        Returns:
            Generated Pydantic model code
        """
        fields = schema.get_variant_fields(variant) if variant else schema.fields

        # Determine the model name
        model_name = schema.name
        if variant:
            model_name = self._variant_to_class_name(schema.name, variant)

        # Generate field definitions
        field_definitions = []
        imports = {"pydantic", "typing"}

        for field in fields:
            field_def, field_imports = self._generate_field_definition(field)
            field_definitions.append(field_def)
            imports.update(field_imports)

        return self.template.render(
            model_name=model_name,
            schema_name=schema.name,
            variant_name=variant,
            description=schema.description,
            imports=sorted(imports),
            fields=field_definitions,
            has_config=self._needs_config(fields),
            model_config_line=self._get_model_config_line(),
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC"),
        )

    def generate_all_variants(self, schema: USRSchema) -> dict[str, str]:
        """Generate all variants for a schema

        Args:
            schema: USR schema to generate variants for

        Returns:
            Dictionary mapping variant names to generated code
        """
        variants = {}

        # Generate base model (all fields)
        variants["base"] = self.generate_model(schema)

        # Generate specific variants
        for variant_name in schema.variants:
            variants[variant_name] = self.generate_model(schema, variant_name)

        return variants

    def generate_file(self, schema: USRSchema) -> str:
        """Generate a complete file with all variants for a schema

        Args:
            schema: USR schema to generate from

        Returns:
            Complete file content with all models
        """
        # Collect all imports needed
        all_imports = {"pydantic"}
        all_fields = []
        all_models = []

        # Generate base model
        base_fields = schema.fields
        for field in base_fields:
            field_def, field_imports = self._generate_field_definition(field)
            all_fields.append(field_def)
            all_imports.update(field_imports)

        # Extract pydantic-specific custom code
        pydantic_custom_code = schema.custom_code.get("pydantic", {})

        base_model = self._generate_single_model(
            schema.name,
            schema.description,
            all_fields,
            self._needs_config(base_fields),
            is_base_model=True,
            custom_code=pydantic_custom_code,
        )
        all_models.append(base_model)

        # Generate variants (without custom code)
        for variant_name in schema.variants:
            variant_fields = schema.get_variant_fields(variant_name)
            variant_field_defs = []

            for field in variant_fields:
                field_def, field_imports = self._generate_field_definition(field)
                variant_field_defs.append(field_def)
                all_imports.update(field_imports)

            variant_model_name = self._variant_to_class_name(schema.name, variant_name)
            variant_model = self._generate_single_model(
                variant_model_name,
                schema.description,
                variant_field_defs,
                self._needs_config(variant_fields),
                is_base_model=False,  # Variants don't get custom code
            )
            all_models.append(variant_model)

        # Check for self-referencing fields
        has_self_ref = bool(schema.get_self_referencing_fields())

        # Generate complete file
        return self._generate_complete_file(
            schema.name,
            all_imports,
            all_models,
            pydantic_custom_code,
            schema.enums,
            self_ref_model=schema.name if has_self_ref else None,
        )

    def _variant_to_class_name(self, schema_name: str, variant_name: str) -> str:
        """Convert variant name to PascalCase class name"""
        # Convert snake_case to PascalCase
        parts = variant_name.split("_")
        variant_pascal = "".join(word.capitalize() for word in parts)
        return f"{schema_name}{variant_pascal}"

    def _generate_field_definition(self, field: USRField) -> tuple[str, set[str]]:
        """Generate a single field definition

        Returns:
            Tuple of (field_definition_code, required_imports)
        """
        imports = set()

        # Generate type annotation
        type_annotation = self._get_pydantic_type(field, imports)

        # Discriminated union: wrap in Annotated[Union[...], Field(discriminator="...")]
        # so Pydantic v2 can deserialize tagged payloads correctly.
        if field.discriminator and field.union_types:
            union_types = [
                self._get_pydantic_type(ut, imports) for ut in field.union_types
            ]
            imports.add("typing")
            imports.add("typing.Annotated")
            imports.add("pydantic.Field")
            type_annotation = (
                f"Annotated[Union[{', '.join(union_types)}], "
                f'Field(discriminator="{field.discriminator}")]'
            )

        # Generate Field() definition
        field_params = []

        # Default value
        if field.default is not None:
            if isinstance(field.default, Enum):
                field_params.append(
                    f"default={field.default.__class__.__name__}.{field.default.name}"
                )
            elif isinstance(field.default, str):
                field_params.append(f'default="{field.default}"')
            else:
                field_params.append(f"default={field.default}")
        elif field.default_factory is not None:
            factory_name = getattr(field.default_factory, "__name__", None)
            if not factory_name or not factory_name.isidentifier():
                raise ValueError(
                    f"Field '{field.name}': default_factory must be a named callable "
                    f"(e.g. list, dict), got {field.default_factory!r}"
                )
            field_params.append(f"default_factory={factory_name}")
        elif field.optional and not field_params:
            field_params.append("default=None")
        elif not field.optional and not field_params:
            field_params.append("...")  # Required field marker

        # Validation parameters
        if field.min_length is not None:
            field_params.append(f"min_length={field.min_length}")
        if field.max_length is not None:
            field_params.append(f"max_length={field.max_length}")
        if field.min_value is not None:
            field_params.append(f"ge={field.min_value}")  # greater or equal
        if field.max_value is not None:
            field_params.append(f"le={field.max_value}")  # less or equal
        if field.regex_pattern:
            field_params.append(f'pattern=r"{field.regex_pattern}"')

        # Description
        if field.description:
            field_params.append(f'description="{field.description}"')

        # Pydantic-specific configurations
        pydantic_config = field.target_config.get("pydantic", {})
        for key, value in pydantic_config.items():
            if isinstance(value, str):
                field_params.append(f'{key}="{value}"')
            else:
                field_params.append(f"{key}={value}")

        # Build field definition
        if field_params:
            imports.add("pydantic.Field")
            field_def = f"    {field.name}: {type_annotation} = Field({', '.join(field_params)})"
        else:
            field_def = f"    {field.name}: {type_annotation}"

        return field_def, imports

    def _get_pydantic_type(self, field: USRField, imports: set) -> str:
        """Get the Pydantic type annotation for a field"""

        # For optional fields, get the base type from inner_type first
        if field.optional and field.inner_type:
            inner_type = self._get_pydantic_type(field.inner_type, imports)
            imports.add("typing")
            return f"Optional[{inner_type}]"

        base_type = ""

        if field.type == FieldType.STRING:
            if field.format_type == "email":
                imports.add("pydantic.EmailStr")
                base_type = "EmailStr"
            else:
                base_type = "str"

        elif field.type == FieldType.INTEGER:
            base_type = "int"

        elif field.type == FieldType.FLOAT:
            base_type = "float"

        elif field.type == FieldType.BOOLEAN:
            base_type = "bool"

        elif field.type == FieldType.DATETIME:
            imports.add("datetime.datetime")
            base_type = "datetime"

        elif field.type == FieldType.DATE:
            imports.add("datetime.date")
            base_type = "date"

        elif field.type == FieldType.UUID:
            imports.add("uuid.UUID")
            base_type = "UUID"

        elif field.type == FieldType.DECIMAL:
            imports.add("decimal.Decimal")
            base_type = "Decimal"

        elif field.type == FieldType.LIST:
            if field.inner_type:
                inner_type = self._get_pydantic_type(field.inner_type, imports)
                base_type = f"list[{inner_type}]"
            else:
                imports.add("typing")
                base_type = "list[Any]"

        elif field.type == FieldType.SET:
            if field.inner_type:
                inner_type = self._get_pydantic_type(field.inner_type, imports)
                base_type = f"set[{inner_type}]"
            else:
                imports.add("typing")
                base_type = "set[Any]"

        elif field.type == FieldType.FROZENSET:
            if field.inner_type:
                inner_type = self._get_pydantic_type(field.inner_type, imports)
                base_type = f"frozenset[{inner_type}]"
            else:
                imports.add("typing")
                base_type = "frozenset[Any]"

        elif field.type == FieldType.DICT:
            imports.add("typing")
            base_type = "dict[str, Any]"

        elif field.type == FieldType.UNION:
            imports.add("typing")
            if field.union_types:
                union_types = [
                    self._get_pydantic_type(ut, imports) for ut in field.union_types
                ]
                base_type = f"Union[{', '.join(union_types)}]"
            else:
                base_type = "Any"

        elif field.type == FieldType.LITERAL:
            if field.literal_values:
                values = [
                    f'"{v}"' if isinstance(v, str) else str(v)
                    for v in field.literal_values
                ]
                imports.add("typing.Literal")
                base_type = f"Literal[{', '.join(values)}]"
            else:
                base_type = "str"

        elif field.type == FieldType.TUPLE:
            if field.union_types:
                inner_types = [
                    self._get_pydantic_type(ut, imports) for ut in field.union_types
                ]
                base_type = f"tuple[{', '.join(inner_types)}]"
            else:
                base_type = "tuple[()]"

        elif field.type == FieldType.ENUM:
            base_type = field.enum_name or "str"

        elif field.type == FieldType.NESTED_SCHEMA:
            # For nested schemas, use forward reference
            base_type = f'"{field.nested_schema}"'

        else:
            imports.add("typing")
            base_type = "Any"

        return base_type

    def _needs_config(self, fields: list[USRField]) -> bool:
        """Check if the model needs a ``model_config`` block.

        Emits a ``model_config = ConfigDict(...)`` block when either:

        1. Any field has a database relationship (the historical reason
           ``from_attributes=True`` was needed), OR
        2. ``Config.pydantic`` contains at least one key that this
           generator actually honors (see ``_SUPPORTED_PYDANTIC_CONFIG_KEYS``).

        A dict containing only unknown keys must NOT trigger emission —
        otherwise the resulting ``model_config`` block would only contain
        ``from_attributes=True`` for no reason, surprising users who
        passed an unrelated setting.
        """
        if any(field.relationship is not None for field in fields):
            return True
        if self.config is None:
            return False
        pyd_cfg = getattr(self.config, "pydantic", None) or {}
        return any(key in pyd_cfg for key in _SUPPORTED_PYDANTIC_CONFIG_KEYS)

    def _generate_single_model(
        self,
        model_name: str,
        description: str,
        field_defs: list[str],
        has_config: bool,
        is_base_model: bool = False,
        custom_code: dict[str, Any] = None,
    ) -> str:
        """Generate a single model class definition"""
        lines = [f"class {model_name}(BaseModel):"]

        if description:
            lines.append(f'    """{description}"""')

        # Add fields
        for field_def in field_defs:
            lines.append(field_def)

        # Add custom code only to base model
        if is_base_model and custom_code:
            if custom_code.get("raw_code"):
                lines.append("")
                lines.append("    # Custom validators")
                # Indent the custom code properly - ensure all lines have proper indentation
                raw_code_lines = custom_code["raw_code"].strip().split("\n")
                for code_line in raw_code_lines:
                    if code_line.strip():  # Skip empty lines
                        # If line already starts with proper indentation, use as is
                        # Otherwise, add 4 spaces for class method indentation
                        if code_line.startswith("    "):
                            lines.append(code_line)
                        else:
                            lines.append("    " + code_line)
                    else:
                        lines.append("")

            if custom_code.get("methods"):
                lines.append("")
                lines.append("    # Custom methods")
                # Indent the custom methods properly - ensure all lines have proper indentation
                methods_lines = custom_code["methods"].strip().split("\n")
                for method_line in methods_lines:
                    if method_line.strip():  # Skip empty lines
                        # If line already starts with proper indentation, use as is
                        # Otherwise, add 4 spaces for class method indentation
                        if method_line.startswith("    "):
                            lines.append(method_line)
                        else:
                            lines.append("    " + method_line)
                    else:
                        lines.append("")

        # Add config if needed
        if has_config:
            lines.append("")
            lines.append(self._get_model_config_line())

        return "\n".join(lines)

    def _generate_complete_file(
        self,
        schema_name: str,
        imports: set,
        models: list[str],
        custom_code: dict[str, Any] = None,
        enums: list = None,
        self_ref_model: str | None = None,
    ) -> str:
        """Generate complete file with header, imports, and all models"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")
        custom_code = custom_code or {}
        enums = enums or []

        lines = [
            '"""',
            "AUTO-GENERATED FILE - DO NOT EDIT MANUALLY",
            f"Generated from: {schema_name}",
            f"Generated at: {timestamp}",
            "Generator: schema-gen Pydantic generator",
            "",
            "To regenerate this file, run:",
            "    schema-gen generate --target pydantic",
            "",
            "Changes to this file will be overwritten.",
            '"""',
            "",
        ]

        # Determine which enums to import vs inline.
        # When get_extra_files() has run (multi-schema generation), enums
        # live in _enums.py and we import them. For single-schema usage
        # (e.g. generate_file() called directly in tests without prior
        # get_extra_files()), we fall back to inline declaration.
        enums_to_import = [e for e in enums if e.name in self._shared_enum_names]
        enums_to_inline = [e for e in enums if e.name not in self._shared_enum_names]

        # Add enum import if we have inline enums
        if enums_to_inline:
            lines.append("from enum import Enum")

        # Add import from _enums module for shared enums
        if enums_to_import:
            enum_names = sorted(e.name for e in enums_to_import)
            lines.append(f"from ._enums import {', '.join(enum_names)}")

        # Add custom imports from Meta.imports
        custom_imports = custom_code.get("imports", [])

        # Add imports
        pydantic_imports = ["BaseModel", "ConfigDict"]
        if "pydantic.Field" in imports:
            pydantic_imports.append("Field")
        lines.append(f"from pydantic import {', '.join(pydantic_imports)}")

        if "pydantic.EmailStr" in imports:
            lines.append("from pydantic import EmailStr")

        # Add typing imports
        typing_imports = []
        other_imports = []

        for imp in sorted(imports):
            if imp.startswith("datetime"):
                other_imports.append(f"from datetime import {imp.split('.')[-1]}")
            elif imp.startswith("uuid"):
                other_imports.append("import uuid")
            elif imp.startswith("decimal"):
                other_imports.append("from decimal import Decimal")
            elif imp == "typing":
                typing_imports.extend(["Optional", "Any", "Union"])
            elif imp == "typing.Literal":
                typing_imports.append("Literal")
            elif imp == "typing.Annotated":
                typing_imports.append("Annotated")

        # Add typing import if needed
        if typing_imports:
            lines.append(f"from typing import {', '.join(sorted(set(typing_imports)))}")

        # Add other imports
        for imp_line in other_imports:
            lines.append(imp_line)

        # Add custom imports
        for custom_import in custom_imports:
            lines.append(custom_import)

        lines.append("")

        # Generate inline enum classes before models (only enums NOT in _enums.py)
        for enum_def in enums_to_inline:
            lines.append("")
            # Preserve the mixin base type (str, int) when the source enum
            # inherits from it — e.g. ``class Foo(str, Enum):``.
            if enum_def.value_type is not None:
                mixin_name = enum_def.value_type.__name__
                lines.append(f"class {enum_def.name}({mixin_name}, Enum):")
            else:
                lines.append(f"class {enum_def.name}(Enum):")
            for member_name, member_value in enum_def.values:
                if isinstance(member_value, str):
                    lines.append(f'    {member_name} = "{member_value}"')
                else:
                    lines.append(f"    {member_name} = {member_value}")
            # Inject PydanticMeta.methods on the enum class body. Users
            # attach domain methods (is_terminal, has_trailing, ...)
            # directly on the Python Enum and we preserve them verbatim
            # in the generated Pydantic enum.
            enum_meta = (enum_def.custom_code or {}).get("pydantic", {}) or {}
            methods_src = (enum_meta.get("methods") or "").strip()
            if methods_src:
                lines.append("")
                for method_line in methods_src.splitlines():
                    if method_line.strip():
                        lines.append(f"    {method_line}")
                    else:
                        lines.append("")

        lines.append("")

        # Add models
        for i, model in enumerate(models):
            if i > 0:
                lines.append("")
                lines.append("")
            lines.append(model)

        # Add model_rebuild() for self-referential models to resolve forward references
        if self_ref_model:
            lines.append("")
            lines.append("")
            lines.append(
                "# Rebuild model to resolve self-referential forward references"
            )
            lines.append(f"{self_ref_model}.model_rebuild()")

        return "\n".join(lines)

    def _get_template(self) -> str:
        """Get the Jinja2 template for Pydantic models"""
        return '''"""
AUTO-GENERATED FILE - DO NOT EDIT MANUALLY
Generated from: {{ schema_name }}{% if variant_name %} ({{ variant_name }} variant){% endif %}
Generated at: {{ timestamp }}
Generator: schema-gen Pydantic generator

To regenerate this file, run:
    schema-gen generate --target pydantic

Changes to this file will be overwritten.
"""

from pydantic import BaseModel, ConfigDict{% if 'pydantic.Field' in imports %}, Field{% endif %}
{% if 'pydantic.EmailStr' in imports %}from pydantic import EmailStr{% endif %}
{% for imp in imports %}
{%- if imp.startswith('datetime') %}
from datetime import {{ imp.split('.')[-1] }}
{%- elif imp.startswith('uuid') %}
import uuid
{%- elif imp.startswith('decimal') %}
from decimal import Decimal
{%- elif imp == 'typing' %}
from typing import Optional, Any, Union
{%- elif imp == 'typing.Literal' %}
from typing import Literal
{%- endif %}
{%- endfor %}


class {{ model_name }}(BaseModel):
{%- if description %}
    """{{ description }}"""
{%- endif %}
{% for field_def in fields %}
{{ field_def }}
{%- endfor %}
{%- if has_config %}

{{ model_config_line }}
{%- endif %}'''
