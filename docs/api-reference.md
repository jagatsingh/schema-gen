# API Reference

This page documents the Python API for Schema Gen.

## Core Components

### `@Schema` Decorator

The `@Schema` decorator marks a class as a schema definition.

```python
from schema_gen import Schema

@Schema
class MyModel:
    """Schema description"""
    # field definitions...
```

**Parameters:**
- None - The decorator takes no parameters

**Returns:**
- The decorated class with schema metadata added

**Behavior:**
- Registers the schema in the global schema registry
- Adds `_schema_name` and `_schema_fields` attributes
- Enables schema parsing and generation

### `Field()` Function

The `Field()` function defines field configuration and validation rules.

```python
from schema_gen import Field

field = Field(
    default=None,
    description="Field description",
    min_length=1,
    max_length=100,
    # ... other options
)
```

**Parameters:**

#### Basic Configuration
- **`default`** (`Any`, optional) - Static default value
- **`default_factory`** (`Callable`, optional) - Factory function for default value
- **`description`** (`str`, optional) - Human-readable field description

#### Validation Constraints
- **`min_length`** (`int`, optional) - Minimum string length
- **`max_length`** (`int`, optional) - Maximum string length
- **`regex`** (`str`, optional) - Regular expression pattern
- **`min_value`** (`Union[int, float]`, optional) - Minimum numeric value
- **`max_value`** (`Union[int, float]`, optional) - Maximum numeric value
- **`format`** (`str`, optional) - Format validation (`"email"`, `"uri"`, `"uuid"`, etc.)

#### Database Properties
- **`primary_key`** (`bool`, default `False`) - Mark as primary key
- **`auto_increment`** (`bool`, default `False`) - Auto-incrementing field
- **`unique`** (`bool`, default `False`) - Unique constraint
- **`index`** (`bool`, default `False`) - Database index
- **`foreign_key`** (`str`, optional) - Foreign key reference
- **`auto_now_add`** (`bool`, default `False`) - Set on creation
- **`auto_now`** (`bool`, default `False`) - Update on every save

#### Relationship Configuration
- **`relationship`** (`str`, optional) - Relationship type (`"one_to_many"`, `"many_to_one"`, `"many_to_many"`)
- **`back_populates`** (`str`, optional) - Bidirectional relationship field
- **`cascade`** (`str`, optional) - SQLAlchemy cascade options
- **`through_table`** (`str`, optional) - Many-to-many join table

#### Generation Control
- **`exclude_from`** (`List[str]`, optional) - Exclude from specific variants
- **`include_only`** (`List[str]`, optional) - Include only in specific variants

#### Target-Specific Configuration
- **`pydantic`** (`Dict[str, Any]`, optional) - Pydantic-specific options
- **`sqlalchemy`** (`Dict[str, Any]`, optional) - SQLAlchemy-specific options
- **`pathway`** (`Dict[str, Any]`, optional) - Pathway-specific options
- **`custom_metadata`** (`Dict[str, Any]`, optional) - Custom metadata

**Returns:**
- `FieldInfo` object containing all field configuration

### `Config` Class

Configuration object for Schema Gen projects.

```python
from schema_gen import Config

config = Config(
    input_dir="schemas",
    output_dir="generated",
    targets=["pydantic"]
)
```

**Parameters:**
- **`input_dir`** (`str`) - Directory containing schema definitions
- **`output_dir`** (`str`) - Directory for generated code
- **`targets`** (`List[str]`) - List of generation targets
- **`pydantic`** (`Dict[str, Any]`, optional) - Pydantic generator settings
- **`sqlalchemy`** (`Dict[str, Any]`, optional) - SQLAlchemy generator settings
- **`pathway`** (`Dict[str, Any]`, optional) - Pathway generator settings

## Schema Registry

### `SchemaRegistry`

Global registry that tracks all defined schemas.

```python
from schema_gen.core.schema import SchemaRegistry

# Get all registered schemas
schemas = SchemaRegistry.get_all_schemas()

# Get specific schema
schema = SchemaRegistry.get_schema("MyModel")

# Clear registry (mainly for testing)
SchemaRegistry.clear()
```

**Methods:**

#### `get_all_schemas() -> Dict[str, Type]`
Returns all registered schema classes.

#### `get_schema(name: str) -> Optional[Type]`
Returns a specific schema class by name.

#### `clear() -> None`
Clears all registered schemas (used in testing).

## Universal Schema Representation (USR)

### `FieldType` Enum

Enumeration of supported field types in the universal representation.

```python
from schema_gen.core.usr import FieldType

# Available types
FieldType.STRING
FieldType.INTEGER
FieldType.FLOAT
FieldType.BOOLEAN
FieldType.DATETIME
FieldType.DATE
FieldType.TIME
FieldType.UUID
FieldType.DECIMAL
FieldType.DICT
FieldType.LIST
FieldType.BYTES
```

### `USRField` Class

Universal representation of a field definition.

```python
from schema_gen.core.usr import USRField, FieldType

field = USRField(
    name="username",
    type=FieldType.STRING,
    optional=False,
    constraints={
        "min_length": 3,
        "max_length": 30
    },
    metadata={
        "description": "Unique username"
    }
)
```

**Attributes:**
- **`name`** (`str`) - Field name
- **`type`** (`FieldType`) - Field type
- **`optional`** (`bool`) - Whether field is optional
- **`constraints`** (`Dict[str, Any]`) - Validation constraints
- **`metadata`** (`Dict[str, Any]`) - Additional metadata
- **`target_config`** (`Dict[str, Dict[str, Any]]`) - Target-specific configuration

