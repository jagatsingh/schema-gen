"""Parser to convert schema_gen Schema classes to USR format"""

import logging
import warnings
from enum import Enum

from ..core.schema import SchemaRegistry
from ..core.usr import FieldType, TypeMapper, USREnum, USRField, USRSchema

logger = logging.getLogger(__name__)


class SchemaParser:
    """Parses schema_gen Schema classes into USR format"""

    def __init__(self):
        self.type_mapper = TypeMapper()

    def parse_schema(self, schema_class: type) -> USRSchema:
        """Convert a schema_gen Schema class to USR format

        Args:
            schema_class: Class decorated with @Schema

        Returns:
            USRSchema representation
        """
        if not hasattr(schema_class, "_schema_fields"):
            raise ValueError(
                f"Class {schema_class.__name__} is not a valid Schema. Use @Schema decorator."
            )

        # Create USR fields from schema fields
        usr_fields = []
        for field_name, field_data in schema_class._schema_fields.items():
            usr_field = self.type_mapper.create_usr_field_from_python(
                name=field_name,
                python_type=field_data["type"],
                field_info=field_data["field_info"],
            )
            usr_fields.append(usr_field)

        # Discover enum types referenced by fields.
        #
        # Enums can appear at several nesting depths:
        #   Enum                                          -> top-level
        #   Optional[Enum] / Enum | None                  -> inner_type
        #   list[Enum] / set[Enum] / frozenset[Enum]      -> inner_type
        #   Optional[list[Enum]]                          -> inner_type.inner_type
        #   Union[Enum, ...]                              -> union_types
        #   dict[str, Enum]                               -> not currently modeled in USR
        #
        # We walk the field tree recursively so that an enum referenced at any
        # depth contributes its members to ``schema.enums``. Previously the
        # discovery pass only looked at ``usr_field.python_type`` for top-level
        # enum fields, and for ``Optional[Enum]`` that attribute is the wrapped
        # ``Optional[...]`` form rather than the enum class itself, so enum
        # member extraction silently produced an empty list (issue #15).
        seen_enums: dict[str, USREnum] = {}

        def _collect_enum(f: USRField) -> None:
            if f is None:
                return
            if (
                f.type == FieldType.ENUM
                and f.enum_name
                and f.enum_name not in seen_enums
            ):
                pt = f.python_type
                # ``python_type`` is the unwrapped enum class for top-level
                # enum fields and for the recursively-created inner_type of an
                # ``Optional[Enum]`` / ``list[Enum]``. For the *outer* field of
                # an Optional it is the wrapper (e.g. ``Optional[Enum]``), in
                # which case we skip and let recursion into ``inner_type``
                # populate the entry.
                if isinstance(pt, type) and issubclass(pt, Enum):
                    seen_enums[f.enum_name] = USREnum(
                        name=f.enum_name,
                        values=[(e.name, e.value) for e in pt],
                    )
            # Recurse through wrappers: Optional[T], list[T], set[T], Union[...].
            if f.inner_type is not None:
                _collect_enum(f.inner_type)
            for ut in f.union_types:
                _collect_enum(ut)

        for usr_field in usr_fields:
            _collect_enum(usr_field)

        enums = list(seen_enums.values())

        # Extract variants if defined
        variants = {}
        if hasattr(schema_class, "Variants"):
            variants_class = schema_class.Variants
            for attr_name in dir(variants_class):
                if not attr_name.startswith("_"):
                    attr_value = getattr(variants_class, attr_name)
                    if isinstance(attr_value, list):
                        variants[attr_name] = attr_value

        # Extract custom code if available
        custom_code = getattr(schema_class, "_custom_code", {})

        usr_schema = USRSchema(
            name=schema_class.__name__,
            fields=usr_fields,
            description=schema_class.__doc__,
            enums=enums,
            variants=variants,
            custom_code=custom_code,
            metadata={},
        )

        # Validate the parsed schema
        issues = usr_schema.validate()
        errors = [i for i in issues if i.severity == "error"]
        warns = [i for i in issues if i.severity == "warning"]
        infos = [i for i in issues if i.severity == "info"]

        for info in infos:
            logger.info("Schema '%s': %s", usr_schema.name, info.message)

        for warn in warns:
            warnings.warn(
                f"Schema '{usr_schema.name}': {warn.message}",
                stacklevel=2,
            )

        if errors:
            error_msgs = [f"  - {e.message}" for e in errors]
            raise ValueError(
                f"Schema '{usr_schema.name}' has validation errors:\n"
                + "\n".join(error_msgs)
            )

        return usr_schema

    def parse_all_schemas(self) -> list[USRSchema]:
        """Parse all registered schemas to USR format

        Returns:
            List of USRSchema objects for all registered schemas

        Raises:
            ValueError: If any schema has validation errors
        """
        usr_schemas = []
        all_errors = []
        for _schema_name, schema_class in SchemaRegistry.get_all_schemas().items():
            try:
                usr_schema = self.parse_schema(schema_class)
                usr_schemas.append(usr_schema)
            except ValueError as e:
                all_errors.append(str(e))

        if all_errors:
            raise ValueError("Schema validation failed:\n" + "\n".join(all_errors))

        return usr_schemas

    def parse_schema_by_name(self, schema_name: str) -> USRSchema:
        """Parse a specific schema by name

        Args:
            schema_name: Name of the schema to parse

        Returns:
            USRSchema representation

        Raises:
            ValueError: If schema not found
        """
        schema_class = SchemaRegistry.get_schema(schema_name)
        if schema_class is None:
            raise ValueError(f"Schema '{schema_name}' not found in registry")
        return self.parse_schema(schema_class)
