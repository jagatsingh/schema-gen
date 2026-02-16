"""Universal Schema Representation (USR) - Internal schema format"""

import types
import typing
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional, Union


@dataclass
class ValidationIssue:
    """Result of a single validation check on a USR schema or field"""

    severity: str  # "error", "warning", "info"
    field_name: str | None
    message: str


class FieldType(Enum):
    """Universal field types supported by schema_gen"""

    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    DATETIME = "datetime"
    DATE = "date"
    TIME = "time"
    UUID = "uuid"
    DECIMAL = "decimal"
    JSON = "json"
    BYTES = "bytes"
    LIST = "list"
    SET = "set"
    FROZENSET = "frozenset"
    TUPLE = "tuple"
    DICT = "dict"
    UNION = "union"
    OPTIONAL = "optional"
    LITERAL = "literal"
    ENUM = "enum"
    NESTED_SCHEMA = "nested_schema"


# Types where min_value/max_value constraints make sense
NUMERIC_TYPES = frozenset({FieldType.INTEGER, FieldType.FLOAT, FieldType.DECIMAL})

# Types where min_length/max_length constraints make sense
STRING_LIKE_TYPES = frozenset(
    {
        FieldType.STRING,
        FieldType.LIST,
        FieldType.SET,
        FieldType.FROZENSET,
        FieldType.BYTES,
    }
)


@dataclass
class USREnum:
    """Universal representation of an enum type"""

    name: str
    values: list[tuple[str, Any]]  # (member_name, member_value)


@dataclass
class USRField:
    """Universal representation of a schema field"""

    name: str
    type: FieldType
    python_type: type  # Original Python type for reference

    # Value properties
    optional: bool = False
    default: Any = None
    default_factory: Callable | None = None

    # Type-specific properties
    inner_type: Optional["USRField"] = None  # For List, Optional, etc.
    union_types: list["USRField"] = field(default_factory=list)  # For Union
    literal_values: list[Any] = field(default_factory=list)  # For Literal
    nested_schema: str | None = None  # Schema name for nested types
    enum_name: str | None = None  # Enum class name for ENUM types
    enum_values: list[Any] = field(default_factory=list)  # Enum member values

    # Validation constraints
    min_length: int | None = None
    max_length: int | None = None
    min_value: float | None = None
    max_value: float | None = None
    regex_pattern: str | None = None
    format_type: str | None = None  # email, uri, uuid, etc.

    # Database properties
    primary_key: bool = False
    unique: bool = False
    index: bool = False
    foreign_key: str | None = None
    auto_increment: bool = False
    auto_now_add: bool = False
    auto_now: bool = False

    # Relationship properties
    relationship: str | None = None  # one_to_many, many_to_one, many_to_many
    back_populates: str | None = None
    cascade: str | None = None
    through_table: str | None = None

    # Generation control
    exclude_from: list[str] = field(default_factory=list)
    include_only: list[str] = field(default_factory=list)

    # Target-specific configuration
    target_config: dict[str, dict[str, Any]] = field(default_factory=dict)

    # Metadata
    description: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> list[ValidationIssue]:
        """Validate this field for common misconfigurations.

        Returns a list of ValidationIssue objects. Call this explicitly;
        it is not invoked automatically during construction.
        """
        issues: list[ValidationIssue] = []

        # Primary key that is also optional
        if self.primary_key and self.optional:
            issues.append(
                ValidationIssue(
                    severity="warning",
                    field_name=self.name,
                    message="Field is marked as primary_key but is also optional",
                )
            )

        # List/Set/Frozenset type without inner_type
        if (
            self.type in (FieldType.LIST, FieldType.SET, FieldType.FROZENSET)
            and self.inner_type is None
        ):
            issues.append(
                ValidationIssue(
                    severity="warning",
                    field_name=self.name,
                    message=f"{self.type.value.capitalize()} field has no inner_type specified",
                )
            )

        # min_value / max_value on non-numeric fields
        if (
            self.min_value is not None or self.max_value is not None
        ) and self.type not in NUMERIC_TYPES:
            issues.append(
                ValidationIssue(
                    severity="warning",
                    field_name=self.name,
                    message=f"min_value/max_value set on non-numeric field (type={self.type.value})",
                )
            )

        # min_length / max_length on non-string/non-list fields
        if (
            self.min_length is not None or self.max_length is not None
        ) and self.type not in STRING_LIKE_TYPES:
            issues.append(
                ValidationIssue(
                    severity="warning",
                    field_name=self.name,
                    message=f"min_length/max_length set on non-string/non-list field (type={self.type.value})",
                )
            )

        # enum_name set but enum_values is empty
        if self.enum_name and not self.enum_values:
            issues.append(
                ValidationIssue(
                    severity="error",
                    field_name=self.name,
                    message=f"enum_name '{self.enum_name}' is set but enum_values is empty",
                )
            )

        # foreign_key set but no relationship defined
        if self.foreign_key and not self.relationship:
            issues.append(
                ValidationIssue(
                    severity="info",
                    field_name=self.name,
                    message="foreign_key is set but no relationship is defined",
                )
            )

        return issues


