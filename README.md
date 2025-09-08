# Schema Gen

[![CI](https://github.com/jagatsingh/schema-gen/actions/workflows/ci.yml/badge.svg)](https://github.com/jagatsingh/schema-gen/actions/workflows/ci.yml)
[![PyPI version](https://badge.fury.io/py/schema-gen.svg)](https://badge.fury.io/py/schema-gen)
[![Python versions](https://img.shields.io/pypi/pyversions/schema-gen.svg)](https://pypi.org/project/schema-gen/)
[![Documentation Status](https://readthedocs.org/projects/schema-gen/badge/?version=latest)](https://schema-gen.readthedocs.io/en/latest/?badge=latest)

**Universal schema converter - define once, generate everywhere.**

Schema Gen eliminates schema duplication across multiple programming languages and frameworks by providing a single source of truth for your data models. Define your schemas once using Python type annotations, then automatically generate code for 12+ different targets.

## 🎯 Supported Generators (12)

### Python Ecosystem
- **Pydantic** - Python models with validation
- **SQLAlchemy** - Database ORM models
- **Dataclasses** - Python standard library dataclasses
- **TypedDict** - Python typing dictionaries
- **Pathway** - Data processing schemas

### TypeScript/JavaScript
- **Zod** - TypeScript runtime validation

### Schema Formats
- **JSON Schema** - Standard JSON schema validation
- **GraphQL** - GraphQL Schema Definition Language
- **Protobuf** - Protocol Buffers with gRPC services
- **Avro** - Apache Avro schemas

### JVM Languages
- **Jackson** - Java classes with JSON annotations
- **Kotlin** - Kotlin data classes with kotlinx.serialization

## 🎯 Why Schema Gen?

If the struggle of maintaining multiple schema definitions across your polyglot applications sounds familiar, Schema Gen is here to help! Countless hours are wasted on mismatched field names, inconsistent validation rules, and keeping schemas synchronized across different programming languages.

### The Problem
In modern polyglot applications, you often need to maintain:
- **Pydantic models** for Python API validation
- **SQLAlchemy models** for database operations
- **TypeScript interfaces** for frontend applications
- **Java DTOs** for enterprise services
- **Protobuf schemas** for microservice communication
- **JSON schemas** for API documentation
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
uv pip install schema-gen
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

This generates code for all configured targets:
- `generated/pydantic/user_models.py` - Python Pydantic models
- `generated/sqlalchemy/user_models.py` - SQLAlchemy ORM models
- `generated/zod/user.ts` - TypeScript Zod schemas
- `generated/jackson/User.java` - Java classes with Jackson annotations
- `generated/kotlin/User.kt` - Kotlin data classes
- `generated/protobuf/user.proto` - Protocol Buffer definitions
- `generated/avro/user.avsc` - Apache Avro schemas
- `generated/jsonschema/user.json` - JSON Schema validation
- `generated/graphql/user.graphql` - GraphQL SDL
- All variants: `User`, `UserCreateRequest`, `UserUpdateRequest`, etc.
- Full type hints, validation, and documentation

### Use Across Multiple Languages

**Python FastAPI:**
```python
# Import generated models
from generated.pydantic.user_models import (
    User, UserCreateRequest, UserPublicResponse
)

@app.post("/users", response_model=UserPublicResponse)
async def create_user(user_data: UserCreateRequest):
    return UserPublicResponse(...)
```

**TypeScript Frontend:**
```typescript
// Import generated Zod schemas
import { UserCreateRequestSchema, UserPublicResponseSchema } from './generated/zod/user';

// Validate API responses
const user = UserPublicResponseSchema.parse(apiResponse);
```

**Java Spring Boot:**
```java
// Import generated Jackson models
import com.example.user.User;
import com.example.user.UserCreateRequest;

@PostMapping("/users")
public User createUser(@Valid @RequestBody UserCreateRequest request) {
    return userService.create(request);
}
```

**Kotlin Service:**
```kotlin
// Import generated Kotlin data classes
import com.example.user.User
import com.example.user.UserCreateRequest

fun createUser(request: UserCreateRequest): User {
    return userRepository.save(request)
}
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

### Custom Code Injection
Add complex validation logic and business methods to your generated models:
```python
class PydanticMeta:
    imports = ["import math", "from pydantic import field_validator"]

    raw_code = '''
    @field_validator("price", mode="before")
    def clean_price_data(cls, value) -> float:
        # Handle NaN, infinity, and string values from data feeds
        if isinstance(value, str) and value.lower() == 'nan':
            return 0.0
        return float(value)'''

    methods = '''
    def calculate_total_value(self, quantity: int) -> float:
        return self.price * quantity'''
```

Future generators will use their own meta classes:
- `SQLAlchemyMeta` for database-specific customizations
- `PathwayMeta` for streaming data processing

### Version Controlled Output
Generated files are committed to your repository, ensuring:
- No runtime dependencies
- Fast application startup
- Easy code review and debugging
- Reliable deployment

## ⚡ Features

### Current Features
- **12+ Generators** - Python, TypeScript, Java, Kotlin, and schema formats
- **Multi-language Support** - Single schema → multiple programming languages
- **Schema Variants** - Multiple model variants from single definition
- **Custom Code Injection** - Add custom validators, methods, and business logic
- **Rich Validation** - String, numeric, format, and custom constraints
- **Type Safety** - Full IDE support across all target languages
- **Professional Code Generation** - Proper imports, documentation, conventions
- **CLI Tools** - Complete command-line interface
- **File Watching** - Auto-regeneration during development
- **Pre-commit Hooks** - Automatic generation in git workflow

### Planned Features
- **OpenAPI/Swagger** - REST API specifications
- **Great Expectations** - Data validation schemas
- **Terraform** - Infrastructure as Code schemas
- **Rust Serde** - Rust serialization support
- **C# Records** - .NET ecosystem support
- **Go Structs** - Go language support
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
        "validate_assignment": True,
    },

    sqlalchemy={
        "use_declarative": True,
        "naming_convention": "snake_case"
    }
)
```

## 🎨 Use Cases

### Polyglot Applications
- **Full-stack Development** - Frontend TypeScript + Backend Python/Java/Kotlin
- **API Contracts** - Consistent models across multiple services
- **Database Schemas** - SQLAlchemy models that match your APIs
- **Type Safety** - End-to-end type checking across languages

### Microservices Architecture
- **Service Contracts** - Shared schemas across service boundaries
- **Protocol Buffers** - High-performance gRPC communication
- **Event Schemas** - Consistent message formats with Avro
- **API Documentation** - Auto-generated OpenAPI/GraphQL specs

### Data Engineering
- **ETL Pipelines** - Pathway schemas for data processing
- **Analytics** - Type-safe data structures across languages
- **ML Models** - Feature definitions and model inputs/outputs
- **Data Validation** - JSON Schema and Great Expectations rules

### Enterprise Development
- **Java Spring Boot** - Jackson-annotated DTOs with validation
- **Kotlin Services** - Data classes with kotlinx.serialization
- **Legacy Integration** - Protocol Buffers for system communication
- **Cross-platform SDKs** - Generated client libraries

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

- 📝 **OpenAPI/Swagger** - Complete REST API specifications
- 📊 **Great Expectations** - Data quality validation schemas
- 🏗️ **Terraform** - Infrastructure as Code schema validation
- 🦀 **Rust Serde** - High-performance Rust serialization
- 🔷 **C# Records** - .NET ecosystem data models
- 🐹 **Go Structs** - Go language struct generation
- 🎯 **Custom Generators** - Plugin system for any format
- 🔍 **IDE Extensions** - Enhanced development experience

---

**Define once, generate everywhere.** Start using Schema Gen today and eliminate schema duplication across your entire technology stack!
