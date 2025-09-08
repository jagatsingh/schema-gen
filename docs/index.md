# Schema Gen Documentation

Welcome to Schema Gen - the schema generator for Python!

Schema Gen eliminates schema duplication in Python projects by providing a single source of truth for your data models. Define your schemas once using Python type annotations, then generate Pydantic models, SQLAlchemy tables, and other formats automatically.

## Quick Navigation

- **[Getting Started](getting-started.md)** - Installation and your first schema
- **[Schema Format](schema-format.md)** - Complete field types and constraints reference
- **[CLI Reference](cli-reference.md)** - All command-line tools
- **[Configuration](configuration.md)** - Project configuration options
- **[Examples](examples.md)** - Real-world usage examples
- **[API Reference](api-reference.md)** - Python API documentation

## Why Schema Gen?

### The Problem
In modern Python applications, especially FastAPI projects, you often need to maintain:
- **Pydantic models** for API request/response validation
- **SQLAlchemy models** for database operations
- **Data processing schemas** for analytics pipelines
- **Multiple variants** of the same model for different use cases

This leads to code duplication, maintenance burden, and version skew.

### The Solution
Schema Gen provides a **single source of truth** approach:
- ✅ **Define once** - write your schema definition in one place
- ✅ **Generate everywhere** - automatically create all required variants
- ✅ **Stay in sync** - generated code is always up-to-date
- ✅ **Version controlled** - generated files are committed to git
- ✅ **Type safe** - full IDE support with type hints and validation

## Features

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

## Get Started

Ready to eliminate schema duplication in your project? Head over to [Getting Started](getting-started.md) to begin!
