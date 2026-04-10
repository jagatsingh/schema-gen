# Supply Chain Security & Dependency Management

This guide documents the dependency management practices for schema-gen, aligned with the tradingutils supply chain security conventions.

## 7-Day Dependency Delay

All dependency upgrades are delayed by 7 days to allow the open-source community time to detect compromised packages. Most supply chain attacks on PyPI are detected within 24-72 hours — a 7-day quarantine provides a comfortable margin. Security vulnerabilities bypass the delay entirely.

## Architecture: Defense in Depth

```
┌─────────────────────────────────────────────────────────┐
│  Layer 1: Registry-Level Delay                          │
│  UV exclude-newer blocks packages < 7 days old          │
├─────────────────────────────────────────────────────────┤
│  Layer 2: Automated PR Delay                            │
│  Renovate minimumReleaseAge delays update PRs           │
├─────────────────────────────────────────────────────────┤
│  Layer 3: Lockfile Discipline                           │
│  Frozen installs in CI prevent silent resolution        │
└─────────────────────────────────────────────────────────┘
```

## Layer 1: UV Exclude-Newer

UV's `--exclude-newer` flag refuses to resolve any package version published less than 7 days ago. Set globally via environment variable in `~/.bashrc`:

```bash
export UV_EXCLUDE_NEWER=$(date -u -d '7 days ago' +%Y-%m-%dT%H:%M:%SZ)
```

This covers every UV operation: `uv lock`, `uv sync`, `uv pip install`.

### CI Enforcement

Every GitHub Actions job sets the same variable:

```yaml
steps:
  - name: Set 7-day dependency delay
    run: echo "UV_EXCLUDE_NEWER=$(date -u -d '7 days ago' +%Y-%m-%dT%H:%M:%SZ)" >> $GITHUB_ENV
```

### Emergency Bypass

When a critical security patch requires a package released within the last 7 days:

```bash
UV_EXCLUDE_NEWER="" uv lock
```

Always document the reason for bypassing in the commit message.

## Layer 2: Renovate

schema-gen extends the shared Renovate preset from tradingutils:

```jsonc
// renovate.json5
{
  "extends": ["github>jagatsingh/tradingutils"]
}
```

The shared preset enforces:

| Setting | Value | Effect |
|---------|-------|--------|
| `minimumReleaseAge` | `7 days` (default) | All packages delayed 7 days |
| `minimumReleaseAge` (major) | `14 days` | Extra caution for breaking changes |
| `minimumReleaseAge` (vulnerability) | `0 days` | Security patches immediate |

schema-gen adds project-specific rules on top:

- **Core schema libraries** (pydantic, sqlalchemy, protobuf, etc.) get separate PRs for major updates
- **Development dependencies** are grouped and auto-merged for patches
- **GitHub Actions** are pinned by SHA digest
- **Lock file maintenance** runs weekly

### Updating Dependencies (the right way)

1. **Wait for a Renovate PR** — opens weekly after the 7-day stability period
2. **Review the PR** — check changelog, breaking changes, CI results
3. **Merge** — non-major updates auto-merge if CI passes; major updates require manual review

## Layer 3: Lockfile Discipline

### Frozen Installs

All CI workflows use frozen install mode:

```bash
uv sync --frozen  # Uses committed uv.lock exactly — fails if out of date
```

This prevents silent resolution of new (potentially malicious) packages.

### Python Version Pinning

Python version is pinned to a minor version range (`>=3.12,<3.13`) to prevent accidental upgrades to untested Python releases.

## Vulnerability Scanning

Security vulnerabilities **bypass all delays**. Detection tools:

| Tool | When it runs | What it checks |
|------|-------------|----------------|
| `uv-secure` | Pre-commit hook | PyPI CVEs in `uv.lock` |
| Renovate vulnerability alerts | Continuous | All ecosystems |
| GitHub Dependabot alerts | Continuous | Security tab |

The `uv-secure` pre-commit hook runs automatically when `pyproject.toml` or `uv.lock` changes:

```yaml
# .pre-commit-config.yaml
- id: uv-secure
  name: uv-secure vulnerability check
  entry: bash -c 'uv-secure uv.lock; rc=$?; if [ "$rc" -eq 1 ]; then exit 1; else exit 0; fi'
  language: system
  files: '(pyproject\.toml|uv\.lock)$'
```

## Configuration Files

| File | Purpose |
|------|---------|
| `~/.bashrc` | `UV_EXCLUDE_NEWER` environment variable |
| `renovate.json5` | Renovate config (extends `github>jagatsingh/tradingutils`) |
| `.github/workflows/*.yml` | CI with `UV_EXCLUDE_NEWER` enforcement |
| `.pre-commit-config.yaml` | `uv-secure` vulnerability scanning hook |
| `pyproject.toml` | Python version constraint, dependency pins |
| `uv.lock` | Committed lockfile for frozen installs |

## Verification

```bash
# Check UV delay is active
echo $UV_EXCLUDE_NEWER
# Should show a date 7 days in the past

# Run vulnerability scan
uv-secure uv.lock

# Check Renovate config extends shared preset
grep 'github>jagatsingh/tradingutils' renovate.json5
```
