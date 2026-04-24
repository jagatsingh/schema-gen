"""Main CLI entry point for schema-gen"""

import time
from pathlib import Path

import click
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from ..core.generator import create_generation_engine
from ..diff.baseline import BaselineError, load_baseline, load_current
from ..diff.comparator import compare_schemas
from ..diff.formatter import format_github, format_json, format_text
from ..diff.rules import RuleId, StrictnessLevel


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

                if expected_content != actual_content:
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
    type=click.Choice(["text", "json", "github"], case_sensitive=False),
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
        # Validate --ignore values early so typos are caught before comparison.
        valid_rule_names = {r.value for r in RuleId}
        for rule_name in ignore_rules:
            if rule_name not in valid_rule_names:
                click.echo(
                    f"Unknown rule: {rule_name}. "
                    f"Valid rules: {sorted(valid_rule_names)}",
                    err=True,
                )
                raise SystemExit(2)

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
            elif fmt == "github":
                click.echo(format_github(violations))
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


@main.group()
def registry():
    """Contract registry: query, validate, and inspect generated schemas."""
    pass


def _load_registry_index(config_path: str) -> dict:
    """Load the registry.json from the configured output directory."""
    import json

    engine = create_generation_engine(config_path)
    output_dir = Path(engine.config.output_dir)
    registry_path = output_dir / "registry.json"

    if not registry_path.exists():
        click.echo(
            "Registry index not found. Run 'schema-gen generate' first "
            "or 'schema-gen registry index' to build it."
        )
        raise SystemExit(1)

    return json.loads(registry_path.read_text())