@dataclass
class USRSchema:
    """Universal representation of a complete schema"""

    name: str
    fields: list[USRField]
    description: str | None = None

    # Enum types used by this schema
    enums: list[USREnum] = field(default_factory=list)

    # Variants configuration
    variants: dict[str, list[str]] = field(default_factory=dict)

    # Custom code sections for complex model features
    custom_code: dict[str, Any] = field(default_factory=dict)

    # Target-specific configuration (e.g., package names)
    target_config: dict[str, dict[str, Any]] = field(default_factory=dict)

    # Schema-level metadata
    metadata: dict[str, Any] = field(default_factory=dict)

    def get_field(self, name: str) -> USRField | None:
        """Get a field by name"""
        return next((f for f in self.fields if f.name == name), None)

    def get_primary_key_fields(self) -> list[USRField]:
        """Get all primary key fields"""
        return [f for f in self.fields if f.primary_key]

    def get_relationship_fields(self) -> list[USRField]:
        """Get all relationship fields"""
        return [f for f in self.fields if f.relationship is not None]

    def get_self_referencing_fields(self) -> list[USRField]:
        """Get all fields that reference this schema itself (self-referential).

        A field is self-referencing if:
        - It has nested_schema == self.name (direct self-reference), or
        - It is a LIST/SET/FROZENSET with inner_type.nested_schema == self.name
        """
        result = []
        for f in self.fields:
            if f.nested_schema == self.name or (
                f.type in (FieldType.LIST, FieldType.SET, FieldType.FROZENSET)
                and f.inner_type
                and f.inner_type.nested_schema == self.name
            ):
                result.append(f)
        return result

    def get_variant_fields(self, variant_name: str) -> list[USRField]:
        """Get fields for a specific variant

        Raises:
            KeyError: If variant_name is not defined on this schema
        """
        if variant_name not in self.variants:
            raise KeyError(
                f"Variant '{variant_name}' not found on schema '{self.name}'. "
                f"Available: {list(self.variants.keys())}"
            )

        variant_field_names = self.variants[variant_name]
        return [f for f in self.fields if f.name in variant_field_names]

    def validate(self) -> list[ValidationIssue]:
        """Validate this schema for common misconfigurations.

        Returns a list of ValidationIssue objects. Call this explicitly;
        it is not invoked automatically during construction.
        """
        issues: list[ValidationIssue] = []

        # Collect all field names for reference checks
        field_names = {f.name for f in self.fields}

        # Validate each field individually
        for usr_field in self.fields:
            issues.extend(usr_field.validate())

        # Validate variant references
        for variant_name, variant_field_names in self.variants.items():
            for ref_name in variant_field_names:
                if ref_name not in field_names:
                    issues.append(
                        ValidationIssue(
                            severity="error",
                            field_name=None,
                            message=(
                                f"Variant '{variant_name}' references field "
                                f"'{ref_name}' which does not exist on schema "
                                f"'{self.name}'"
                            ),
                        )
                    )

        return issues


