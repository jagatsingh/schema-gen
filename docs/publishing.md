# Publishing

schema-gen can be published to PyPI (public) or a local Nexus repository (internal).

## Local Nexus (for internal use)

The fastest way to make schema-gen available to other repos on your machine:

```bash
./build.sh
```

This runs pre-commit checks, tests, builds the package, and uploads to the local Nexus repository at `http://localhost:5081/repository/pypi-local/`.

### Prerequisites

- Nexus running locally (via `trading_infrastructure/docker/docker-compose.yml`)
- `~/.pypirc` configured with the `[nexus]` section:
  ```ini
  [nexus]
  repository: http://localhost:5081/repository/pypi-local/
  username: admin
  password: admin
  ```

### Installing from Nexus

```bash
uv pip install schema-gen --index-url http://localhost:5081/repository/pypi-local/simple/
```

Or in `pyproject.toml`:
```toml
[tool.uv.sources]
schema-gen = { index = "nexus" }
```

With `.uv.toml`:
```toml
[repositories]
nexus = { url = "http://localhost:5081/repository/pypi-local/" }
```

## PyPI (for public release)

### Method 1: Git Tags (Recommended)

```bash
# 1. Update version in pyproject.toml and __init__.py
# 2. Commit the version bump
git add pyproject.toml src/schema_gen/__init__.py
git commit -m "bump: version 0.3.0"

# 3. Create and push a tag
git tag v0.3.0
git push origin v0.3.0
```

This triggers the publish workflow which:
- Runs tests and linting
- Builds the package
- Publishes to PyPI (stable) or Test PyPI (alpha/beta)
- Creates a GitHub release

### Method 2: GitHub Actions Manual Dispatch

1. Go to **Actions** > **Publish to PyPI**
2. Click **Run workflow**
3. Choose target: `test-pypi`, `pypi`, or `both`
4. Optionally specify a version override

### Method 3: GitHub Release

Create a release via the GitHub UI — this also triggers the publish workflow.

## Version Strategy

Follows [Semantic Versioning](https://semver.org/):
- **Major** (`1.0.0`): Breaking changes
- **Minor** (`0.3.0`): New features
- **Patch** (`0.3.1`): Bug fixes

Pre-release tags: `v0.3.0-alpha.1`, `v0.3.0-beta.1`, `v0.3.0-rc.1`

## Pre-Publication Checklist

- [ ] Version updated in `pyproject.toml` and `src/schema_gen/__init__.py`
- [ ] Tests pass: `uv run pytest tests/ --ignore=tests/test_e2e_compile.py`
- [ ] Pre-commit clean: `pre-commit run --all-files`
- [ ] CLI works: `schema-gen --version`
- [ ] Package builds: `uv build`
