# Dependency Management System

This document describes the automated dependency management system for schema-gen, ensuring all Python libraries and external compilers are kept up to date with comprehensive validation.

## 📊 Current Dependencies

### Python Libraries (8 formats - 67% coverage)
| Library | Current | Min Required | Purpose | Critical |
|---------|---------|--------------|---------|----------|
| **pydantic** | 2.11.7 | ≥2.0 | Data validation using type annotations | ✅ |
| **sqlalchemy** | 2.0.43 | ≥2.0 | SQL toolkit and ORM library | ✅ |
| **jsonschema** | 4.25.1 | ≥4.0 | JSON Schema validation | ✅ |
| **graphql-core** | 3.2.6 | ≥3.2 | GraphQL implementation for Python | ✅ |
| **avro-python3** | 1.10.2 | ≥1.11 | Apache Avro serialization | ✅ |
| **pathway** | 0.26.1 | ≥0.7 | Data processing framework | ✅ |

### External Compilers (4 formats - 33% coverage)
| Compiler | Current | Purpose | Critical |
|----------|---------|---------|----------|
| **TypeScript** | 5.9.2 | Zod validation compilation | ✅ |
| **Node.js** | v20.19.2 | TypeScript runtime | ✅ |
| **Java JDK** | 21.0.8 | Jackson validation compilation | ✅ |
| **Kotlin** | v2.0.21 | Data class validation compilation | ✅ |
| **Protobuf** | 3.21.12 | Multi-language schema compilation | ✅ |

### External Libraries
| Library | Current | Purpose |
|---------|---------|---------|
| **Jackson Core** | 2.18.0 | JSON processing for Java |
| **kotlinx.serialization** | 1.6.2 | Kotlin serialization support |

## 🤖 Automated Update System

### 1. Dependency Monitoring
- **Schedule**: Weekly checks every Monday at 9 AM UTC
- **Trigger**: Manual workflow dispatch or file changes
- **Monitoring**: GitHub Actions workflow `dependency-check.yml`

### 2. Update Detection
The system checks for updates using:
- **Python Libraries**: PyPI API for latest versions
- **External Compilers**: GitHub Releases API and registry APIs
- **External Libraries**: Maven Central search API

### 3. Automated Actions
When updates are detected:
1. **Issue Creation**: Auto-creates/updates GitHub issue with update details
2. **Version Comparison**: Uses semantic versioning for accurate comparison
3. **Impact Assessment**: Categorizes updates by criticality
4. **Testing Validation**: Ensures Docker build still works

## 📁 Key Files

### Configuration Files
- **`dependencies.json`** - Central dependency configuration
- **`Dockerfile.validation`** - External compiler versions
- **`pyproject.toml`** - Python library constraints

### Automation Scripts
- **`scripts/check_dependency_versions.py`** - Version checking and reporting
- **`scripts/update_dependencies.py`** - Automated update execution
- **`.github/workflows/dependency-check.yml`** - CI/CD automation

## 🔧 Usage

### Manual Dependency Check
```bash
# Check all dependency versions
python scripts/check_dependency_versions.py

# Generate detailed report
python scripts/check_dependency_versions.py > dependency_report.txt
```

### Manual Updates
```bash
# Update dependencies automatically
python scripts/update_dependencies.py

# Update without Docker build test
python scripts/update_dependencies.py --no-test
```

### GitHub Actions
The dependency check workflow runs automatically:
- **Weekly**: Every Monday at 9 AM UTC
- **On Changes**: When Dockerfile.validation or pyproject.toml changes
- **Manual**: Via workflow_dispatch

## 📈 Update Strategy

### Critical Dependencies (Auto-monitored)
- **Python validation libraries** - Essential for format validation
- **External compilers** - Required for compilation testing
- **Security updates** - Applied immediately

### Development Tools (Auto-updated)
- **pytest, ruff, mypy** - Development and testing tools
- **Non-critical utilities** - Updated automatically

### Update Process
1. **Detection**: Automated weekly scans
2. **Validation**: Docker build and validation tests
3. **Notification**: GitHub issue with update details
4. **Manual Review**: Human approval for critical updates
5. **Application**: Automated or manual update application

## 🧪 Validation Requirements

Before applying any dependency updates, the system validates:

### Python Library Updates
- ✅ Import and basic functionality tests
- ✅ Generated code syntax validation
- ✅ Library-specific validation (e.g., Pydantic model creation)

### External Compiler Updates
- ✅ Compilation success with generated code
- ✅ Multi-format output validation (Protobuf: Python + C++ + Java)
- ✅ Library integration (Jackson, kotlinx.serialization)

### Docker Environment
- ✅ Complete Docker build success
- ✅ All compiler validation tests pass
- ✅ Comprehensive format validation (12/12 formats)

## 🚨 Rollback Strategy

If updates cause issues:
1. **Immediate**: Revert Dockerfile.validation changes
2. **Testing**: Run validation suite to confirm fix
3. **Documentation**: Update issue with rollback details
4. **Investigation**: Analyze compatibility issues

## 📊 Success Metrics

### Current Achievement
- **Total Formats**: 12
- **Validation Coverage**: 100% (12/12)
- **Python Library Coverage**: 67% (8/12 formats)
- **External Compiler Coverage**: 33% (4/12 formats)
- **Overall Success Rate**: 100% validation success

### Target Metrics
- **Update Detection**: < 1 week lag time
- **Update Application**: < 1 day for critical security updates
- **Validation Success**: 100% format validation after updates
- **Docker Build Success**: 100% after dependency changes

## 🔍 Troubleshooting

### Common Issues

**Dependency Check Fails**
- Check network connectivity to PyPI/GitHub APIs
- Verify API rate limits not exceeded
- Review authentication if required

**Docker Build Fails After Update**
- Check for breaking changes in updated dependencies
- Verify compatibility between library versions
- Review Dockerfile syntax for URL/version changes

**Validation Tests Fail**
- Compare generated code before/after update
- Check for API changes in updated libraries
- Validate external compiler compatibility

### Support Commands
```bash
# Test current environment
docker run --rm schema-gen-validation:latest validate-compilers

# Validate specific format
python scripts/validate_all_formats.py --format pydantic --verbose

# Check Docker build
docker build -f Dockerfile.validation -t test-build .
```

## 🎯 Future Enhancements

### Planned Features
- **Automated PRs**: Auto-create pull requests for updates
- **Security Scanning**: Automated vulnerability detection
- **Performance Monitoring**: Track validation performance changes
- **Notification Integration**: Slack/email notifications for updates

### Version Pinning Strategy
- **Major versions**: Manual review required
- **Minor versions**: Automated with validation
- **Patch versions**: Automated for security fixes
- **Pre-release versions**: Never automated

---

**🎉 The dependency management system ensures schema-gen stays current with the latest libraries and compilers while maintaining 100% validation success across all 12 supported formats.**