class TypeMapper:
    """Maps Python types to USR types"""

    _type_mapping = {
        str: FieldType.STRING,
        int: FieldType.INTEGER,
        float: FieldType.FLOAT,
        bool: FieldType.BOOLEAN,
        bytes: FieldType.BYTES,
        dict: FieldType.DICT,
        list: FieldType.LIST,
        set: FieldType.SET,
        frozenset: FieldType.FROZENSET,
        tuple: FieldType.TUPLE,
    }

    @classmethod
    def python_type_to_usr(cls, python_type: type) -> FieldType:
        """Convert Python type to USR FieldType"""

        # Handle string forward references (e.g., 'TreeNode' for self-referential types)
        if isinstance(python_type, str):
            return FieldType.NESTED_SCHEMA

        # Handle Annotated types - unwrap and recurse with base type
        if typing.get_origin(python_type) is typing.Annotated:
            base_type = typing.get_args(python_type)[0]
            return cls.python_type_to_usr(base_type)

        # Handle basic types
        if python_type in cls._type_mapping:
            return cls._type_mapping[python_type]

        # Handle typing module types
        origin = typing.get_origin(python_type)

        if origin is Union:
            args = typing.get_args(python_type)
            # Check if it's Optional (Union with None)
            if len(args) == 2 and type(None) in args:
                return FieldType.OPTIONAL
            else:
                return FieldType.UNION

        if origin is list:
            return FieldType.LIST

        if origin is set:
            return FieldType.SET

        if origin is frozenset:
            return FieldType.FROZENSET

        if origin is tuple:
            return FieldType.TUPLE

        if origin is dict:
            return FieldType.DICT

        # Handle standard library types
        import datetime
        import decimal
        import uuid

        if python_type is datetime.datetime:
            return FieldType.DATETIME
        elif python_type is datetime.date:
            return FieldType.DATE
        elif python_type is datetime.time:
            return FieldType.TIME
        elif python_type is uuid.UUID:
            return FieldType.UUID
        elif python_type is decimal.Decimal:
            return FieldType.DECIMAL

        # Check for Literal types
        try:
            if (
                hasattr(typing, "get_origin")
                and typing.get_origin(python_type) is typing.Literal
            ):
                return FieldType.LITERAL
        except (AttributeError, TypeError, ValueError):
            pass

        # Check for Enum types
        try:
            if isinstance(python_type, type) and issubclass(python_type, Enum):
                return FieldType.ENUM
        except TypeError:
            pass

        # Default to nested schema for unknown types
        return FieldType.NESTED_SCHEMA

    @classmethod
    def create_usr_field_from_python(
        cls, name: str, python_type: type, field_info: Any
    ) -> USRField:
        """Create USR field from Python type and field info"""

        # Handle Annotated types - extract metadata before processing
        annotated_metadata: list[Any] = []
        if typing.get_origin(python_type) is typing.Annotated:
            args = typing.get_args(python_type)
            python_type = args[0]  # base type
            annotated_metadata = list(args[1:])

        # Handle Optional types first
        optional = False
        inner_type = None
        union_types = []
        literal_values = []
        nested_schema = None
        actual_type = python_type

        origin = typing.get_origin(python_type)

        # Handle both typing.Union and types.UnionType (Python 3.12+ syntax)
        if origin is Union or origin is getattr(types, "UnionType", None):
            args = typing.get_args(python_type)
            if len(args) == 2 and type(None) in args:
                # This is Optional[T] or T | None
                optional = True
                non_none_type = next(arg for arg in args if arg is not type(None))
                actual_type = non_none_type  # Use the non-None type for field_type
                inner_type = cls.create_usr_field_from_python(
                    f"{name}_inner", non_none_type, None
                )
            else:
                # This is Union[T1, T2, ...]
                union_types = [
                    cls.create_usr_field_from_python(f"{name}_{i}", arg, None)
                    for i, arg in enumerate(args)
                ]

        elif origin is list or origin is set or origin is frozenset:
            args = typing.get_args(python_type)
            if args:
                inner_type = cls.create_usr_field_from_python(
                    f"{name}_item", args[0], None
                )

        elif origin is tuple:
            args = typing.get_args(python_type)
            if args:
                # tuple[str, ...] means variable-length homogeneous tuple -> treat as LIST
                if len(args) == 2 and args[1] is Ellipsis:
                    inner_type = cls.create_usr_field_from_python(
                        f"{name}_item", args[0], None
                    )
                    # Override actual_type so field_type becomes LIST
                    actual_type = list
                else:
                    # Fixed-length heterogeneous tuple like tuple[str, int, bool]
                    union_types = [
                        cls.create_usr_field_from_python(f"{name}_{i}", arg, None)
                        for i, arg in enumerate(args)
                    ]

        # Get field type from the actual type (not Optional wrapper)
        field_type = cls.python_type_to_usr(actual_type)

        # Enum-specific properties
        enum_name = None
        enum_values = []

        if field_type == FieldType.LITERAL:
            try:
                literal_values = list(typing.get_args(actual_type))
            except (AttributeError, TypeError, ValueError):
                literal_values = []

        elif field_type == FieldType.ENUM:
            enum_name = actual_type.__name__
            enum_values = [e.value for e in actual_type]

        elif field_type == FieldType.NESTED_SCHEMA:
            # Handle string forward references (self-referential types)
            if isinstance(actual_type, str):
                nested_schema = actual_type
            else:
                nested_schema = getattr(actual_type, "__name__", str(actual_type))

        usr_field = USRField(
            name=name,
            type=field_type,
            python_type=python_type,
            optional=optional,
            inner_type=inner_type,
            union_types=union_types,
            literal_values=literal_values,
            nested_schema=nested_schema,
            enum_name=enum_name,
            enum_values=enum_values,
            # Copy field_info properties if available
            default=getattr(field_info, "default", None),
            default_factory=getattr(field_info, "default_factory", None),
            min_length=getattr(field_info, "min_length", None),
            max_length=getattr(field_info, "max_length", None),
            min_value=getattr(field_info, "min_value", None),
            max_value=getattr(field_info, "max_value", None),
            regex_pattern=getattr(field_info, "regex", None),
            format_type=getattr(field_info, "format", None),
            primary_key=getattr(field_info, "primary_key", False),
            unique=getattr(field_info, "unique", False),
            index=getattr(field_info, "index", False),
            foreign_key=getattr(field_info, "foreign_key", None),
            auto_increment=getattr(field_info, "auto_increment", False),
            auto_now_add=getattr(field_info, "auto_now_add", False),
            auto_now=getattr(field_info, "auto_now", False),
            relationship=getattr(field_info, "relationship", None),
            back_populates=getattr(field_info, "back_populates", None),
            cascade=getattr(field_info, "cascade", None),
            through_table=getattr(field_info, "through_table", None),
            exclude_from=getattr(field_info, "exclude_from", []),
            include_only=getattr(field_info, "include_only", []),
            target_config={
                "pydantic": getattr(field_info, "pydantic", {}),
                "sqlalchemy": getattr(field_info, "sqlalchemy", {}),
                "pathway": getattr(field_info, "pathway", {}),
            },
            description=getattr(field_info, "description", None),
            metadata=getattr(field_info, "metadata", {}),
        )

        # Apply Annotated metadata to the USRField
        if annotated_metadata:
            for item in annotated_metadata:
                if isinstance(item, dict):
                    # Merge dict metadata into field.metadata
                    usr_field.metadata.update(item)
                elif isinstance(item, str):
                    # Use string as description if not already set from field_info
                    if usr_field.description is None:
                        usr_field.description = item
                else:
                    # Extract constraint attributes from objects (e.g. pydantic
                    # Field-like objects or custom constraint descriptors)
                    constraint_attrs = {
                        "min_length": "min_length",
                        "max_length": "max_length",
                        "ge": "min_value",
                        "le": "max_value",
                        "gt": "min_value",
                        "lt": "max_value",
                        "min_value": "min_value",
                        "max_value": "max_value",
                        "pattern": "regex_pattern",
                        "regex": "regex_pattern",
                    }
                    for attr_name, field_attr in constraint_attrs.items():
                        val = getattr(item, attr_name, None)
                        if val is not None and getattr(usr_field, field_attr) is None:
                            setattr(usr_field, field_attr, val)

        return usr_field