### `USRSchema` Class

Universal representation of a complete schema.

```python
from schema_gen.core.usr import USRSchema

schema = USRSchema(
    name="User",
    fields=[field1, field2, ...],
    variants={"create": ["field1"], "response": ["field1", "field2"]},
    metadata={"description": "User schema"}
)
```

**Attributes:**
- **`name`** (`str`) - Schema name
- **`fields`** (`List[USRField]`) - Schema fields
- **`variants`** (`Dict[str, List[str]]`) - Schema variants
- **`metadata`** (`Dict[str, Any]`) - Schema metadata

**Methods:**

#### `get_variant_fields(variant_name: str) -> List[USRField]`
Returns fields for a specific variant.

#### `get_field(field_name: str) -> Optional[USRField]`
Returns a specific field by name.

## Parsers

### `SchemaParser`

Parses Python schema classes into USR format.

```python
from schema_gen.parsers.schema_parser import SchemaParser

parser = SchemaParser()
usr_schema = parser.parse_schema(MySchemaClass)
```

**Methods:**

#### `parse_schema(schema_class: Type) -> USRSchema`
Converts a Python schema class to USR format.

**Parameters:**
- **`schema_class`** - Class decorated with `@Schema`

**Returns:**
- `USRSchema` object representing the parsed schema

## Generators

### `PydanticGenerator`

Generates Pydantic models from USR schemas.

```python
from schema_gen.generators.pydantic_generator import PydanticGenerator

generator = PydanticGenerator()
```

**Methods:**

#### `generate_model(schema: USRSchema, variant: Optional[str] = None) -> str`
Generates Pydantic model code for a schema.

**Parameters:**
- **`schema`** (`USRSchema`) - Schema to generate from
- **`variant`** (`Optional[str]`) - Specific variant to generate

**Returns:**
- Generated Python code as string

#### `generate_all_variants(schema: USRSchema) -> Dict[str, str]`
Generates all variants for a schema.

**Parameters:**
- **`schema`** (`USRSchema`) - Schema to generate from

**Returns:**
- Dictionary mapping variant names to generated code

#### `generate_file(schema: USRSchema, output_path: Path) -> None`
Generates and writes model file to disk.

**Parameters:**
- **`schema`** (`USRSchema`) - Schema to generate from
- **`output_path`** (`Path`) - File path to write to

## Generation Engine

### `SchemaGenerationEngine`

Main engine that coordinates schema parsing and code generation.

```python
from schema_gen.core.generator import SchemaGenerationEngine

engine = SchemaGenerationEngine(config)
```

**Methods:**

#### `load_schemas_from_directory() -> None`
Loads and parses all schema files from the input directory.

#### `generate_all() -> None`
Generates code for all loaded schemas and all configured targets.

#### `generate_target(target_name: str) -> None`
Generates code for a specific target.

**Parameters:**
- **`target_name`** (`str`) - Name of target to generate

### `create_generation_engine(config_path: str) -> SchemaGenerationEngine`

Factory function to create a generation engine from a config file.

**Parameters:**
- **`config_path`** (`str`) - Path to configuration file

**Returns:**
- Configured `SchemaGenerationEngine` instance

## Type Mapping

### `TypeMapper`

Maps Python types to USR field types.

```python
from schema_gen.core.usr import TypeMapper

mapper = TypeMapper()
field_type = mapper.map_type(str)  # Returns FieldType.STRING
```

**Methods:**

#### `map_type(python_type: Type) -> FieldType`
Maps a Python type to a USR field type.

**Parameters:**
- **`python_type`** (`Type`) - Python type to map

**Returns:**
- Corresponding `FieldType` enum value

## Exceptions

### `SchemaGenError`

Base exception for all Schema Gen errors.

```python
from schema_gen.exceptions import SchemaGenError
```

### `ValidationError`

Raised when schema validation fails.

```python
from schema_gen.exceptions import ValidationError
```

### `GenerationError`

Raised when code generation fails.

```python
from schema_gen.exceptions import GenerationError
```

## Usage Examples

### Basic Schema Definition

```python
from schema_gen import Schema, Field
from typing import Optional

@Schema
class User:
    id: int = Field(primary_key=True, auto_increment=True)
    name: str = Field(max_length=100)
    email: str = Field(format="email", unique=True)
    age: Optional[int] = Field(default=None, min_value=0)

    class Variants:
        create = ['name', 'email', 'age']
        response = ['id', 'name', 'email', 'age']
```

### Programmatic Usage

```python
from schema_gen import Config
from schema_gen.core.generator import SchemaGenerationEngine

# Create configuration
config = Config(
    input_dir="schemas",
    output_dir="generated",
    targets=["pydantic"]
)

# Create engine
engine = SchemaGenerationEngine(config)

# Load and generate
engine.load_schemas_from_directory()
engine.generate_all()
```

### Direct Generator Usage

```python
from schema_gen.parsers.schema_parser import SchemaParser
from schema_gen.generators.pydantic_generator import PydanticGenerator

# Parse schema
parser = SchemaParser()
usr_schema = parser.parse_schema(User)

# Generate model
generator = PydanticGenerator()
model_code = generator.generate_model(usr_schema)
print(model_code)
```
