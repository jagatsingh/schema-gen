# CLI Reference

Schema Gen provides a comprehensive command-line interface for managing your schemas and generated code.

## Global Options

All commands support these global options:

- `--help` - Show help message and exit
- `--version` - Show version and exit

## Commands

### `schema-gen init`

Initialize a new Schema Gen project in the current directory.

```bash
schema-gen init [OPTIONS]
```

**Options:**
- `--input-dir TEXT` - Input directory for schemas (default: `schemas/`)
- `--output-dir TEXT` - Output directory for generated files (default: `generated/`)
- `--targets TEXT` - Comma-separated list of targets (default: `pydantic`)
  Available targets: `pydantic`, `sqlalchemy`, `dataclasses`, `typeddict`, `pathway`, `zod`, `jsonschema`, `graphql`, `protobuf`, `avro`, `jackson`, `kotlin`

**Example:**
```bash
schema-gen init --input-dir src/schemas --output-dir src/generated --targets pydantic,jackson,kotlin
```

**What it creates:**
- Input directory with example schema
- Output directory structure
- Configuration file (`.schema-gen.config.py`)
- Pre-configured settings for your targets

### `schema-gen generate`

Generate all configured targets from your schema definitions.

```bash
schema-gen generate [OPTIONS]
```

**Options:**
- `-i, --input TEXT` - Input directory containing schemas
- `-o, --output TEXT` - Output directory for generated files
- `-t, --target TEXT` - Target generators to run (can be used multiple times)
- `-c, --config TEXT` - Path to config file (default: `.schema-gen.config.py`)

**Examples:**
```bash
# Use configuration file settings
schema-gen generate

# Override specific options
schema-gen generate --input src/schemas --output src/generated

# Generate only specific targets
schema-gen generate --target pydantic --target sqlalchemy

# Use different config file
schema-gen generate --config .schema-gen.prod.config.py
```

**Output:**
- Generated model files for each target
- Package initialization files
- Import statements and exports

### `schema-gen watch`

Watch for schema changes and automatically regenerate models. Perfect for development.

```bash
schema-gen watch [OPTIONS]
```

**Options:**
- `-i, --input TEXT` - Input directory containing schemas
- `-o, --output TEXT` - Output directory for generated files
- `-c, --config TEXT` - Path to config file (default: `.schema-gen.config.py`)

**Example:**
```bash
schema-gen watch --config .schema-gen.dev.config.py
```

**Features:**
- Watches schema files for changes
- Watches config file for changes
- Debounced regeneration (1 second delay)
- Graceful shutdown with Ctrl+C
- Real-time feedback on changes

### `schema-gen validate`

Validate that generated schemas are up-to-date with source definitions.

```bash
schema-gen validate [OPTIONS]
```

**Options:**
- `-c, --config TEXT` - Path to config file (default: `.schema-gen.config.py`)

**Example:**
```bash
schema-gen validate
```

**Checks:**
- Generated directories exist
- All configured targets are present
- Models can be imported successfully
- No syntax errors in generated code

**Exit codes:**
- `0` - All schemas are up-to-date
- `1` - Validation failed or schemas are out-of-date

### `schema-gen install-hooks`

Install pre-commit hooks for automatic schema generation.

```bash
schema-gen install-hooks [OPTIONS]
```

**Options:**
- `--install-pre-commit/--no-install-pre-commit` - Install pre-commit package (default: `true`)

**Example:**
```bash
# Install hooks and pre-commit package
schema-gen install-hooks

# Only create config, don't install pre-commit
schema-gen install-hooks --no-install-pre-commit
```

**What it does:**
- Creates `.pre-commit-config.yaml` with schema-gen hooks
- Optionally installs `pre-commit` package
- Installs the hooks in your git repository
- Sets up automatic generation on schema changes

## Configuration Priority

Schema Gen uses the following priority order for configuration:

1. **Command-line arguments** (highest priority)
2. **Configuration file** (`.schema-gen.config.py`)
3. **Default values** (lowest priority)

This allows you to:
- Set project defaults in the config file
- Override settings for specific commands
- Use different configs for different environments

## Exit Codes

All commands follow standard Unix exit code conventions:

- `0` - Success
- `1` - General error (validation failed, generation error, etc.)
- `2` - Command-line usage error (invalid arguments)

## Examples

### Basic Workflow
```bash
# Initialize project
schema-gen init

# Edit schemas in schemas/ directory
# ...

# Generate models
schema-gen generate

# Validate everything is up-to-date
schema-gen validate
```

### Development Workflow
```bash
# Set up pre-commit hooks
schema-gen install-hooks

# Start watching for changes
schema-gen watch

# In another terminal, edit schemas
# Models regenerate automatically
```

### CI/CD Integration
```bash
# Validate in CI pipeline
schema-gen validate || exit 1

# Generate fresh models
schema-gen generate

# Check for uncommitted changes
git diff --exit-code generated/ || {
    echo "Generated models are out of date"
    exit 1
}
```

### Multi-Environment Setup
```bash
# Development config
schema-gen generate --config .schema-gen.dev.config.py

# Production config
schema-gen generate --config .schema-gen.prod.config.py

# Testing with different targets
schema-gen generate --target pydantic --output test_generated
```
