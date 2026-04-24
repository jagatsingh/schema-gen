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
  Available targets: `pydantic`, `sqlalchemy`, `dataclasses`, `typeddict`, `pathway`, `zod`, `jsonschema`, `graphql`, `protobuf`, `avro`, `jackson`, `kotlin`, `rust`, `docs`

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

### `schema-gen diff`

Detect breaking changes by comparing current JSON Schema output against a baseline (git branch, tag, commit, or directory snapshot). Inspired by [buf breaking](https://buf.build/docs/breaking/rules/).

```bash
schema-gen diff [OPTIONS]
```

**Options:**
- `--against TEXT` - **(required)** Baseline reference:
  - `.git#branch=main` — compare against a git branch
  - `.git#tag=v1.0.0` — compare against a git tag
  - `.git#commit=abc123` — compare against a specific commit
  - `/path/to/snapshot/` — compare against a directory of JSON Schema files
- `--level [WIRE|WIRE_JSON|SOURCE]` - Strictness level (default: `WIRE_JSON`)
- `--format [text|json|github]` - Output format (default: `text`)
- `--ignore TEXT` - Suppress a specific rule (repeatable)
- `-c, --config TEXT` - Path to config file (default: `.schema-gen.config.py`)

**Prerequisites:**
- `jsonschema` must be in your configured `targets`
- JSON Schema output must be committed to version control

**Examples:**
```bash
# Compare against main branch
schema-gen diff --against .git#branch=main

# Use WIRE level (serialization-breaking only)
schema-gen diff --against .git#tag=v1.0.0 --level WIRE

# JSON output for CI parsing
schema-gen diff --against .git#branch=main --format json

# GitHub Actions annotations (inline PR comments)
schema-gen diff --against .git#branch=main --format github

# Suppress a known intentional break
schema-gen diff --against .git#branch=main --ignore FIELD_NO_DELETE
```

**Strictness levels:**

| Level | What it checks |
|-------|---------------|
| `WIRE` | Serialization-breaking: deleted types/fields, type changes, narrowed types, new required fields, removed enum variants |
| `WIRE_JSON` | WIRE + JSON key identity: field renames, enum value name changes |
| `SOURCE` | Reserved for future use (field ordering, namespace changes) |

**Rules:**

| Rule | Level | Description |
|------|-------|-------------|
| `TYPE_NO_DELETE` | WIRE | Schema type was removed |
| `FIELD_NO_DELETE` | WIRE | Field was removed from a schema |
| `FIELD_SAME_TYPE` | WIRE | Field type changed incompatibly |
| `FIELD_TYPE_NARROWED` | WIRE | Numeric type narrowed (e.g. number to integer) |
| `FIELD_REQUIRED_ADDED` | WIRE | New required field added |
| `ENUM_VALUE_NO_DELETE` | WIRE | Enum variant was removed |
| `FIELD_SAME_NAME` | WIRE_JSON | Field appears to have been renamed |
| `ENUM_VALUE_SAME_NAME` | WIRE_JSON | Enum value changed at same position |

**Always safe (never flagged):**
- Adding a new optional field
- Adding a new enum variant
- Adding a new schema type
- Adding a new schema file
- Widening a numeric type (integer to number)

**Exit codes:**
- `0` — No breaking changes
- `1` — Breaking changes detected
- `2` — Tool error (e.g. baseline not found)

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

### Breaking Change Detection
```bash
# Check for breaking schema changes on every PR
schema-gen diff --against .git#branch=main

# Use in CI with JSON output
schema-gen diff --against .git#branch=main --format json

# Allow a known intentional break
schema-gen diff --against .git#branch=main --ignore FIELD_NO_DELETE
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
