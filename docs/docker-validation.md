# 🐳 Comprehensive Docker-Based Validation System

This document provides an overview of the complete Docker-based validation system for schema-gen, which tests all generated formats with real external compilers.

## 🎯 Overview

The validation system ensures that **all 12 supported formats** generate syntactically correct, functionally valid code by testing with actual compilers and runtime environments.

### Supported Formats Validated

✅ **Python Formats**
- Pydantic v2 Models (with BaseModel validation)
- SQLAlchemy ORM Models (with Table/Column validation)
- Python Dataclasses (with proper field ordering)
- TypedDict Definitions (with type checking)
- Pathway Schemas (with connector validation)

✅ **External Language Formats**
- **Zod TypeScript Schemas** → Validated with TypeScript compiler (tsc)
- **Jackson Java POJOs** → Validated with Java compiler (javac) + Jackson libs
- **Kotlin Data Classes** → Validated with Kotlin compiler (kotlinc)
- **Protocol Buffer Messages** → Validated with protoc compiler

✅ **Schema Definition Formats**
- JSON Schema Documents (with draft validation)
- GraphQL Type Definitions (with GraphQL validation)
- Apache Avro Schemas (with Avro validation)

## 🛠️ Quick Start

### 1. Build & Run Comprehensive Validation

```bash
# Build Docker validation environment
make docker-build

# Run complete validation with all external compilers
make docker-test
```

### 2. Interactive Development

```bash
# Start interactive Docker environment
make docker-dev

# Inside container:
validate-compilers    # Test all compilers
test-all-formats-docker # Run comprehensive validation
```

### 3. Format-Specific Testing

```bash
# Test specific formats with external compilers
make docker-format-test

# Test individual formats
docker run --rm -v $PWD:/app schema-gen-validation \
  uv run python scripts/validate_all_formats.py --format zod --verbose
```

## 🏗️ Architecture

### Docker Environment (`Dockerfile.validation`)

**Base**: Python 3.13 slim with comprehensive toolchain:

```dockerfile
# External Compilers
- Node.js + TypeScript compiler (tsc)
- OpenJDK 17 + Java compiler (javac)
- Kotlin compiler (kotlinc)
- Protocol Buffers compiler (protoc)

# Java Libraries
- Jackson Core, Databind, Annotations
- Bean Validation API + Hibernate Validator

# Python Environment
- uv package manager
- pytest, ruff, mypy development tools
```

### Multi-Level Validation Strategy

#### 1. **Syntax Validation**
```python
# Python AST parsing
ast.parse(generated_code)

# External compiler validation
subprocess.run(["tsc", "--noEmit", "schema.ts"])
subprocess.run(["javac", "-cp", "libs/*", "Schema.java"])
subprocess.run(["kotlinc", "Schema.kt"])
subprocess.run(["protoc", "schema.proto"])
```

#### 2. **Functional Validation**
```python
# Code execution testing
import generated_module
instance = generated_module.Model(**test_data)

# Cross-format consistency
assert all_formats_have_same_fields()
assert all_formats_handle_optionals_consistently()
```

#### 3. **Structure Validation**
```python
# Format-specific checks
assert "BaseModel" in pydantic_code
assert "data class" in kotlin_code
assert '"$schema"' in json_schema
assert "type Query {" in graphql_schema
```

## 🚀 CI/CD Integration

### GitHub Actions Workflows

#### 1. **Comprehensive Test Workflow** (`.github/workflows/comprehensive-test.yml`)

**Multi-Matrix Validation:**
```yaml
Strategy Matrix:
  - Quick validation (Python only)
  - Docker validation (all compilers)
  - Multi-Python (3.11, 3.12, 3.13)
  - Performance testing
  - Cross-platform (Linux, Windows, macOS)
```

**Daily Scheduled Runs:**
- Comprehensive validation at 6 AM UTC
- Performance regression testing
- Cross-platform compatibility checks

#### 2. **Publication Workflow** (`.github/workflows/publish.yml`)

**Pre-Publication Validation:**
```bash
# Standard tests + Docker comprehensive validation
uv run pytest tests/ --cov-fail-under=65
docker run schema-gen-validation test-all-formats-docker
```

### Local Development Integration

