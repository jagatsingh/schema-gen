"""Main CLI entry point for schema-gen"""

import re
import time
from pathlib import Path

import click
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from ..core.generator import create_generation_engine
from ..diff.baseline import BaselineError, load_baseline, load_current
from ..diff.comparator import compare_schemas
from ..diff.formatter import format_json, format_text
from ..diff.rules import StrictnessLevel

# Pattern to match timestamp lines across all generators
_TIMESTAMP_RE = re.compile(r"^.*Generated at:.*$", re.MULTILINE)


def _normalize_generated(content: str) -> str:
    """Strip timestamp lines so content can be compared across runs."""
    return _TIMESTAMP_RE.sub("", content).strip()


class SchemaWatcher(FileSystemEventHandler):
    """File system event handler for watching schema changes"""

    def __init__(self, engine, config_path=".schema-gen.config.py"):
        self.engine = engine
        self.config_path = config_path
        self.last_run = 0
        self.debounce_seconds = 1

    def on_modified(self, event):
        """Handle file modification events"""
        if event.is_directory:
            return

        # Only watch Python files and config files
        if not (
            event.src_path.endswith(".py") or event.src_path.endswith(self.config_path)
        ):
            return

        # Debounce rapid file changes
        current_time = time.time()
        if current_time - self.last_run < self.debounce_seconds:
            return

        self.last_run = current_time

        try:
            click.echo(f"📝 Detected change in {event.src_path}")

            # Reload config if config file changed
            if event.src_path.endswith(self.config_path):
                click.echo("🔄 Reloading configuration...")
                self.engine = create_generation_engine(self.config_path)

            # Regenerate schemas
            click.echo("🚀 Regenerating schemas...")
            self.engine.load_schemas_from_directory()
            self.engine.generate_all()
            click.echo("✅ Regeneration completed!")

        except Exception as e:
            click.echo(f"❌ Error during regeneration: {e}")

    def on_created(self, event):
        """Handle file creation events"""
        if not event.is_directory and event.src_path.endswith(".py"):
            self.on_modified(event)

    def on_deleted(self, event):
        """Handle file deletion events"""
        if not event.is_directory and event.src_path.endswith(".py"):
            click.echo(f"🗑️  Detected deletion of {event.src_path}")
            # Trigger regeneration to clean up deleted schemas
            self.on_modified(event)


@click.group()
@click.version_option()
def main():
    """Schema Gen - Universal schema converter for Python

    Define schemas once, generate everywhere.
    """
    pass


@main.command()
@click.option(
    "--input",
    "-i",
    "input_dir",
    help="Input directory containing schemas",
    default=None,
)
@click.option(
    "--output",
    "-o",
    "output_dir",
    help="Output directory for generated files",
    default=None,
)
@click.option(
    "--target",
    "-t",
    "targets",
    multiple=True,
    help="Target generators to run",
    default=None,
)
@click.option(
    "--config",
    "-c",
    "config_path",
    help="Path to config file",
    default=".schema-gen.config.py",
)
def generate(input_dir, output_dir, targets, config_path):
    """Generate schema variants from source definitions"""
    click.echo("🚀 Generating schemas...")

    try:
        # Create generation engine
        engine = create_generation_engine(config_path)

        # Override config with CLI options if provided
        if input_dir:
            engine.config.input_dir = input_dir
        if output_dir:
            engine.config.output_dir = output_dir
        if targets:
            engine.config.targets = list(targets)

        # Load schemas from input directory
        engine.load_schemas_from_directory()

        # Generate all targets
        engine.generate_all()

        click.echo(f"✅ Generation completed! Check {engine.config.output_dir}/")

    except Exception as e:
        click.echo(f"❌ Generation failed: {e}")
        raise click.Abort() from e


