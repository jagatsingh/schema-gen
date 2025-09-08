# Configuration

Schema Gen is configured using a Python configuration file that provides type safety and flexibility.

## Configuration File

The configuration file is a Python file (typically `.schema-gen.config.py`) that defines a `config` variable:

```python
from schema_gen import Config

config = Config(
    input_dir="schemas",
    output_dir="generated",
    targets=[
        # Python ecosystem
        "pydantic", "sqlalchemy", "dataclasses", "typeddict", "pathway",
        # TypeScript/JavaScript
        "zod",
        # Schema formats
        "jsonschema", "graphql", "protobuf", "avro",
        # JVM languages
        "jackson", "kotlin"
    ],

    # Target-specific settings
    pydantic={
        "use_enum": True,
        "extra": "forbid",
    }
)
```

## Core Settings

### `input_dir: str`
Directory containing your schema definitions.

**Default:** `"schemas"`

```python
config = Config(
    input_dir="src/schemas",  # Look for schemas in src/schemas/
)
```

### `output_dir: str`
Directory where generated code will be written.

**Default:** `"generated"`

```python
config = Config(
    output_dir="src/generated",  # Output to src/generated/
)
```

### `targets: List[str]`
List of code generation targets to run.

**Available targets:**
- `"pydantic"` - Pydantic v2 models
- `"sqlalchemy"` - SQLAlchemy ORM models
- `"zod"` - Zod validation schemas (TypeScript)
- `"pathway"` - Pathway schemas (planned)

**Default:** `["pydantic"]`

```python
config = Config(
    targets=["pydantic", "sqlalchemy", "zod"],  # Generate all three
)
```

## Target-Specific Settings

### Pydantic Settings

Configure Pydantic model generation with the `pydantic` dictionary:

```python
config = Config(
    targets=["pydantic"],
    pydantic={
        # Model configuration
        "use_enum": True,              # Use Enum for Literal types
        "extra": "forbid",             # Forbid extra fields
        "validate_assignment": True,   # Validate on assignment
        "arbitrary_types_allowed": False,  # Allow arbitrary types

        # Import settings
        "imports": [                   # Additional imports
            "from myproject.types import CustomType"
        ],

        # Template customization
        "template_dir": "templates/",  # Custom template directory

        # File naming
        "model_suffix": "_models",     # File suffix (user_models.py)
        "class_naming": "PascalCase",  # Class naming convention
    }
)
```

#### Schema Variants

Schema variants allow you to generate multiple Pydantic models from a single schema definition, each containing only a specific subset of fields. This is useful for creating different models for different use cases (API requests, responses, public views, etc.).

**How Variants Work:**

Variants are defined directly in your schema files using a `Variants` class, not in the configuration:

```python
@Schema
class User:
    """User schema for the application"""

    id: int = Field(primary_key=True, description="Unique identifier")
    name: str = Field(max_length=100, description="User's full name")
    email: str = Field(format="email", description="User's email address")
    age: Optional[int] = Field(default=None, description="User's age")
    created_at: datetime = Field(auto_now_add=True, description="Creation timestamp")

    class Variants:
        create_request = ['name', 'email', 'age']        # For user creation
        update_request = ['name', 'email', 'age']        # For user updates
        public_response = ['id', 'name', 'age', 'created_at']  # Public API
        full_response = ['id', 'name', 'email', 'age', 'created_at']  # Admin API
```

**Generated Models:**

- Base model: `User` (contains all fields)
- Variant models: `UserCreateRequest`, `UserUpdateRequest`, `UserPublicResponse`, `UserFullResponse`

**Important Notes:**

- Variants are controlled entirely by the `Variants` class in your schema definition
- Each variant becomes a separate Pydantic class with only the specified fields
- Only the base model includes custom validators and methods; variants are clean data structures
- All variants are generated automatically when you run `schema-gen generate`

**Available Pydantic options:**

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `use_enum` | `bool` | `True` | Convert Literal types to Enums |
| `extra` | `str` | `"forbid"` | Extra field handling (`"allow"`, `"forbid"`, `"ignore"`) |
| `validate_assignment` | `bool` | `True` | Validate field assignments |
| `arbitrary_types_allowed` | `bool` | `False` | Allow arbitrary Python types |
| `imports` | `List[str]` | `[]` | Additional import statements |
| `template_dir` | `str` | `None` | Custom Jinja2 template directory |
| `model_suffix` | `str` | `"_models"` | Generated file suffix |
| `class_naming` | `str` | `"PascalCase"` | Class naming convention |

### SQLAlchemy Settings

Configure SQLAlchemy ORM model generation:

```python
config = Config(
    targets=["sqlalchemy"],
    sqlalchemy={
        "use_declarative": True,       # Use declarative base
        "base_class": "Base",          # Base class name
        "table_naming": "snake_case",  # Table naming convention
        "relationship_loading": "lazy", # Relationship loading strategy
        "include_metadata": True,      # Include Column metadata
        "generate_relationships": True, # Generate relationship mappings
    }
)
```

