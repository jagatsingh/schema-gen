# Schema Gen

[![CI](https://github.com/jagatsingh/schema-gen/actions/workflows/ci.yml/badge.svg)](https://github.com/jagatsingh/schema-gen/actions/workflows/ci.yml)
[![PyPI version](https://badge.fury.io/py/schema-gen.svg)](https://badge.fury.io/py/schema-gen)
[![Python versions](https://img.shields.io/pypi/pyversions/schema-gen.svg)](https://pypi.org/project/schema-gen/)
[![Documentation Status](https://readthedocs.org/projects/schema-gen/badge/?version=latest)](https://schema-gen.readthedocs.io/en/latest/?badge=latest)

**Universal schema converter for Python - define once, generate everywhere.**

Schema Gen eliminates schema duplication in Python projects by providing a single source of truth for your data models. Define your schemas once using Python type annotations, then generate Pydantic models, SQLAlchemy tables, and other formats automatically.

## 🎯 Why Schema Gen?

### The Problem
In modern Python applications, especially FastAPI projects, you often need to maintain:
- **Pydantic models** for API request/response validation
- **SQLAlchemy models** for database operations  
- **Data processing schemas** for analytics pipelines
- **Multiple variants** of the same model for different use cases

This leads to:
- ❌ **Code duplication** - same fields defined multiple times
- ❌ **Maintenance burden** - changes need to be synchronized across files
- ❌ **Version skew** - models drift out of sync over time
- ❌ **Developer overhead** - mental burden of keeping everything aligned

### The Solution
Schema Gen provides a **single source of truth** approach:
- ✅ **Define once** - write your schema definition in one place
- ✅ **Generate everywhere** - automatically create all required variants
- ✅ **Stay in sync** - generated code is always up-to-date
- ✅ **Version controlled** - generated files are committed to git
- ✅ **Type safe** - full IDE support with type hints and validation

## 🚀 Quick Start

### Installation

```bash
pip install schema-gen
```

### Initialize Your Project

```bash
cd your-project
schema-gen init
```

This creates:
- `schemas/` directory for your schema definitions
- `generated/` directory for generated code  
- `.schema-gen.config.py` configuration file
- Example schema to get you started

### Define Your Schema

Create `schemas/user.py`:

```python
from schema_gen import Schema, Field
from typing import Optional
from datetime import datetime

@Schema
class User:
    """User account schema"""
    
    id: int = Field(
        primary_key=True,
        auto_increment=True,
        description="Unique user identifier"
    )
    
    username: str = Field(
        min_length=3,
        max_length=30,
        regex=r'^[a-zA-Z0-9_]+$',
        unique=True,
        description="Unique username"
    )
    
    email: str = Field(
        format="email",
        unique=True,
        description="User email address"
    )
    
    age: Optional[int] = Field(
        default=None,
        min_value=13,
        max_value=120,
        description="User age"
    )
    
    created_at: datetime = Field(
        auto_now_add=True,
        description="Account creation timestamp"
    )
    
    class Variants:
        # Different model variants for different use cases
        create_request = ['username', 'email', 'age']
        update_request = ['email', 'age'] 
        public_response = ['id', 'username', 'age', 'created_at']
        admin_response = ['id', 'username', 'email', 'age', 'created_at']
```

### Generate Your Models

```bash
schema-gen generate
```

This generates:
- `generated/pydantic/user_models.py` - Complete Pydantic models
- All variants: `User`, `UserCreateRequest`, `UserUpdateRequest`, etc.
- Full type hints, validation, and documentation

### Use in Your FastAPI App

```python
# Import generated models
from generated.pydantic.user_models import (
    User, UserCreateRequest, UserUpdateRequest, 
    UserPublicResponse, UserAdminResponse
)

app = FastAPI()

@app.post("/users", response_model=UserPublicResponse)
async def create_user(user_data: UserCreateRequest):
    # Create user logic
    return UserPublicResponse(...)

@app.get("/users/{user_id}", response_model=UserAdminResponse)
async def get_user(user_id: int, current_user: User = Depends(get_current_admin)):
    # Get user logic  
    return UserAdminResponse(...)
```

## 📖 Core Concepts

### Single Source of Truth
Define your data structure once using the `@Schema` decorator. Schema Gen automatically generates all the different representations you need.

### Field Configuration
Rich field configuration with validation, constraints, and metadata:

```python
name: str = Field(
    min_length=1,
    max_length=100,
    description="User's full name",
    pydantic={"example": "John Doe"}
)
```

### Schema Variants
Create different views of the same schema for different use cases:

```python
class Variants:
    create_request = ['name', 'email']           # For user registration
    update_request = ['name', 'bio']             # For profile updates  
    public_api = ['id', 'name', 'avatar_url']    # For public endpoints
    admin_view = ['id', 'name', 'email', 'role'] # For admin interface
```

### Version Controlled Output
Generated files are committed to your repository, ensuring:
- No runtime dependencies
- Fast application startup
- Easy code review and debugging
- Reliable deployment

## ⚡ Features

### Current Features
- **Pydantic Generation** - Full Pydantic v2 models with validation
- **Schema Variants** - Multiple model variants from single definition
- **Rich Validation** - String, numeric, format, and custom constraints
- **CLI Tools** - Complete command-line interface
- **File Watching** - Auto-regeneration during development
- **Pre-commit Hooks** - Automatic generation in git workflow
- **Type Safety** - Full IDE support and static type checking

### Planned Features
- **SQLAlchemy Generation** - Database models and migrations
- **Pathway Generation** - Data processing schemas
- **GraphQL Support** - Schema and resolver generation
- **OpenAPI Enhancement** - Rich API documentation
- **Custom Generators** - Plugin system for custom formats

## 🛠️ CLI Commands

### `schema-gen init`
Initialize a new project with example configuration and schemas.

```bash
schema-gen init --input-dir schemas --output-dir generated --targets pydantic
```

### `schema-gen generate`
Generate all configured targets from your schema definitions.

```bash
schema-gen generate --config .schema-gen.config.py
```

### `schema-gen watch`  
Watch for schema changes and auto-regenerate (perfect for development).

```bash
schema-gen watch
```

### `schema-gen validate`
Validate that generated files are up-to-date with schema definitions.

```bash
schema-gen validate
```

### `schema-gen install-hooks`
Set up pre-commit hooks for automatic generation.

```bash
schema-gen install-hooks
```

## ⚙️ Configuration

Configure Schema Gen with `.schema-gen.config.py`:

```python
from schema_gen import Config

config = Config(
    input_dir="schemas",
    output_dir="generated", 
    targets=["pydantic"],  # Will support: sqlalchemy, pathway, graphql
    
    # Pydantic-specific settings
    pydantic={
        "use_enum": True,
        "extra": "forbid",
        "validate_assignment": True,
    },
    
    # Future: SQLAlchemy settings
    sqlalchemy={
        "use_declarative": True,
        "naming_convention": "snake_case"
    }
)
```

## 🎨 Use Cases

### FastAPI Applications
- **API Models** - Request/response schemas with validation
- **Database Models** - SQLAlchemy tables that match your API
- **Admin Interfaces** - Extended models with additional fields
- **Public APIs** - Filtered models that hide sensitive data

### Data Processing
- **ETL Pipelines** - Consistent schemas across data transformations  
- **Analytics** - Type-safe data structures for processing
- **ML Models** - Feature definitions and model inputs/outputs
- **Data Validation** - Ensure data quality and consistency

### Microservices
- **Service Contracts** - Shared schemas across service boundaries
- **Event Schemas** - Consistent message formats
- **API Documentation** - Auto-generated, always up-to-date docs
- **Client SDKs** - Generated client libraries

## 📚 Documentation

- **[Schema Format Specification](docs/SCHEMA_FORMAT.md)** - Complete field types and constraints
- **[API Reference](https://schema-gen.readthedocs.io)** - Full API documentation
- **[Examples](examples/)** - Real-world usage examples  
- **[Contributing](CONTRIBUTING.md)** - Development setup and guidelines

## 🤝 Contributing

We welcome contributions! Please see our [Contributing Guide](CONTRIBUTING.md) for details.

### Development Setup

```bash
git clone https://github.com/jagatsingh/schema-gen
cd schema-gen
uv sync --all-extras --dev
uv run pre-commit install
```

### Running Tests

```bash
uv run pytest tests/ -v
```

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- **Pydantic** - For excellent data validation and serialization
- **FastAPI** - For inspiring the need for this tool
- **SQLAlchemy** - For database modeling patterns
- **Click** - For the CLI framework

## 🚀 Coming Soon

- 📊 **SQLAlchemy Generator** - Database models and migrations
- 🔄 **Pathway Integration** - Data processing pipelines
- 📝 **GraphQL Support** - Schema and resolver generation
- 🎯 **Custom Generators** - Plugin system for any format
- 🔍 **IDE Extensions** - Enhanced development experience

---

**Define once, generate everywhere.** Start using Schema Gen today and eliminate schema duplication in your Python projects!