@main.command()
@click.option(
    "--input",
    "-i",
    "input_dir",
    help="Input directory containing schemas",
    default=None,
)
@click.option(
    "--output",
    "-o",
    "output_dir",
    help="Output directory for generated files",
    default=None,
)
@click.option(
    "--config",
    "-c",
    "config_path",
    help="Path to config file",
    default=".schema-gen.config.py",
)
def watch(input_dir, output_dir, config_path):
    """Watch for schema changes and auto-regenerate"""
    click.echo("👀 Starting schema watcher...")

    try:
        # Create generation engine
        engine = create_generation_engine(config_path)

        # Override config with CLI options if provided
        if input_dir:
            engine.config.input_dir = input_dir
        if output_dir:
            engine.config.output_dir = output_dir

        # Initial generation
        click.echo("🚀 Running initial schema generation...")
        engine.load_schemas_from_directory()
        engine.generate_all()
        click.echo("✅ Initial generation completed!")

        # Set up file watcher
        event_handler = SchemaWatcher(engine, config_path)
        observer = Observer()

        # Watch input directory
        input_path = Path(engine.config.input_dir)
        if input_path.exists():
            observer.schedule(event_handler, str(input_path), recursive=True)
            click.echo(f"📁 Watching input directory: {input_path}")

        # Watch config file
        config_file_path = Path(config_path)
        if config_file_path.exists():
            observer.schedule(
                event_handler, str(config_file_path.parent), recursive=False
            )
            click.echo(f"⚙️  Watching config file: {config_path}")

        # Start watching
        observer.start()
        click.echo("✨ File watcher started! Press Ctrl+C to stop.")

        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            observer.stop()
            click.echo("\n🛑 File watcher stopped.")

        observer.join()

    except FileNotFoundError as e:
        click.echo(f"❌ Directory not found: {e}")
        click.echo("💡 Try running 'schema-gen init' first to set up the project.")
        raise click.Abort() from e
    except Exception as e:
        click.echo(f"❌ Watch failed: {e}")
        raise click.Abort() from e


@main.command()
@click.option(
    "--config",
    "-c",
    "config_path",
    help="Path to config file",
    default=".schema-gen.config.py",
)
def validate(config_path):
    """Validate that generated schemas are up-to-date"""
    click.echo("Validating schemas...")

    try:
        # Create generation engine
        engine = create_generation_engine(config_path)

        # Gracefully skip when there is no schemas/ directory. This makes the
        # `schema-gen-validate` pre-commit hook safe to enable in repos that
        # don't yet have any @Schema-decorated files (or temporarily have
        # none) without forcing contributors to use --no-verify.
        schema_dir = Path(engine.config.input_dir)
        if not schema_dir.exists():
            click.echo(
                f"No schemas directory found at '{schema_dir}', skipping validation."
            )
            return

        # Load schemas
        engine.load_schemas_from_directory()

        # Parse all schemas
        schemas = engine.parser.parse_all_schemas()

        # Check if generated files exist and are up-to-date
        output_path = Path(engine.config.output_dir)
        if not output_path.exists():
            click.echo("Output directory does not exist!")
            click.echo("Run 'schema-gen generate' to create generated files.")
            raise SystemExit(1)

        validation_passed = True
        files_checked = 0

        for target in engine.config.targets:
            target_dir = output_path / target
            if not target_dir.exists():
                click.echo(f"FAIL: Target directory {target}/ does not exist!")
                validation_passed = False
                continue

            generator = engine.generators.get(target)
            if not generator:
                click.echo(f"FAIL: No generator found for target: {target}")
                validation_passed = False
                continue

            # Build expected files: {relative_filename: expected_content}
            expected_files = {}

            # Extra files (e.g. _base.py for SQLAlchemy)
            extra_files = generator.get_extra_files(schemas, target_dir)
            expected_files.update(extra_files)

            # Per-schema files
            for schema in schemas:
                filename = generator.get_schema_filename(schema)
                content = generator.generate_file(schema)
                expected_files[filename] = content

            # Index file
            if generator.generates_index_file:
                index_content = generator.generate_index(schemas, target_dir)
                if index_content is not None:
                    if generator.file_extension == ".ts":
                        index_filename = "index.ts"
                    else:
                        index_filename = "__init__.py"
                    expected_files[index_filename] = index_content

            # Compare each expected file with actual
            for filename, expected_content in expected_files.items():
                files_checked += 1
                actual_path = target_dir / filename

                if not actual_path.exists():
                    click.echo(f"  MISSING: {target}/{filename}")
                    validation_passed = False
                    continue

                actual_content = actual_path.read_text()

                if _normalize_generated(expected_content) != _normalize_generated(
                    actual_content
                ):
                    click.echo(f"  OUT-OF-DATE: {target}/{filename}")
                    validation_passed = False
                else:
                    click.echo(f"  up-to-date: {target}/{filename}")

        if validation_passed:
            click.echo(f"All schemas are up-to-date! ({files_checked} file(s) checked)")
        else:
            click.echo(
                "Some schemas are out of date. Run 'schema-gen generate' to update."
            )
            raise SystemExit(1)

    except SystemExit:
        raise
    except click.Abort:
        raise
    except Exception as e:
        click.echo(f"Validation failed: {e}")
        raise SystemExit(1) from e


