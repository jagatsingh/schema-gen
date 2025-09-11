#!/usr/bin/env python3
"""
Publishing script for schema-gen

This script helps with local publishing to PyPI or Test PyPI.
"""

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path


def run_command(cmd: str, check: bool = True) -> subprocess.CompletedProcess:
    """Run a shell command and return the result."""
    print(f"🔨 Running: {cmd}")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)

    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)

    if check and result.returncode != 0:
        print(f"❌ Command failed with exit code {result.returncode}")
        sys.exit(result.returncode)

    return result


def get_current_version() -> str:
    """Get the current version from pyproject.toml."""
    pyproject = Path("pyproject.toml")
    if not pyproject.exists():
        print("❌ pyproject.toml not found. Run this from the project root.")
        sys.exit(1)

    content = pyproject.read_text()
    for line in content.split("\n"):
        if line.startswith("version = "):
            return line.split('"')[1]

    print("❌ Could not find version in pyproject.toml")
    sys.exit(1)


def update_version(version: str) -> None:
    """Update version in pyproject.toml."""
    pyproject = Path("pyproject.toml")
    content = pyproject.read_text()

    # Replace version line
    lines = content.split("\n")
    for i, line in enumerate(lines):
        if line.startswith("version = "):
            lines[i] = f'version = "{version}"'
            break

    pyproject.write_text("\n".join(lines))
    print(f"📝 Updated version to {version}")


def run_tests() -> None:
    """Run comprehensive tests."""
    print("\n🧪 Running tests...")

    # Run pytest with coverage
    run_command("uv run pytest tests/ -v --cov=src/schema_gen --cov-report=term")

    # Test all generators
    run_command("uv run python scripts/check_compatibility.py --library all-generators")

    # Run linting
    run_command("uv run ruff check src/ tests/")
    run_command("uv run ruff format --check src/ tests/")

    print("✅ All tests passed!")


def test_cli() -> None:
    """Test CLI functionality."""
    print("\n🖥️  Testing CLI...")

    # Test help
    run_command("uv run schema-gen --help")

    # Test in temporary directory
    with tempfile.TemporaryDirectory() as temp_dir:
        original_dir = Path.cwd()
        try:
            import os

            os.chdir(temp_dir)

            # Test init
            run_command("uv run schema-gen init")

            # Test generate
            run_command("uv run schema-gen generate")

            # Test validate
            run_command("uv run schema-gen validate")

            # Verify files exist
            generated_file = Path("generated/pydantic/user_models.py")
            if not generated_file.exists():
                print(f"❌ Expected file not found: {generated_file}")
                sys.exit(1)

        finally:
            os.chdir(original_dir)

    print("✅ CLI tests passed!")


def build_package() -> None:
    """Build the package."""
    print("\n📦 Building package...")

    # Clean previous builds
    import shutil

    if Path("dist").exists():
        shutil.rmtree("dist")

    # Build package
    run_command("uv build --verbose")

    # Check package
    run_command("uv run pip install twine")
    run_command(
        "               1111111111111111111111111111111111111111Z3`EDÈSSSSSSDlmmmmmnwmj"
    )

    # List built files
    dist_files = list(Path("dist").glob("*"))
    print(f"📁 Built files: {[f.name for f in dist_files]}")

    print("✅ Package built successfully!")


def verify_installation() -> None:
    """Verify package can be installed."""
    print("\n🔍 Verifying installation...")

    with tempfile.TemporaryDirectory() as temp_dir:
        # Install wheel in temporary environment
        wheel_file = next(Path("dist").glob("*.whl"))
        run_command(f"pip install --target {temp_dir} {wheel_file}")

        # Test import
        run_command(
            f"PYTHONPATH={temp_dir} python -c \"import schema_gen; print(f'Version: {{schema_gen.__version__}}')\""
        )

    print("✅ Package installation verified!")


def publish_package(target: str, dry_run: bool = False) -> None:
    """Publish package to PyPI or Test PyPI."""
    print(f"\n🚀 Publishing to {target}...")

    if target == "testpypi":
        repository = "--repository testpypi"
        url = "https://test.pypi.org/project/schema-gen/"
    else:
        repository = ""
        url = "https://pypi.org/project/schema-gen/"

    cmd = f"uv run twine upload {repository} dist/*"
    if dry_run:
        print(f"🔍 Dry run - would execute: {cmd}")
        return

    try:
        run_command(cmd)
        print(f"✅ Published successfully to {target}!")
        print(f"🔗 Package URL: {url}")

        if target == "testpypi":
            print("🧪 To test installation from Test PyPI:")
            print(
                "pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ schema-gen"
            )
        else:
            print("📦 To install:")
            print("pip install schema-gen")

    except Exception as e:
        print(f"❌ Publication failed: {e}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Publish schema-gen to PyPI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/publish.py --version 0.1.1 --target testpypi  # Publish to Test PyPI
  python scripts/publish.py --target pypi                      # Publish current version to PyPI
  python scripts/publish.py --build-only                       # Just build and test
""",
    )

    parser.add_argument("--version", help="Version to publish (updates pyproject.toml)")
    parser.add_argument(
        "--target",
        choices=["testpypi", "pypi"],
        default="testpypi",
        help="Where to publish (default: testpypi)",
    )
    parser.add_argument(
        "--build-only", action="store_true", help="Only build and test, don't publish"
    )
    parser.add_argument(
        "--skip-tests", action="store_true", help="Skip running tests (not recommended)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without actually publishing",
    )

    args = parser.parse_args()

    # Show current version
    current_version = get_current_version()
    print(f"📋 Current version: {current_version}")

    # Update version if specified
    if args.version:
        update_version(args.version)
        current_version = args.version

    # Run tests unless skipped
    if not args.skip_tests:
        run_tests()
        test_cli()
    else:
        print("⚠️  Skipping tests (--skip-tests specified)")

    # Build package
    build_package()

    # Verify installation
    verify_installation()

    # Publish unless build-only
    if not args.build_only:
        publish_package(args.target, args.dry_run)
    else:
        print("📦 Build completed. Use --target to publish.")

    print(f"\n🎉 Done! Version {current_version} ready.")


if __name__ == "__main__":
    main()