**Available SQLAlchemy options:**

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `use_declarative` | `bool` | `True` | Use declarative base class |
| `base_class` | `str` | `"Base"` | Base class name for models |
| `table_naming` | `str` | `"snake_case"` | Table naming convention |
| `relationship_loading` | `str` | `"lazy"` | Default relationship loading strategy |
| `include_metadata` | `bool` | `True` | Include Column metadata and constraints |
| `generate_relationships` | `bool` | `True` | Generate relationship mappings |

### Zod Settings

Configure Zod schema generation for TypeScript:

```python
config = Config(
    targets=["zod"],
    zod={
        "generate_types": True,        # Generate TypeScript types
        "strict_mode": True,           # Use strict validation
        "export_schemas": True,        # Export schema objects
        "file_extension": ".ts",       # File extension (.ts or .js)
        "import_style": "named",       # Import style ("named" or "default")
    }
)
```

**Available Zod options:**

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `generate_types` | `bool` | `True` | Generate TypeScript type definitions |
| `strict_mode` | `bool` | `True` | Use strict validation rules |
| `export_schemas` | `bool` | `True` | Export Zod schema objects |
| `file_extension` | `str` | `".ts"` | Generated file extension |
| `import_style` | `str` | `"named"` | Import style for Zod library |

### Pathway Settings (Planned)

```python
config = Config(
    targets=["pathway"],
    pathway={
        "column_type": "pw.Column",    # Column type to use
        "table_type": "pw.Table",      # Table type to use
        "optional_handling": "Union",  # How to handle Optional types
    }
)
```

## Environment-Specific Configuration

### Multiple Config Files

Use different configuration files for different environments:

```python
# .schema-gen.dev.config.py
from schema_gen import Config

config = Config(
    input_dir="schemas",
    output_dir="generated",
    targets=["pydantic"],
    pydantic={
        "validate_assignment": True,   # Strict validation for development
        "extra": "forbid",
    }
)
```

```python
# .schema-gen.prod.config.py
from schema_gen import Config

config = Config(
    input_dir="schemas",
    output_dir="generated",
    targets=["pydantic", "sqlalchemy"],  # More targets for production
    pydantic={
        "validate_assignment": False,  # Less strict for performance
        "extra": "ignore",
    }
)
```

Use with CLI:
```bash
schema-gen generate --config .schema-gen.dev.config.py
schema-gen generate --config .schema-gen.prod.config.py
```

### Environment Variables

Reference environment variables in your config:

```python
import os
from schema_gen import Config

config = Config(
    input_dir=os.getenv("SCHEMA_INPUT_DIR", "schemas"),
    output_dir=os.getenv("SCHEMA_OUTPUT_DIR", "generated"),
    targets=os.getenv("SCHEMA_TARGETS", "pydantic").split(","),
)
```

### Conditional Configuration

Use Python logic for conditional configuration:

```python
import os
from schema_gen import Config

# Detect environment
is_development = os.getenv("ENV") == "development"
is_production = os.getenv("ENV") == "production"

config = Config(
    input_dir="schemas",
    output_dir="generated",

    # More targets in production
    targets=["pydantic", "sqlalchemy"] if is_production else ["pydantic"],

    pydantic={
        # Strict validation in development
        "validate_assignment": is_development,
        "extra": "forbid" if is_development else "ignore",
    }
)
```

## Validation and Type Safety

The configuration system provides full type safety and validation:

```python
from schema_gen import Config

# This will raise a validation error
config = Config(
    targets=["invalid_target"]  # ❌ Error: unknown target
)

# This will provide IDE autocomplete and type checking
config = Config(
    input_dir="schemas",        # ✅ Type: str
    targets=["pydantic"],       # ✅ Type: List[str], valid values
    pydantic={
        "extra": "forbid",      # ✅ Type: str, valid enum value
        "use_enum": True,       # ✅ Type: bool
    }
)
```

## Configuration Reference

### Full Example

```python
"""Complete configuration example"""

import os
from schema_gen import Config

config = Config(
    # Core settings
    input_dir="schemas",
    output_dir="generated",
    targets=["pydantic", "sqlalchemy", "zod"],

    # Pydantic settings
    pydantic={
        # Model behavior
        "use_enum": True,
        "extra": "forbid",
        "validate_assignment": True,
        "arbitrary_types_allowed": False,

        # Code generation
        "imports": [
            "from myproject.types import CustomEnum",
            "from decimal import Decimal",
        ],
        "model_suffix": "_models",
        "class_naming": "PascalCase",

        # Template customization
        "template_dir": None,  # Use built-in templates
    },

    # SQLAlchemy settings
    sqlalchemy={
        "use_declarative": True,
        "base_class": "Base",
        "table_naming": "snake_case",
        "generate_relationships": True,
    },

    # Zod settings
    zod={
        "generate_types": True,
        "strict_mode": True,
        "export_schemas": True,
        "file_extension": ".ts",
    },

    # Future: Pathway settings
    pathway={
        "column_type": "pw.Column",
        "table_type": "pw.Table",
    }
)
```