@main.command()
@click.option("--input-dir", help="Input directory for schemas", default="schemas/")
@click.option(
    "--output-dir", help="Output directory for generated files", default="generated/"
)
@click.option("--targets", help="Comma-separated list of targets", default="pydantic")
def init(input_dir, output_dir, targets):
    """Initialize schema-gen in current project"""
    click.echo("🏗️  Initializing schema-gen project...")

    # Create directories
    Path(input_dir).mkdir(exist_ok=True)
    Path(output_dir).mkdir(exist_ok=True)

    # Create config file
    config_content = f'''"""Schema Gen configuration file"""

from schema_gen import Config

config = Config(
    input_dir="{input_dir}",
    output_dir="{output_dir}",
    targets=[{", ".join(f'"{t.strip()}"' for t in targets.split(","))}],

    # Pydantic-specific settings
    pydantic={{
        "use_enum": True,
        "extra": "forbid",
    }},

    # SQLAlchemy-specific settings (for future use)
    sqlalchemy={{
        "use_declarative": True,
        "naming_convention": "snake_case"
    }},
)
'''

    with open(".schema-gen.config.py", "w") as f:
        f.write(config_content)

    # Create example schema
    example_schema = '''"""Example schema definition"""

from schema_gen import Schema, Field
from typing import Optional
from datetime import datetime


@Schema
class User:
    """User schema for the application"""

    id: int = Field(
        primary_key=True,
        auto_increment=True,
        description="Unique identifier"
    )

    name: str = Field(
        max_length=100,
        min_length=2,
        description="User's full name"
    )

    email: str = Field(
        unique=True,
        format="email",
        description="User's email address"
    )

    age: Optional[int] = Field(
        default=None,
        min_value=13,
        max_value=120,
        description="User's age"
    )

    created_at: datetime = Field(
        auto_now_add=True,
        description="Account creation timestamp"
    )

    class Variants:
        create_request = ['name', 'email', 'age']
        update_request = ['name', 'email', 'age']
        public_response = ['id', 'name', 'age', 'created_at']
        full_response = ['id', 'name', 'email', 'age', 'created_at']
'''

    with open(f"{input_dir}/user.py", "w") as f:
        f.write(example_schema)

    click.echo("✅ Project initialized!")
    click.echo(f"  📁 Schema directory: {input_dir}/")
    click.echo(f"  📁 Output directory: {output_dir}/")
    click.echo("  📋 Config file: .schema-gen.config.py")
    click.echo(f"  📄 Example schema: {input_dir}/user.py")
    click.echo()
    click.echo("Next steps:")
    click.echo("  1. Edit your schemas in the schema directory")
    click.echo("  2. Run 'schema-gen generate' to generate models")
    click.echo("  3. Run 'schema-gen install-hooks' to set up pre-commit integration")


