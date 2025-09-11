# Publishing to PyPI

This document explains how to publish schema-gen to PyPI using the automated workflows and manual methods.

## 📦 Publishing Methods

### Method 1: Git Tags (Recommended)

The easiest way to publish is by creating a git tag:

```bash
# 1. Update version in pyproject.toml
sed -i 's/version = "[^"]*"/version = "0.1.1"/' pyproject.toml

# 2. Commit the version bump
git add pyproject.toml
git commit -m "bump: version 0.1.1"

# 3. Create and push a tag
git tag v0.1.1
git push origin v0.1.1
```

This will automatically:
- ✅ Run comprehensive tests and compatibility checks
- ✅ Build the package with strict validation
- ✅ Publish to PyPI (for stable versions) or Test PyPI (for alpha/beta)
- ✅ Create a GitHub release with changelog
- ✅ Verify the publication worked

### Method 2: GitHub Actions Manual Dispatch

You can also publish manually through GitHub Actions:

1. Go to **Actions** → **Publish to PyPI**
2. Click **Run workflow**
3. Choose options:
   - **Version**: e.g., `0.1.1` (optional - leave empty to use current)
   - **Target**: `test-pypi`, `pypi`, or `both`
4. Click **Run workflow**

### Method 3: GitHub Releases

Create a release through the GitHub web interface:

1. Go to **Releases** → **Create a new release**
2. Create a new tag (e.g., `v0.1.1`)
3. Write release notes
4. Click **Publish release**

This triggers the same automated publication workflow.

## 🎯 Publication Targets

### PyPI (Production)

**Automatic triggers:**
- Git tags: `v1.0.0`, `v1.2.3` (no pre-release identifiers)
- GitHub releases: Any published release
- Manual dispatch: When `target=pypi` or `target=both`

**Requirements:**
- All tests must pass (>80% coverage)
- All generators must pass compatibility tests
- Package must pass `twine check --strict`
- CLI functionality must work correctly

### Test PyPI (Testing)

**Automatic triggers:**
- Git tags: `v1.0.0-alpha.1`, `v1.0.0-beta.1` (with pre-release identifiers)
- Manual dispatch: When `target=test-pypi` or `target=both`

**Use cases:**
- Testing the publication process
- Validating package installation
- Pre-release testing

## 🛡️ Security & Trust

### Trusted Publishing

This project uses **PyPI Trusted Publishing** with GitHub Actions:

- ✅ **No API tokens required** - uses OIDC authentication
- ✅ **Automatic security** - GitHub manages credentials
- ✅ **Audit trail** - all publications tracked in GitHub Actions

### Environment Protection

Both PyPI environments have protection rules:
- **Manual approval** required for production PyPI
- **Environment secrets** managed securely
- **Deployment logs** available for audit

## 🔧 Manual Publishing (Local)

If you need to publish manually from your local machine:

### Prerequisites

1. **Install dependencies:**
   ```bash
   uv sync --all-extras --dev
   ```

2. **Set up PyPI API token:**
   ```bash
   # Get token from https://pypi.org/manage/account/token/
   export TWINE_USERNAME=__token__
   export TWINE_PASSWORD=pypi-your-api-token-here
   ```

### Build and Publish

```bash
# 1. Run tests
uv run pytest tests/ -v --cov=src/schema_gen --cov-fail-under=80

# 2. Test all generators
uv run python scripts/check_compatibility.py --library all-generators

# 3. Run linting
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/

# 4. Test CLI
uv run schema-gen --help

# 5. Build package
uv build

# 6. Check package
uv run twine check dist/* --strict

# 7. Test installation
pip install dist/*.whl
python -c "import schema_gen; print(schema_gen.__version__)"

# 8. Publish to Test PyPI (testing)
uv run twine upload --repository testpypi dist/*

# 9. Test install from Test PyPI
pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ schema-gen

# 10. Publish to PyPI (production)
uv run twine upload dist/*
```

## 📋 Pre-Publication Checklist

Before publishing, ensure:

### ✅ Code Quality
- [ ] All tests pass (`uv run pytest tests/ -v`)
- [ ] Coverage ≥80% (`--cov-fail-under=80`)
- [ ] All generators work (`check_compatibility.py`)
- [ ] Linting passes (`ruff check`)
- [ ] Formatting is correct (`ruff format --check`)

### ✅ Package Configuration
- [ ] Version updated in `pyproject.toml`
- [ ] Dependencies are current and correct
- [ ] README.md is comprehensive and up-to-date
- [ ] License is properly specified
- [ ] Author information is correct

### ✅ CLI Functionality
- [ ] `schema-gen --help` works
- [ ] `schema-gen --version` shows correct version
- [ ] `schema-gen init` creates proper project structure
- [ ] `schema-gen generate` produces valid output
- [ ] `schema-gen validate` works correctly

### ✅ Documentation
- [ ] README has installation instructions
- [ ] Examples are tested and working
- [ ] API documentation is current
- [ ] Changelog is updated (for major releases)

## 🚀 Version Strategy

### Semantic Versioning

Schema-gen follows [Semantic Versioning](https://semver.org/):

- **Major** (`1.0.0`): Breaking changes
- **Minor** (`0.1.0`): New features, backward compatible
- **Patch** (`0.0.1`): Bug fixes, backward compatible

### Pre-release Versions

For testing and development:

- **Alpha** (`1.0.0-alpha.1`): Early development, may be unstable
- **Beta** (`1.0.0-beta.1`): Feature complete, testing phase
- **RC** (`1.0.0-rc.1`): Release candidate, final testing

### Version Automation

The workflow automatically:
- Extracts version from git tags (`v1.0.0` → `1.0.0`)
- Updates `pyproject.toml` for manual dispatches
- Creates consistent release names
- Links to the correct PyPI package version

## 📊 Publication Monitoring

### Success Indicators

After publication, verify:

1. **PyPI Package**: https://pypi.org/project/schema-gen/
2. **Installation**: `pip install schema-gen`
3. **Import**: `python -c "import schema_gen"`
4. **CLI**: `schema-gen --help`
5. **GitHub Release**: Automatic release created

### Troubleshooting

**Common issues:**

1. **Tests failing**: Check the Actions logs, fix issues, re-run
2. **Package validation errors**: Check `twine check` output
3. **Version conflicts**: Ensure version isn't already published
4. **Permission errors**: Verify trusted publishing is configured

**Getting help:**

- Check GitHub Actions logs for detailed error messages
- Review PyPI project settings for trusted publishing configuration
- Test locally using the manual publishing steps
- Create an issue if the problem persists

## 🔄 Continuous Integration

The publication workflow integrates with:

- **CI workflow**: Must pass before publication
- **Version compatibility**: Tests all supported library versions
- **Renovate**: Keeps dependencies current
- **Pre-commit hooks**: Ensures code quality

This creates a robust, automated pipeline from development to publication.
