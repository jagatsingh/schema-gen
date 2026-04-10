"""End-to-end compile-check tests for generated code.

Defines a representative set of @Schema classes covering the hardest cases,
generates all 4 targets (Rust, Pydantic, Zod, JSON Schema), and validates
the output actually compiles/imports/parses.

This is the highest-leverage test in the suite — it would have caught the
__init__.py vs lib.rs bug, missing use statements, duplicate enums, and
Box<T> omission that only surfaced in downstream POC consumers.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
from enum import StrEnum, nonmember
from pathlib import Path
from typing import Annotated, Literal

import pytest

from schema_gen import Field, Schema
from schema_gen.core.config import Config
from schema_gen.core.generator import SchemaGenerationEngine
from schema_gen.core.schema import SchemaRegistry
from schema_gen.core.usr import FieldType, USRField, USRSchema
from schema_gen.generators.rust_generator import RustGenerator

# -----------------------------------------------------------------------
# Schema fixtures — module-level for forward-reference resolution
# -----------------------------------------------------------------------


class E2EExchange(StrEnum):
    """Mixed-case enum values."""

    NSE = "NSE"
    BSE = "BSE"


class E2ESide(StrEnum):
    buy = "buy"
    sell = "sell"

    SerdeMeta = nonmember(
        type(
            "SerdeMeta",
            (),
            {
                "raw_code": (
                    "impl E2ESide {\n"
                    "    pub fn is_buy(&self) -> bool {\n"
                    "        matches!(self, Self::Buy)\n"
                    "    }\n"
                    "}"
                )
            },
        )
    )


@Schema
class E2EAddress:
    """Simple struct with optional + required fields."""

    street: str = Field(description="Street address")
    city: str
    zip_code: str | None = Field(default=None)


@Schema
class E2ECustomer:
    """Nested struct reference (A references B)."""

    name: str
    exchange: E2EExchange
    address: E2EAddress


@Schema
class E2ECeLeg:
    option_type: Literal["CE"]
    strike: float


@Schema
class E2EPeLeg:
    option_type: Literal["PE"]
    strike: float


@Schema
class E2EOrder:
    """Discriminated union with integer width override."""

    side: E2ESide
    quantity: int = Field(rust={"type": "u32"})
    leg: Annotated[E2ECeLeg | E2EPeLeg, Field(discriminator="option_type")]


# -----------------------------------------------------------------------
# Rust Box<T> test — uses USR directly (no forward-ref issue)
# -----------------------------------------------------------------------


def _make_tree_node_schema() -> USRSchema:
    """Direct self-reference: parent: Optional[TreeNode] → Box<T>."""
    return USRSchema(
        name="E2ETreeNode",
        fields=[
            USRField(name="value", type=FieldType.INTEGER, python_type=int),
            USRField(
                name="parent",
                type=FieldType.NESTED_SCHEMA,
                python_type=str,
                nested_schema="E2ETreeNode",
                optional=True,
            ),
            USRField(
                name="children",
                type=FieldType.LIST,
                python_type=list,
                inner_type=USRField(
                    name="children_item",
                    type=FieldType.NESTED_SCHEMA,
                    python_type=str,
                    nested_schema="E2ETreeNode",
                ),
            ),
        ],
    )


# -----------------------------------------------------------------------
# Test class
# -----------------------------------------------------------------------


class TestE2ECompile:
    """Generate all targets and validate the output compiles."""

    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path: Path):
        self.out_dir = tmp_path / "out"
        self.out_dir.mkdir()

        # Register all schemas
        SchemaRegistry._schemas.clear()
        for cls in (
            E2EAddress,
            E2ECustomer,
            E2ECeLeg,
            E2EPeLeg,
            E2EOrder,
        ):
            SchemaRegistry.register(cls)

    def _generate_targets(self, targets: list[str]) -> None:
        config = Config(
            input_dir=str(self.out_dir / "schemas"),
            output_dir=str(self.out_dir),
            targets=targets,
        )
        engine = SchemaGenerationEngine(config)
        engine.generate_all()

    # ------------------------------------------------------------------
    # Rust: cargo check
    # ------------------------------------------------------------------

    @pytest.mark.skipif(not shutil.which("cargo"), reason="cargo not installed")
    def test_rust_cargo_check(self):
        self._generate_targets(["rust"])
        rust_dir = self.out_dir / "rust"

        # Also generate the TreeNode with Box<T> — write it manually
        # since it's a USR-level fixture not in the registry.
        tree_schema = _make_tree_node_schema()
        gen = RustGenerator()
        tree_content = gen.generate_file(tree_schema)
        (rust_dir / "e2e_tree_node.rs").write_text(tree_content)

        # Add TreeNode module to lib.rs
        lib_rs = rust_dir / "lib.rs"
        lib_content = lib_rs.read_text()
        lib_content += "pub mod e2e_tree_node;\npub use e2e_tree_node::*;\n"
        lib_rs.write_text(lib_content)

        # Add missing dependencies the generated code may reference.
        cargo_toml = rust_dir / "Cargo.toml"
        cargo_content = cargo_toml.read_text()
        for dep_line in [
            'serde_json = "1"',
            'uuid = { version = "1", features = ["serde"] }',
            'rust_decimal = { version = "1", features = ["serde-with-str"] }',
        ]:
            dep_name = dep_line.split("=")[0].strip().strip('"')
            if dep_name not in cargo_content:
                cargo_content = cargo_content.rstrip() + "\n" + dep_line + "\n"

        cargo_toml.write_text(cargo_content)

        # Run cargo check
        result = subprocess.run(
            ["cargo", "check"],
            cwd=rust_dir,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, (
            f"cargo check failed:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )

    # ------------------------------------------------------------------
    # Python/Pydantic: import every generated module
    # ------------------------------------------------------------------

    def test_pydantic_import(self):
        self._generate_targets(["pydantic"])
        pydantic_dir = self.out_dir / "pydantic"

        # Load the generated directory as a package so relative imports
        # (e.g. ``from .e2eaddress_models import E2EAddress``) resolve.
        pkg_name = "_e2e_pydantic_pkg"
        pkg_spec = importlib.util.spec_from_file_location(
            pkg_name,
            pydantic_dir / "__init__.py",
            submodule_search_locations=[str(pydantic_dir)],
        )
        pkg_mod = importlib.util.module_from_spec(pkg_spec)
        sys.modules[pkg_name] = pkg_mod
        pkg_spec.loader.exec_module(pkg_mod)

        errors = []
        try:
            for py_file in sorted(pydantic_dir.glob("*.py")):
                if py_file.name.startswith("__"):
                    continue
                mod_name = f"{pkg_name}.{py_file.stem}"
                try:
                    spec = importlib.util.spec_from_file_location(mod_name, py_file)
                    mod = importlib.util.module_from_spec(spec)
                    sys.modules[mod_name] = mod
                    spec.loader.exec_module(mod)
                except Exception as exc:
                    errors.append(f"{py_file.name}: {exc}")
        finally:
            # Clean up all submodules and the synthetic package.
            for key in [k for k in sys.modules if k.startswith(pkg_name)]:
                sys.modules.pop(key, None)

        assert not errors, "Pydantic import errors:\n" + "\n".join(errors)

    # ------------------------------------------------------------------
    # Zod/TypeScript: tsc --noEmit --strict
    # ------------------------------------------------------------------

    @pytest.mark.skipif(not shutil.which("npx"), reason="npx not installed")
    def test_zod_tsc_check(self):
        self._generate_targets(["zod"])
        zod_dir = self.out_dir / "zod"

        # Create a minimal tsconfig.json
        tsconfig = {
            "compilerOptions": {
                "strict": True,
                "noEmit": True,
                "moduleResolution": "bundler",
                "target": "ES2020",
                "module": "ES2020",
                "skipLibCheck": True,
            },
            "include": ["*.ts"],
        }
        (zod_dir / "tsconfig.json").write_text(json.dumps(tsconfig))

        # Install zod locally
        result = subprocess.run(
            ["npm", "init", "-y"],
            cwd=zod_dir,
            capture_output=True,
            text=True,
            timeout=30,
        )

        result = subprocess.run(
            ["npm", "install", "zod", "typescript"],
            cwd=zod_dir,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            pytest.skip(f"npm install failed: {result.stderr}")

        result = subprocess.run(
            ["npx", "tsc", "--noEmit", "--strict"],
            cwd=zod_dir,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert result.returncode == 0, (
            f"tsc --noEmit failed:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )

    # ------------------------------------------------------------------
    # JSON Schema: valid JSON
    # ------------------------------------------------------------------

    def test_jsonschema_valid_json(self):
        self._generate_targets(["jsonschema"])
        jsonschema_dir = self.out_dir / "jsonschema"

        errors = []
        json_files = list(jsonschema_dir.glob("*.json"))
        assert json_files, "No JSON Schema files generated"

        for json_file in sorted(json_files):
            try:
                data = json.loads(json_file.read_text())
                # Basic structural validation
                assert isinstance(data, dict), (
                    f"{json_file.name}: root is not an object"
                )
            except Exception as exc:
                errors.append(f"{json_file.name}: {exc}")

        assert not errors, "JSON Schema errors:\n" + "\n".join(errors)