@main.command()
@click.option(
    "--install-pre-commit/--no-install-pre-commit",
    default=True,
    help="Install pre-commit package",
)
def install_hooks(install_pre_commit):
    """Install pre-commit hooks for automatic schema generation"""
    click.echo("🔧 Installing schema-gen pre-commit hooks...")

    import subprocess

    config_dest = Path(".pre-commit-config.yaml")

    minimal_config = """repos:
  - repo: local
    hooks:
      - id: schema-gen-validate
        name: Validate generated schemas
        entry: schema-gen validate
        language: system
        pass_filenames: false
        files: '\\.py$'
        stages: [pre-commit]

      - id: schema-gen-generate
        name: Generate schemas
        entry: schema-gen generate
        language: system
        pass_filenames: false
        files: '(schemas/.*\\.py|\\.schema-gen\\.config\\.py)$'
"""

    if config_dest.exists():
        click.echo("  .pre-commit-config.yaml already exists")
        if click.confirm("Overwrite existing configuration?"):
            with open(config_dest, "w") as f:
                f.write(minimal_config)
            click.echo("  Pre-commit configuration updated")
    else:
        with open(config_dest, "w") as f:
            f.write(minimal_config)
        click.echo("  Pre-commit configuration created")

    if install_pre_commit:
        try:
            # Install pre-commit package
            click.echo("📦 Installing pre-commit...")
            subprocess.run(
                ["pip", "install", "pre-commit"], check=True, capture_output=True
            )

            # Install the hooks
            click.echo("🔗 Installing pre-commit hooks...")
            subprocess.run(["pre-commit", "install"], check=True, capture_output=True)

            click.echo("✅ Pre-commit hooks installed successfully!")
            click.echo("💡 Now schema generation will run automatically before commits")

        except subprocess.CalledProcessError:
            click.echo("❌ Failed to install pre-commit hooks")
            click.echo(
                "💡 Install manually with: pip install pre-commit && pre-commit install"
            )
        except FileNotFoundError:
            click.echo("❌ pip not found")
            click.echo("💡 Install pre-commit manually and run: pre-commit install")


@main.command()
@click.option(
    "--against",
    required=True,
    help=(
        "Baseline reference: .git#branch=main, .git#tag=v1.0.0, "
        ".git#commit=abc123, or /path/to/snapshot/"
    ),
)
@click.option(
    "--level",
    type=click.Choice(["WIRE", "WIRE_JSON", "SOURCE"], case_sensitive=False),
    default="WIRE_JSON",
    help="Strictness level [default: WIRE_JSON]",
)
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["text", "json"], case_sensitive=False),
    default="text",
    help="Output format [default: text]",
)
@click.option(
    "--ignore",
    "ignore_rules",
    multiple=True,
    help="Suppress a specific rule (repeatable)",
)
@click.option(
    "--config",
    "-c",
    "config_path",
    help="Path to config file",
    default=".schema-gen.config.py",
)
def diff(against, level, fmt, ignore_rules, config_path):
    """Compare schemas against a baseline to detect breaking changes.

    Requires 'jsonschema' in your configured targets with generated output
    committed to version control.

    \b
    EXIT CODES:
      0   No breaking changes
      1   Breaking changes detected
      2   Tool error
    """
    try:
        engine = create_generation_engine(config_path)
        output_dir = engine.config.output_dir

        strictness = StrictnessLevel(level.upper())
        old_schemas = load_baseline(against, output_dir)
        new_schemas = load_current(output_dir)

        violations = compare_schemas(
            old_schemas,
            new_schemas,
            level=strictness,
            ignore=list(ignore_rules),
        )

        if violations:
            if fmt == "json":
                click.echo(format_json(violations))
            else:
                click.echo(format_text(violations))
            raise SystemExit(1)
        else:
            click.echo("No breaking changes detected.")

    except BaselineError as exc:
        click.echo(f"Error: {exc}", err=True)
        raise SystemExit(2) from exc
    except SystemExit:
        raise
    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    main()