@registry.command("index")
@click.option(
    "--config",
    "-c",
    "config_path",
    help="Path to config file",
    default=".schema-gen.config.py",
)
def registry_index(config_path):
    """Force rebuild the registry index."""
    import json

    from ..registry.index import build_registry_index

    try:
        engine = create_generation_engine(config_path)
        engine.load_schemas_from_directory()
        schemas = engine.parser.parse_all_schemas()

        if not schemas:
            click.echo("No schemas found.")
            raise SystemExit(1)

        index = build_registry_index(schemas, engine.config)
        output_dir = Path(engine.config.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        registry_path = output_dir / "registry.json"

        with open(registry_path, "w") as f:
            json.dump(index, f, indent=2, sort_keys=False)
            f.write("\n")

        type_count = len(index.get("types", {}))
        enum_count = len(index.get("enums", {}))
        click.echo(
            f"Registry index built: {type_count} type(s), "
            f"{enum_count} enum(s) -> {registry_path}"
        )

    except SystemExit:
        raise
    except Exception as e:
        click.echo(f"Error: {e}")
        raise SystemExit(1) from e


@registry.command("list")
@click.option(
    "--config",
    "-c",
    "config_path",
    help="Path to config file",
    default=".schema-gen.config.py",
)
def registry_list(config_path):
    """List all types in the registry index."""
    try:
        index = _load_registry_index(config_path)
        types = index.get("types", {})

        if not types:
            click.echo("No types found in registry.")
            return

        # Table header
        click.echo(f"{'Name':<30} {'Domain':<15} {'Fields':<8} {'Description'}")
        click.echo("-" * 80)

        for name in sorted(types):
            entry = types[name]
            domain = entry.get("domain") or "-"
            fields_count = len(entry.get("fields", {}))
            desc = entry.get("description", "")
            if len(desc) > 40:
                desc = desc[:37] + "..."
            click.echo(f"{name:<30} {domain:<15} {fields_count:<8} {desc}")

    except SystemExit:
        raise
    except Exception as e:
        click.echo(f"Error: {e}")
        raise SystemExit(1) from e


@registry.command("show")
@click.argument("type_name")
@click.option(
    "--config",
    "-c",
    "config_path",
    help="Path to config file",
    default=".schema-gen.config.py",
)
def registry_show(type_name, config_path):
    """Show full type information for TYPE_NAME."""
    try:
        index = _load_registry_index(config_path)
        types = index.get("types", {})
        enums = index.get("enums", {})

        if type_name not in types:
            # Check enums
            if type_name in enums:
                _show_enum(type_name, enums[type_name])
                return
            click.echo(f"Type '{type_name}' not found in registry.")
            raise SystemExit(1)

        entry = types[type_name]
        click.echo(f"Type: {type_name}")
        click.echo(f"Domain: {entry.get('domain') or '-'}")
        click.echo(f"Kind: {entry.get('kind', 'struct')}")
        click.echo(f"Description: {entry.get('description', '')}")
        click.echo()

        # Fields table
        fields = entry.get("fields", {})
        if fields:
            click.echo("Fields:")
            click.echo(f"  {'Name':<25} {'Type':<25} {'Required':<10} {'Description'}")
            click.echo("  " + "-" * 75)
            for fname in sorted(fields):
                finfo = fields[fname]
                req = "yes" if finfo.get("required") else "no"
                desc = finfo.get("description", "")
                click.echo(
                    f"  {fname:<25} {finfo.get('type', ''):<25} {req:<10} {desc}"
                )
            click.echo()

        # Enums referenced
        erefs = entry.get("enums_referenced", [])
        if erefs:
            click.echo(f"Enums referenced: {', '.join(erefs)}")

        # Nested types
        nrefs = entry.get("nested_types", [])
        if nrefs:
            click.echo(f"Nested types: {', '.join(nrefs)}")

        # Variants
        variants = entry.get("variants", [])
        if variants:
            click.echo(f"Variants: {', '.join(variants)}")

    except SystemExit:
        raise
    except Exception as e:
        click.echo(f"Error: {e}")
        raise SystemExit(1) from e


def _show_enum(name: str, entry: dict):
    """Display enum details."""
    click.echo(f"Enum: {name}")
    values = entry.get("values", [])
    if values:
        click.echo("Values:")
        for v in values:
            click.echo(f"  {v['name']} = {v['value']}")
    used_by = entry.get("used_by", [])
    if used_by:
        click.echo(f"Used by: {', '.join(used_by)}")


@registry.command("refs")
@click.argument("type_name")
@click.option(
    "--config",
    "-c",
    "config_path",
    help="Path to config file",
    default=".schema-gen.config.py",
)
def registry_refs(type_name, config_path):
    """Show which types reference TYPE_NAME."""
    try:
        index = _load_registry_index(config_path)
        types = index.get("types", {})
        enums = index.get("enums", {})
        referencing: list[str] = []

        # Check if it's an enum — look at used_by
        if type_name in enums:
            used_by = enums[type_name].get("used_by", [])
            if used_by:
                click.echo(f"Types referencing enum '{type_name}':")
                for t in used_by:
                    click.echo(f"  {t}")
            else:
                click.echo(f"No types reference enum '{type_name}'.")
            return

        # For struct types, scan all other types' enums_referenced and nested_types
        for tname, tentry in sorted(types.items()):
            if tname == type_name:
                continue
            enums_ref = tentry.get("enums_referenced", [])
            nested_ref = tentry.get("nested_types", [])
            if type_name in enums_ref or type_name in nested_ref:
                referencing.append(tname)

        if referencing:
            click.echo(f"Types referencing '{type_name}':")
            for t in sorted(referencing):
                click.echo(f"  {t}")
        else:
            click.echo(f"No types reference '{type_name}'.")

    except SystemExit:
        raise
    except Exception as e:
        click.echo(f"Error: {e}")
        raise SystemExit(1) from e


@registry.command("search")
@click.argument("query")
@click.option(
    "--config",
    "-c",
    "config_path",
    help="Path to config file",
    default=".schema-gen.config.py",
)
def registry_search(query, config_path):
    """Search types and fields matching QUERY."""
    try:
        index = _load_registry_index(config_path)
        types = index.get("types", {})
        enums = index.get("enums", {})
        query_lower = query.lower()
        found = False

        # Search type names and descriptions
        for tname, tentry in sorted(types.items()):
            if (
                query_lower in tname.lower()
                or query_lower in (tentry.get("description", "") or "").lower()
            ):
                click.echo(f"[type] {tname}: {tentry.get('description', '')}")
                found = True

            # Search field names and descriptions
            for fname, finfo in sorted(tentry.get("fields", {}).items()):
                if (
                    query_lower in fname.lower()
                    or query_lower in (finfo.get("description", "") or "").lower()
                ):
                    click.echo(
                        f"  [field] {tname}.{fname} "
                        f"({finfo.get('type', '')}): "
                        f"{finfo.get('description', '')}"
                    )
                    found = True

        # Search enum names
        for ename in sorted(enums):
            if query_lower in ename.lower():
                click.echo(f"[enum] {ename}")
                found = True

        if not found:
            click.echo(f"No results for '{query}'.")

    except SystemExit:
        raise
    except Exception as e:
        click.echo(f"Error: {e}")
        raise SystemExit(1) from e


@registry.command("validate")
@click.argument("file", type=click.Path(exists=True))
@click.option(
    "--type", "-t", "type_name", required=True, help="Type name to validate against"
)
@click.option(
    "--config",
    "-c",
    "config_path",
    help="Path to config file",
    default=".schema-gen.config.py",
)
def registry_validate(file, type_name, config_path):
    """Validate a JSON file against a type's JSON Schema."""
    import json

    try:
        import jsonschema as jsonschema_lib
    except ImportError as exc:
        click.echo("jsonschema package is required. Install it: pip install jsonschema")
        raise SystemExit(1) from exc

    try:
        engine = create_generation_engine(config_path)
        output_dir = Path(engine.config.output_dir)

        # Load the JSON Schema for the type
        schema_filename = type_name.lower() + ".json"
        schema_path = output_dir / "jsonschema" / schema_filename
        if not schema_path.exists():
            click.echo(
                f"JSON Schema file not found: {schema_path}\n"
                "Ensure 'jsonschema' is in your targets and run 'schema-gen generate'."
            )
            raise SystemExit(1)

        json_schema = json.loads(schema_path.read_text())

        # Build a validation schema that references the type via $defs.
        defs = json_schema.get("$defs", {})
        if type_name in defs:
            # Create a top-level schema that $ref's the type within $defs.
            type_schema = {
                "$ref": f"#/$defs/{type_name}",
                "$defs": defs,
            }
        else:
            click.echo(
                f"Type '{type_name}' not found in $defs of {schema_path}.\n"
                f"Available types: {', '.join(sorted(defs)) or '(none)'}"
            )
            raise SystemExit(1)

        # Load the data file
        data = json.loads(Path(file).read_text())

        # Validate
        jsonschema_lib.validate(instance=data, schema=type_schema)
        click.echo(f"Validation passed: '{file}' conforms to '{type_name}'.")

    except jsonschema_lib.ValidationError as e:
        click.echo(f"Validation failed: {e.message}")
        if e.absolute_path:
            click.echo(f"  Path: {'.'.join(str(p) for p in e.absolute_path)}")
        raise SystemExit(1) from e
    except json.JSONDecodeError as e:
        click.echo(f"Invalid JSON in '{file}': {e}")
        raise SystemExit(1) from e
    except SystemExit:
        raise
    except Exception as e:
        click.echo(f"Error: {e}")
        raise SystemExit(1) from e


@registry.command("compat")
@click.option("--type", "-t", "type_name", required=True, help="Type name to check")
@click.option(
    "--against",
    required=True,
    help="Baseline reference (e.g. .git#branch=main)",
)
@click.option(
    "--config",
    "-c",
    "config_path",
    help="Path to config file",
    default=".schema-gen.config.py",
)
def registry_compat(type_name, against, config_path):
    """Check compatibility of a type against a baseline."""
    try:
        engine = create_generation_engine(config_path)
        output_dir = Path(engine.config.output_dir)

        old_schemas = load_baseline(against, output_dir)
        new_schemas = load_current(output_dir)

        # Filter to the specific type's file
        type_filename = type_name.lower() + ".json"
        old_filtered = {k: v for k, v in old_schemas.items() if k == type_filename}
        new_filtered = {k: v for k, v in new_schemas.items() if k == type_filename}

        if not old_filtered and not new_filtered:
            click.echo(
                f"No JSON Schema file '{type_filename}' found in baseline or current."
            )
            raise SystemExit(1)

        violations = compare_schemas(old_filtered, new_filtered)

        if violations:
            click.echo(f"Compatibility issues for '{type_name}':")
            for v in violations:
                field_str = f".{v.field_name}" if v.field_name else ""
                click.echo(
                    f"  [{v.level}] {v.rule_id.value}: "
                    f"{v.schema_name}{field_str} - {v.message}"
                )
            raise SystemExit(1)
        else:
            click.echo(f"No compatibility issues for '{type_name}'.")

    except SystemExit:
        raise
    except BaselineError as e:
        click.echo(f"Baseline error: {e}")
        raise SystemExit(2) from e
    except Exception as e:
        click.echo(f"Error: {e}")
        raise SystemExit(2) from e


if __name__ == "__main__":
    main()
