# Renovate Configuration

This project uses [Renovate](https://docs.renovatebot.com/) to automatically keep dependencies up to date.

## Configuration Files

- `renovate.json` - Main configuration file
- `.github/renovate.json5` - GitHub-specific settings (more readable JSON5 format)
- `.renovaterc` - Simple config for local testing

## How It Works

### Scheduling
- **Main updates**: Runs weekly on Monday mornings (before 6am UTC)
- **Security updates**: Run immediately when detected
- **Lock file maintenance**: Weekly on Monday mornings

### Update Strategy

#### Core Libraries (Require Review)
These libraries are critical to schema generation and updates need manual review:
- `pydantic` - Core validation library
- `sqlalchemy` - Database ORM
- `pathway` - Data processing framework
- `jsonschema` - JSON schema validation
- `graphql-core` - GraphQL support
- `avro` - Apache Avro support
- `protobuf` - Protocol Buffers support

#### Development Dependencies (Auto-mergeable)
Patch updates to these can be auto-merged:
- `pytest` - Testing framework
- `ruff` - Linting and formatting
- `mypy` - Type checking
- `pre-commit` - Git hooks
- `mkdocs` - Documentation
- `coverage` - Code coverage

#### GitHub Actions
- Automatically pinned to digest hashes for security
- Patch updates can be auto-merged

### Package Management

This project uses **uv** for Python package management with PEP 621 compliant `pyproject.toml` configuration. Renovate automatically detects and manages:

- **uv.lock** - Lockfile maintenance for reproducible builds
- **pyproject.toml dependencies** - Production dependencies
- **pyproject.toml dev-dependencies** - Development dependencies

### Package Grouping

Updates are grouped logically to reduce PR noise:
- **Python dependencies** - General Python packages from `pyproject.toml`
- **Schema generation core** - Critical schema libraries
- **Development dependencies** - Testing, linting, documentation tools
- **GitHub Actions** - Workflow dependencies

### Security

- **Vulnerability alerts** enabled with high priority
- **OSV vulnerability database** integration
- **Security updates** bypass normal scheduling and run immediately
- **GitHub Actions** pinned to specific digest hashes

## Manual Testing

To test Renovate configuration locally:

```bash
# Install Renovate CLI
npm install -g renovate

# Dry run (check what would be updated)
renovate --platform=local --dry-run

# Full local run
renovate --platform=local
```

### Testing with uv

Since this project uses uv, make sure you have it installed for testing:

```bash
# Install uv if not already installed
curl -LsSf https://astral.sh/uv/install.sh | sh

# Sync dependencies to test lockfile updates
uv sync --all-extras --dev
```

## Customization

### Adding New Package Rules

Edit `renovate.json` to add new package-specific rules:

```json
{
  "packageRules": [
    {
      "description": "Special handling for new library",
      "matchPackageNames": ["new-library"],
      "schedule": ["before 6am on monday"],
      "labels": ["dependencies", "special"]
    }
  ]
}
```

### Updating Test Matrix

The configuration includes custom managers to automatically update library versions in:
- `tests/test-matrix.yml` - Version compatibility matrix
- `.github/workflows/version-compatibility.yml` - CI workflow versions

## Monitoring

- **Dependency Dashboard** - GitHub issue showing all pending updates
- **Labels** - PRs are automatically labeled for easy filtering
- **Reviewers** - Code owners are automatically assigned for core library updates

## Troubleshooting

### Common Issues

1. **PR limit reached** - Maximum 5 concurrent PRs, 2 per hour
2. **Stability period** - 3-day waiting period for new releases
3. **Failed updates** - Check CI status and dependency compatibility

### Disabling Updates

To temporarily disable Renovate:
```json
{
  "enabled": false
}
```

To disable for specific packages:
```json
{
  "packageRules": [
    {
      "matchPackageNames": ["problematic-package"],
      "enabled": false
    }
  ]
}
```
