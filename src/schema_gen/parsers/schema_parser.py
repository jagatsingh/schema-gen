"""Parser to convert schema_gen Schema classes to USR format"""

from ..core.schema import SchemaRegistry
from ..core.usr import TypeMapper, USRSchema


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

        return USRSchema(
            name=schema_class.__name__,
            fields=usr_fields,
            description=schema_class.__doc__,
            variants=variants,
            custom_code=custom_code,
            metadata={},
        )

    def parse_all_schemas(self) -> list[USRSchema]:
        """Parse all registered schemas to USR format

        Returns:
            List of USRSchema objects for all registered schemas
        """
        usr_schemas = []
        for _schema_name, schema_class in SchemaRegistry.get_all_schemas().items():
            usr_schema = self.parse_schema(schema_class)
            usr_schemas.append(usr_schema)
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