#### Makefile Commands
```bash
# Development workflow
make dev              # Setup development environment
make test             # Run standard tests
make validate         # Run format validation
make docker-test      # Full Docker validation

# Quality assurance
make lint             # Code linting
make type-check       # Type checking
make quality          # All quality checks

# CI simulation
make ci-test          # Simulate CI locally
make ci-docker        # Simulate CI with Docker
```

## 🔧 Available Commands

### In Docker Container

```bash
# Compiler validation
validate-compilers              # Test all external compilers

# Comprehensive testing
test-all-formats-docker        # Complete validation suite
dev-setup                      # Setup development environment

# Manual testing
uv run pytest tests/test_format_validation.py -v
uv run python scripts/validate_all_formats.py --verbose
bash scripts/test_all_formats.sh
```

### Format-Specific Testing

```bash
# Single format validation
uv run python scripts/validate_all_formats.py --format zod
uv run python scripts/validate_all_formats.py --format jackson
uv run python scripts/validate_all_formats.py --format kotlin

# Multiple specific formats
uv run python scripts/validate_all_formats.py --formats pydantic dataclasses
```

## 📊 Validation Results

### Success Metrics Achieved

**✅ 100% Format Validation Success Rate**
- All 12 formats generate valid, compilable code
- 19/19 pytest validation tests pass
- External compiler integration works correctly

**✅ Comprehensive Coverage**
```
Format Validation: 12/12 ✅
Python Versions: 3.11, 3.12, 3.13 ✅
Operating Systems: Linux, Windows, macOS ✅
External Compilers: TypeScript, Java, Kotlin, Protoc ✅
```

### Validation Report Example
```
🔍 Starting format validation...
📋 Test schema: ValidationTestUser
📝 Fields: 7

Validating pydantic... ✅ VALID
Validating sqlalchemy... ✅ VALID
Validating dataclasses... ✅ VALID
Validating typeddict... ✅ VALID
Validating pathway... ✅ VALID
Validating zod... ✅ VALID
Validating jsonschema... ✅ VALID
Validating graphql... ✅ VALID
Validating protobuf... ✅ VALID
Validating avro... ✅ VALID
Validating jackson... ✅ VALID
Validating kotlin... ✅ VALID

Valid formats: 12/12
Overall success rate: 100.0%
🎉 All formats validated successfully!
```

## 🔍 Troubleshooting

### Common Issues

**Docker Build Problems:**
```bash
# Clean rebuild
make clean-docker
make docker-build
```

**Compiler Issues:**
```bash
# Test compilers inside container
docker run --rm schema-gen-validation validate-compilers
```

**Permission Problems:**
```bash
# Fix file permissions
docker run --rm -v $PWD:/app schema-gen-validation \
  chown -R $(id -u):$(id -g) /app
```

### Debug Mode

```bash
# Interactive debugging
docker run -it --rm -v $PWD:/app schema-gen-validation /bin/bash

# Check individual format
uv run python scripts/validate_all_formats.py --format pydantic --verbose
```

## 📈 Performance & Optimization

### Build Optimization
- **Layer Caching**: Dependencies cached separately from source code
- **Multi-stage Builds**: Optimized for development vs runtime
- **Volume Caching**: Persistent caches for uv, pip, npm

### Validation Speed
```
Quick Validation: ~30 seconds (Python only)
Docker Validation: ~3-5 minutes (all compilers)
Comprehensive Suite: ~8-12 minutes (full matrix)
```

## 🔒 Security Considerations

- Container runs as root (development convenience)
- Only mount trusted source code
- Network access required for dependency downloads
- Not suitable for production deployment

## 🚀 Future Enhancements

### Planned Improvements
- [ ] Multi-architecture builds (ARM64 support)
- [ ] Language-specific validation containers
- [ ] Integration test data generation
- [ ] Performance benchmarking suite
- [ ] Validation result caching

### Contributing

To extend the validation system:

1. **Add New Compiler**: Update `Dockerfile.validation`
2. **Add New Format**: Extend `scripts/validate_all_formats.py`
3. **Add New Test**: Add to `tests/test_format_validation.py`
4. **Update CI**: Modify workflow files as needed

---

This Docker-based validation system ensures **schema-gen generates production-ready, valid code** across all supported formats with **real-world compiler validation**. The comprehensive testing approach provides confidence that generated code works in actual development environments. 🎉
