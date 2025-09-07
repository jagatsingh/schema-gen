# Contributing to Schema Gen

We welcome contributions to Schema Gen! This document explains how to get started with development and outlines our contribution guidelines.

## Development Setup

### Prerequisites

- Python 3.10 or higher
- [uv](https://docs.astral.sh/uv/) package manager
- Git

### Getting Started

1. **Fork and clone the repository**
   ```bash
   git clone https://github.com/yourusername/schema-gen.git
   cd schema-gen
   ```

2. **Install dependencies**
   ```bash
   uv sync --all-extras --dev
   ```

3. **Install pre-commit hooks**
   ```bash
   uv run pre-commit install
   ```

4. **Run tests to verify setup**
   ```bash
   uv run pytest tests/ -v
   ```

5. **Try the CLI**
   ```bash
   uv run schema-gen --help
   ```

## Project Structure

```
schema-gen/
├── src/schema_gen/           # Main source code
│   ├── core/                 # Core functionality
│   ├── parsers/              # Schema parsers
│   ├── generators/           # Code generators
│   └── cli/                  # Command-line interface
├── tests/                    # Test suite
├── docs/                     # Documentation
├── .github/workflows/        # CI/CD workflows
└── examples/                 # Usage examples
```

### Key Components

- **`core/schema.py`** - Schema definition API (`@Schema`, `Field()`)
- **`core/usr.py`** - Universal Schema Representation
- **`core/config.py`** - Configuration system
- **`core/generator.py`** - Main generation engine
- **`parsers/`** - Convert Python schemas to USR
- **`generators/`** - Convert USR to target formats
- **`cli/`** - Command-line interface

## Development Workflow

### Making Changes

1. **Create a feature branch**
   ```bash
   git checkout -b feature/my-new-feature
   ```

2. **Make your changes**
   - Write code following our style guidelines
   - Add tests for new functionality
   - Update documentation as needed

3. **Run the test suite**
   ```bash
   uv run pytest tests/ -v
   ```

4. **Run linting and formatting**
   ```bash
   uv run ruff check src/ tests/
   uv run black src/ tests/
   uv run mypy src/
   ```

5. **Test the CLI functionality**
   ```bash
   # Create test project
   mkdir test-project && cd test-project
   uv run schema-gen init
   uv run schema-gen generate
   uv run schema-gen validate
   ```

### Running Tests

We have comprehensive tests covering all functionality:

```bash
# Run all tests
uv run pytest tests/ -v

# Run with coverage
uv run pytest tests/ --cov=src/schema_gen --cov-report=html

# Run specific test files
uv run pytest tests/test_simple.py -v
uv run pytest tests/test_integration.py -v
```

### Documentation

Documentation is built with MkDocs and hosted on ReadTheDocs:

```bash
# Install documentation dependencies
pip install -r docs/requirements.txt

# Serve documentation locally
mkdocs serve

# Build documentation
mkdocs build
```

## Code Style and Standards

### Python Code Style

We use several tools to maintain code quality:

- **Black** - Code formatting
- **Ruff** - Fast linting and import sorting
- **MyPy** - Static type checking
- **Pre-commit** - Automated checks

### Code Guidelines

1. **Type Hints**
   - All functions should have type hints
   - Use `from __future__ import annotations` for forward references
   
   ```python
   def generate_model(schema: USRSchema, variant: str | None = None) -> str:
       """Generate model code from schema."""
   ```

2. **Docstrings**
   - Use Google-style docstrings
   - Document all public functions and classes
   
   ```python
   def parse_schema(self, schema_class: Type) -> USRSchema:
       """Parse a Python schema class into USR format.
       
       Args:
           schema_class: Class decorated with @Schema
           
       Returns:
           USR representation of the schema
           
       Raises:
           ValidationError: If schema is invalid
       """
   ```

3. **Error Handling**
   - Use specific exception types
   - Provide helpful error messages
   - Log errors appropriately

4. **Testing**
   - Write tests for all new functionality
   - Use descriptive test names
   - Test both success and error cases

### Commit Messages

Use conventional commit format:

```
feat: add support for UUID field types
fix: handle optional fields in variant generation
docs: update schema format documentation
test: add integration tests for CLI commands
refactor: simplify type mapping logic
```

## Contributing Guidelines

### Types of Contributions

We welcome several types of contributions:

1. **Bug Reports**
   - Use GitHub issues
   - Include minimal reproduction case
   - Provide environment details

2. **Feature Requests**
   - Discuss in GitHub issues first
   - Explain use case and benefits
   - Consider backward compatibility

3. **Code Contributions**
   - Bug fixes
   - New features
   - Performance improvements
   - Documentation improvements

4. **Documentation**
   - Fix typos and errors
   - Add examples
   - Improve clarity

### Pull Request Process

1. **Before Starting**
   - Check existing issues and PRs
   - Discuss major changes in issues first
   - Make sure tests pass locally

2. **Creating the PR**
   - Use descriptive title and description
   - Reference related issues
   - Include tests for new functionality
   - Update documentation as needed

3. **Review Process**
   - All PRs require review
   - Address feedback constructively
   - Keep PRs focused and reasonably sized

4. **Merging**
   - All tests must pass
   - Code coverage should not decrease
   - Documentation must be updated

### Adding New Generators

To add support for a new target format (e.g., SQLAlchemy, Pathway):

1. **Create generator class**
   ```python
   # src/schema_gen/generators/my_generator.py
   from .base import BaseGenerator
   
   class MyGenerator(BaseGenerator):
       def generate_model(self, schema: USRSchema, variant: str | None = None) -> str:
           # Implementation here
   ```

2. **Add tests**
   ```python
   # tests/test_my_generator.py
   def test_my_generator():
       # Test implementation
   ```

3. **Register in generation engine**
   - Update `SchemaGenerationEngine` to include new generator
   - Add configuration options

4. **Add CLI support**
   - Update target validation
   - Add generator-specific configuration

5. **Update documentation**
   - Add to supported targets list
   - Document configuration options
   - Add usage examples

## Release Process

We follow semantic versioning (SemVer):

- **Patch** (0.1.1) - Bug fixes
- **Minor** (0.2.0) - New features, backward compatible
- **Major** (1.0.0) - Breaking changes

### Creating a Release

1. Update version in `pyproject.toml`
2. Update CHANGELOG.md
3. Create GitHub release
4. Automated CI/CD publishes to PyPI

## Getting Help

- **GitHub Issues** - Bug reports and feature requests
- **GitHub Discussions** - Questions and general discussion
- **Documentation** - https://schema-gen.readthedocs.io/

## Code of Conduct

This project follows the [Contributor Covenant Code of Conduct](https://www.contributor-covenant.org/). By participating, you are expected to uphold this code.

## License

By contributing to Schema Gen, you agree that your contributions will be licensed under the MIT License.