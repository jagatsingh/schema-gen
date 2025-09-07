"""Universal Schema Representation (USR) - Internal schema format"""

from enum import Enum
from typing import Any, Dict, List, Optional, Union, Type
from dataclasses import dataclass, field
import typing


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
    DICT = "dict"
    UNION = "union"
    OPTIONAL = "optional"
    LITERAL = "literal"
    NESTED_SCHEMA = "nested_schema"


@dataclass
class USRField:
    """Universal representation of a schema field"""
    
    name: str
    type: FieldType
    python_type: Type  # Original Python type for reference
    
    # Value properties
    optional: bool = False
    default: Any = None
    default_factory: Optional[callable] = None
    
    # Type-specific properties
    inner_type: Optional['USRField'] = None  # For List, Optional, etc.
    union_types: List['USRField'] = field(default_factory=list)  # For Union
    literal_values: List[Any] = field(default_factory=list)  # For Literal
    nested_schema: Optional[str] = None  # Schema name for nested types
    
    # Validation constraints
    min_length: Optional[int] = None
    max_length: Optional[int] = None
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    regex_pattern: Optional[str] = None
    format_type: Optional[str] = None  # email, uri, uuid, etc.
    
    # Database properties
    primary_key: bool = False
    unique: bool = False
    index: bool = False
    foreign_key: Optional[str] = None
    auto_increment: bool = False
    auto_now_add: bool = False
    auto_now: bool = False
    
    # Relationship properties
    relationship: Optional[str] = None  # one_to_many, many_to_one, many_to_many
    back_populates: Optional[str] = None
    cascade: Optional[str] = None
    through_table: Optional[str] = None
    
    # Generation control
    exclude_from: List[str] = field(default_factory=list)
    include_only: List[str] = field(default_factory=list)
    
    # Target-specific configuration
    target_config: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    
    # Metadata
    description: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass 
class USRSchema:
    """Universal representation of a complete schema"""
    
    name: str
    fields: List[USRField]
    description: Optional[str] = None
    
    # Variants configuration
    variants: Dict[str, List[str]] = field(default_factory=dict)
    
    # Schema-level metadata
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def get_field(self, name: str) -> Optional[USRField]:
        """Get a field by name"""
        return next((f for f in self.fields if f.name == name), None)
    
    def get_primary_key_fields(self) -> List[USRField]:
        """Get all primary key fields"""
        return [f for f in self.fields if f.primary_key]
    
    def get_relationship_fields(self) -> List[USRField]:
        """Get all relationship fields"""
        return [f for f in self.fields if f.relationship is not None]
    
    def get_variant_fields(self, variant_name: str) -> List[USRField]:
        """Get fields for a specific variant"""
        if variant_name not in self.variants:
            return self.fields  # Return all fields if variant doesn't exist
        
        variant_field_names = self.variants[variant_name]
        return [f for f in self.fields if f.name in variant_field_names]


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
    }
    
    @classmethod
    def python_type_to_usr(cls, python_type: Type) -> FieldType:
        """Convert Python type to USR FieldType"""
        
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
        
        if origin is dict:
            return FieldType.DICT
        
        # Handle standard library types
        import datetime
        import uuid
        import decimal
        
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
            if hasattr(typing, 'get_origin') and typing.get_origin(python_type) is typing.Literal:
                return FieldType.LITERAL
        except:
            pass
        
        # Default to nested schema for unknown types
        return FieldType.NESTED_SCHEMA
    
    @classmethod
    def create_usr_field_from_python(cls, name: str, python_type: Type, field_info: Any) -> USRField:
        """Create USR field from Python type and field info"""
        
        field_type = cls.python_type_to_usr(python_type)
        
        # Handle Optional types
        optional = False
        inner_type = None
        union_types = []
        literal_values = []
        nested_schema = None
        
        origin = typing.get_origin(python_type)
        
        if origin is Union:
            args = typing.get_args(python_type)
            if len(args) == 2 and type(None) in args:
                # This is Optional[T]
                optional = True
                non_none_type = next(arg for arg in args if arg is not type(None))
                inner_type = cls.create_usr_field_from_python(f"{name}_inner", non_none_type, None)
            else:
                # This is Union[T1, T2, ...]
                union_types = [cls.create_usr_field_from_python(f"{name}_{i}", arg, None) 
                              for i, arg in enumerate(args)]
        
        elif origin is list:
            args = typing.get_args(python_type)
            if args:
                inner_type = cls.create_usr_field_from_python(f"{name}_item", args[0], None)
        
        elif field_type == FieldType.LITERAL:
            try:
                literal_values = list(typing.get_args(python_type))
            except:
                literal_values = []
        
        elif field_type == FieldType.NESTED_SCHEMA:
            nested_schema = getattr(python_type, '__name__', str(python_type))
        
        return USRField(
            name=name,
            type=field_type,
            python_type=python_type,
            optional=optional,
            inner_type=inner_type,
            union_types=union_types,
            literal_values=literal_values,
            nested_schema=nested_schema,
            
            # Copy field_info properties if available
            default=getattr(field_info, 'default', None),
            default_factory=getattr(field_info, 'default_factory', None),
            min_length=getattr(field_info, 'min_length', None),
            max_length=getattr(field_info, 'max_length', None),
            min_value=getattr(field_info, 'min_value', None),
            max_value=getattr(field_info, 'max_value', None),
            regex_pattern=getattr(field_info, 'regex', None),
            format_type=getattr(field_info, 'format', None),
            primary_key=getattr(field_info, 'primary_key', False),
            unique=getattr(field_info, 'unique', False),
            index=getattr(field_info, 'index', False),
            foreign_key=getattr(field_info, 'foreign_key', None),
            auto_increment=getattr(field_info, 'auto_increment', False),
            auto_now_add=getattr(field_info, 'auto_now_add', False),
            auto_now=getattr(field_info, 'auto_now', False),
            relationship=getattr(field_info, 'relationship', None),
            back_populates=getattr(field_info, 'back_populates', None),
            cascade=getattr(field_info, 'cascade', None),
            through_table=getattr(field_info, 'through_table', None),
            exclude_from=getattr(field_info, 'exclude_from', []),
            include_only=getattr(field_info, 'include_only', []),
            target_config={
                'pydantic': getattr(field_info, 'pydantic', {}),
                'sqlalchemy': getattr(field_info, 'sqlalchemy', {}),
                'pathway': getattr(field_info, 'pathway', {}),
            },
            description=getattr(field_info, 'description', None),
            metadata=getattr(field_info, 'metadata', {}),
        )