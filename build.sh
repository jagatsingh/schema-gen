#!/bin/bash
set -e

# Build and publish schema-gen to Nexus repository
# Mirrors the tradingutils build.sh pattern

echo "== schema-gen build & publish =="

# --- Auto-bump patch version ---
PYPROJECT="pyproject.toml"
INIT_PY="src/schema_gen/__init__.py"

current_version=$(grep -oP '^version\s*=\s*"\K[^"]+' "$PYPROJECT")
IFS='.' read -r major minor patch <<< "$current_version"
new_version="${major}.${minor}.$((patch + 1))"

sed -i "s/^version = \"${current_version}\"/version = \"${new_version}\"/" "$PYPROJECT"
sed -i "s/__version__ = \"${current_version}\"/__version__ = \"${new_version}\"/" "$INIT_PY"

echo "Version bumped: ${current_version} -> ${new_version}"
echo ""

# Run pre-commit checks before building
echo "Running pre-commit checks..."
pre-commit run --all-files
echo ""

# Clean build artifacts and cache
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
rm -rf build/ dist/ *.egg-info/

# Check if uv is installed
if ! command -v uv &> /dev/null; then
    echo "UV is not installed. Installing UV..."
    curl -sSf https://astral.sh/uv/install.sh | bash
    source ~/.bashrc
fi

# Run tests
echo "Running tests..."
uv run pytest tests/ --ignore=tests/test_e2e_compile.py -q --tb=short
echo ""

# Build the package using uv
echo "Building package..."
uv build

# List built files
ls -la dist/

# Verify package metadata
echo "Checking package metadata..."
uv pip install twine --quiet 2>/dev/null || true
uv run twine check dist/* --strict

# Upload to Nexus repository
echo "Uploading to Nexus repository..."
uv run twine upload --repository nexus dist/*
echo ""
echo "Build and upload completed successfully!"
echo "Install with: uv pip install schema-gen --index-url http://localhost:5081/repository/pypi-local/simple/"
