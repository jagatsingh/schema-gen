# 🚀 Quick Publishing Guide

## Automated Publishing (Recommended)

### Option 1: Git Tag
```bash
# Update version and create tag
sed -i 's/version = "[^"]*"/version = "0.1.1"/' pyproject.toml
git add pyproject.toml
git commit -m "bump: version 0.1.1"
git tag v0.1.1
git push origin v0.1.1
```

### Option 2: GitHub Actions
1. Go to **Actions** → **Publish to PyPI**
2. Click **Run workflow**
3. Enter version (e.g., `0.1.1`) and target (`test-pypi` or `pypi`)

## Manual Publishing

### Test PyPI (Testing)
```bash
python scripts/publish.py --version 0.1.1 --target testpypi
```

### PyPI (Production)
```bash
python scripts/publish.py --version 0.1.1 --target pypi
```

## Prerequisites

1. **Install uv**: `curl -LsSf https://astral.sh/uv/install.sh | sh`
2. **Setup API tokens** (for manual publishing):
   - Get token from https://pypi.org/manage/account/token/
   - Set `TWINE_USERNAME=__token__` and `TWINE_PASSWORD=your-token`

## What Gets Published

- ✅ **Comprehensive testing** (>80% coverage)
- ✅ **All 13 generators** compatibility tested
- ✅ **CLI functionality** verified
- ✅ **Package validation** with twine
- ✅ **Automatic GitHub releases**

## Links

- 📦 [PyPI Package](https://pypi.org/project/schema-gen/)
- 🧪 [Test PyPI](https://test.pypi.org/project/schema-gen/)
- 📚 [Detailed Guide](docs/publishing.md)
- 🔧 [Publishing Script](scripts/publish.py)
