"""Core schema definition API for schema_gen"""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, get_type_hints


@dataclass
class FieldInfo:
    """Information about a schema field"""

    # Core field properties
    default: Any = None
    default_factory: Callable | None = None
    description: str | None = None

    # Type constraints
    min_length: int | None = None
    max_length: int | None = None
    min_value: float | None = None
    max_value: float | None = None
    regex: str | None = None
    format: str | None = None  # email, uri, uuid, etc.

    # Database attributes
    primary_key: bool = False
    unique: bool = False
    index: bool = False
    foreign_key: str | None = None
    auto_increment: bool = False
    auto_now_add: bool = False
    auto_now: bool = False

    # Relationship attributes
    relationship: str | None = None  # one_to_many, many_to_one, many_to_many
    back_populates: str | None = None
    cascade: str | None = None
    through_table: str | None = None

    # Generation control
    exclude_from: list[str] = field(default_factory=list)
    include_only: list[str] = field(default_factory=list)

    # Target-specific overrides
    pydantic: dict[str, Any] = field(default_factory=dict)
    sqlalchemy: dict[str, Any] = field(default_factory=dict)
    pathway: dict[str, Any] = field(default_factory=dict)

    # Additional metadata
    metadata: dict[str, Any] = field(default_factory=dict)


def Field(
    default: Any = None,
    *,
    default_factory: Callable | None = None,
    description: str | None = None,
    min_length: int | None = None,
    max_length: int | None = None,
    min_value: float | None = None,
    max_value: float | None = None,
    regex: str | None = None,
    format: str | None = None,
    primary_key: bool = False,
    unique: bool = False,
    index: bool = False,
    foreign_key: str | None = None,
    auto_increment: bool = False,
    auto_now_add: bool = False,
    auto_now: bool = False,
    relationship: str | None = None,
    back_populates: str | None = None,
    cascade: str | None = None,
    through_table: str | None = None,
    exclude_from: list[str] | None = None,
    include_only: list[str] | None = None,
    pydantic: dict[str, Any] | None = None,
    sqlalchemy: dict[str, Any] | None = None,
    pathway: dict[str, Any] | None = None,
    **metadata: Any,
) -> FieldInfo:
    """Create a field definition for a schema

    Args:
        default: Default value for the field
        default_factory: Factory function for default values
        description: Human-readable description
        min_length/max_length: String length constraints
        min_value/max_value: Numeric value constraints
        regex: Regular expression validation pattern
        format: Standard format (email, uri, uuid, etc.)
        primary_key: Whether field is a primary key
        unique: Whether field values must be unique
        index: Whether to create database index
        foreign_key: Reference to another table's field
        auto_increment: Auto-increment for primary keys
        auto_now_add: Set timestamp on creation
        auto_now: Update timestamp on every save
        relationship: Type of relationship (one_to_many, etc.)
        back_populates: Name of reverse relationship
        cascade: SQLAlchemy cascade options
        through_table: Many-to-many join table name
        exclude_from: List of variants to exclude from
        include_only: List of variants to include in
        pydantic/sqlalchemy/pathway: Target-specific options
        **metadata: Additional metadata

    Returns:
        FieldInfo object with field configuration
    """
    return FieldInfo(
        default=default,
        default_factory=default_factory,
        description=description,
        min_length=min_length,
        max_length=max_length,
        min_value=min_value,
        max_value=max_value,
        regex=regex,
        format=format,
        primary_key=primary_key,
        unique=unique,
        index=index,
        foreign_key=foreign_key,
        auto_increment=auto_increment,
        auto_now_add=auto_now_add,
        auto_now=auto_now,
        relationship=relationship,
        back_populates=back_populates,
        cascade=cascade,
        through_table=through_table,
        exclude_from=exclude_from or [],
        include_only=include_only or [],
        pydantic=pydantic or {},
        sqlalchemy=sqlalchemy or {},
        pathway=pathway or {},
        metadata=metadata,
    )


class SchemaRegistry:
    """Global registry of all schema definitions"""

    _schemas: dict[str, type] = {}

    @classmethod
    def register(cls, schema_class: type) -> type:
        """Register a schema class"""
        cls._schemas[schema_class.__name__] = schema_class
        return schema_class

    @classmethod
    def get_schema(cls, name: str) -> type | None:
        """Get a registered schema by name"""
        return cls._schemas.get(name)

    @classmethod
    def get_all_schemas(cls) -> dict[str, type]:
        """Get all registered schemas"""
        return cls._schemas.copy()


def Schema(cls: type) -> type:
    """Decorator to mark a class as a schema definition

    Usage:
        @Schema
        class User:
            name: str = Field(max_length=100)
            email: str = Field(format="email")
            age: int | None = Field(default=None)
    """

    # Register the schema
    SchemaRegistry.register(cls)

    # Store schema metadata
    cls._schema_fields = {}
    cls._schema_name = cls.__name__

    # Extract field information from class annotations and defaults
    type_hints = get_type_hints(cls)

    for field_name, field_type in type_hints.items():
        # Skip private fields and methods
        if field_name.startswith("_"):
            continue

        # Get field info from class attribute or create default
        field_info = getattr(cls, field_name, Field())

        # If it's not a FieldInfo, create one with the value as default
        if not isinstance(field_info, FieldInfo):
            field_info = Field(default=field_info)

        cls._schema_fields[field_name] = {
            "name": field_name,
            "type": field_type,
            "field_info": field_info,
        }

    # Extract custom code sections if defined
    cls._custom_code = {}

    # Target-specific meta classes
    target_meta_classes = {
        "pydantic": "PydanticMeta",
        "sqlalchemy": "SQLAlchemyMeta",
        "pathway": "PathwayMeta",
    }

    # Extract target-specific meta classes
    for target, meta_name in target_meta_classes.items():
        if hasattr(cls, meta_name):
            meta_class = getattr(cls, meta_name)
            cls._custom_code[target] = _extract_meta_attributes(meta_class)

    return cls


def _extract_meta_attributes(meta_class) -> dict:
    """Extract attributes from a meta class"""
    meta_data = {}

    # Standard attributes that all targets support
    standard_attrs = ["raw_code", "imports", "validators", "methods"]

    # Target-specific attributes
    target_specific_attrs = [
        # SQLAlchemy specific
        "table_name",
        "indexes",
        "constraints",
        # Pathway specific
        "table_properties",
        "transformations",
        # Future extensibility - any other attributes
    ]

    # Extract all attributes
    all_attrs = standard_attrs + target_specific_attrs
    for attr_name in all_attrs:
        if hasattr(meta_class, attr_name):
            meta_data[attr_name] = getattr(meta_class, attr_name)

    return meta_data
