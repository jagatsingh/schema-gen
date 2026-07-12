"""Tests for ``Field(alias=...)`` wire-name override (issue #108).

The alias= kwarg lets a schema author keep one Python attribute name
while serializing under a different wire-format key — most commonly
``_underscore_prefixed`` keys that mirror an existing serde
``#[serde(rename = "_x")]`` convention. This test module locks in:

* The ``alias`` is plumbed from ``Field()`` → ``FieldInfo`` → USR.
* Pydantic emits ``Field(..., alias=...)`` AND auto-enables
  ``populate_by_name=True`` on the model.
* Rust emits ``#[serde(rename = "<alias>")]`` and suppresses the
  redundant rename when the alias already matches the emitted ident.
* JSON Schema lifts the alias to the ``properties`` key (and
  propagates to ``required``).
* Zod emits the alias as the property key.
* Other generators (avro/protobuf/jackson/...) don't crash on an
  alias-bearing schema even though they don't currently honor it.
* Schema-level validation rejects alias collisions.
"""

import json
import re

import pytest

from schema_gen import Field, Schema
from schema_gen.core.schema import SchemaRegistry
from schema_gen.core.usr import USRSchema
from schema_gen.generators.jsonschema_generator import JsonSchemaGenerator
from schema_gen.generators.pydantic_generator import PydanticGenerator
from schema_gen.generators.rust_generator import RustGenerator
from schema_gen.generators.zod_generator import ZodGenerator
from schema_gen.parsers.schema_parser import SchemaParser


@pytest.fixture(autouse=True)
def _clear_registry():
    SchemaRegistry._schemas.clear()
    yield
    SchemaRegistry._schemas.clear()


def _build_alias_schema() -> USRSchema:
    """Mirror the StrategyDefV4 example from the issue."""

    @Schema
    class StrategyDef:
        """A strategy definition."""

        name: str = Field(description="Display name")
        coalesce_reasoning: str | None = Field(
            default=None,
            alias="_coalesce_reasoning",
            description="Compiler metadata (not consumed at runtime).",
        )

    return SchemaParser().parse_schema(StrategyDef)


# ----------------------------------------------------------------------
# Plumbing — Field() → FieldInfo → USRField
# ----------------------------------------------------------------------


def test_field_carries_alias_attribute():
    """``Field(alias=...)`` populates ``FieldInfo.alias`` verbatim."""
    info = Field(alias="_wire_name")
    assert info.alias == "_wire_name"


def test_field_default_alias_is_none():
    """When unset, ``alias`` defaults to ``None`` (no behavior change)."""
    assert Field().alias is None


def test_alias_propagates_into_usr_field():
    """Parser surfaces ``alias`` on the resulting USR field."""
    schema = _build_alias_schema()
    aliased = next(f for f in schema.fields if f.name == "coalesce_reasoning")
    assert aliased.alias == "_coalesce_reasoning"
    plain = next(f for f in schema.fields if f.name == "name")
    assert plain.alias is None


# ----------------------------------------------------------------------
# Pydantic
# ----------------------------------------------------------------------


def test_pydantic_emits_field_alias_and_populate_by_name():
    out = PydanticGenerator().generate_file(_build_alias_schema())
    assert 'alias="_coalesce_reasoning"' in out
    assert "populate_by_name=True" in out
    assert "serialize_by_alias=True" in out
    # The rename must NOT clobber the unrelated field.
    assert re.search(r"\bname:\s*str\s*=\s*Field\(", out)
    # ``from_attributes=True`` must still be present (pre-existing behavior).
    assert "from_attributes=True" in out


def test_pydantic_no_alias_no_populate_by_name_drift():
    """A schema without aliases must NOT acquire ``populate_by_name``.

    Two assertions, two failure modes:
      * if the alias machinery wrongly fires for non-aliased schemas, a
        ``model_config`` block appears that wouldn't exist before, AND
      * if the auto-enable logic misfires when a config block IS emitted
        for some other reason (e.g. a relationship field), it must NOT
        carry ``populate_by_name``.
    """

    @Schema
    class Plain:
        x: int = Field()

    out = PydanticGenerator().generate_file(SchemaParser().parse_schema(Plain))
    # Bare schema → no ConfigDict at all (current pre-#108 behavior).
    assert "model_config = ConfigDict" not in out
    assert "populate_by_name" not in out
    assert "serialize_by_alias" not in out

    # Schema that DOES emit a config block (relationship triggers it)
    # must still not carry populate_by_name or serialize_by_alias when no alias is present.
    @Schema
    class Related:
        owner_id: int = Field(relationship="many_to_one", foreign_key="users.id")

    out2 = PydanticGenerator().generate_file(SchemaParser().parse_schema(Related))
    assert "model_config = ConfigDict" in out2
    assert "populate_by_name" not in out2
    assert "serialize_by_alias" not in out2


def test_pydantic_warns_when_config_disables_populate_by_name(caplog):
    """Explicit ``populate_by_name=False`` + alias is a contract conflict."""
    import logging

    from schema_gen.core.config import Config

    @Schema
    class Conflicted:
        x: str = Field(alias="_x")

    cfg = Config(targets=["pydantic"], pydantic={"populate_by_name": False})
    gen = PydanticGenerator(config=cfg)

    with caplog.at_level(
        logging.WARNING, logger="schema_gen.generators.pydantic_generator"
    ):
        out = gen.generate_file(SchemaParser().parse_schema(Conflicted))

    assert "populate_by_name=False" in out
    assert any(
        "populate_by_name" in rec.getMessage() and "conflicts" in rec.getMessage()
        for rec in caplog.records
    ), [r.getMessage() for r in caplog.records]


def test_pydantic_alias_works_in_generated_module(tmp_path, monkeypatch):
    """Smoke-compile the Pydantic output and confirm both keys deserialize."""
    pytest.importorskip("pydantic")

    import importlib
    import sys

    out = PydanticGenerator().generate_file(_build_alias_schema())
    module_dir = tmp_path / "alias_pkg"
    module_dir.mkdir()
    (module_dir / "__init__.py").write_text("")
    (module_dir / "alias_models.py").write_text(out)
    monkeypatch.syspath_prepend(str(tmp_path))
    # Drop any stale module entries from a previous test run.
    sys.modules.pop("alias_pkg", None)
    sys.modules.pop("alias_pkg.alias_models", None)
    mod = importlib.import_module("alias_pkg.alias_models")
    StrategyDef = mod.StrategyDef

    # Wire key (alias) must be accepted.
    inst = StrategyDef.model_validate({"name": "foo", "_coalesce_reasoning": "because"})
    assert inst.coalesce_reasoning == "because"

    # Python attribute name must ALSO be accepted (populate_by_name=True).
    inst2 = StrategyDef.model_validate(
        {"name": "foo", "coalesce_reasoning": "via_python"}
    )
    assert inst2.coalesce_reasoning == "via_python"

    # With serialize_by_alias=True in ConfigDict, model_dump() defaults to
    # alias keys. Explicit by_alias=False overrides back to Python names.
    assert inst.model_dump()["_coalesce_reasoning"] == "because"
    assert inst.model_dump(by_alias=True)["_coalesce_reasoning"] == "because"
    assert "coalesce_reasoning" in inst.model_dump(by_alias=False)


# ----------------------------------------------------------------------
# Rust serde
# ----------------------------------------------------------------------


def test_rust_emits_serde_rename_for_alias():
    out = RustGenerator().generate_file(_build_alias_schema())
    assert '#[serde(rename = "_coalesce_reasoning"' in out
    # The Rust ident drops leading underscores via _snake_case, so the
    # field name in the struct stays canonical Rust snake_case.
    assert "pub coalesce_reasoning: Option<String>" in out


def test_rust_suppresses_rename_when_alias_matches_ident():
    """``alias`` equal to the emitted Rust ident → no rename attribute."""

    @Schema
    class Item:
        # The emitted ident is ``payload`` (already snake_case); alias
        # equal to that string is a no-op.
        payload: str = Field(alias="payload")

    out = RustGenerator().generate_file(SchemaParser().parse_schema(Item))
    assert "rename" not in out
    assert "pub payload: String," in out


def test_rust_alias_with_raw_identifier_emits_rename():
    """``alias="r#type"`` on a field named ``type`` must NOT be suppressed.

    Codex Stage-2 review (PR #109) flagged the original implementation
    for comparing ``alias`` against the Rust identifier (``emitted_name``,
    which would be ``r#type`` here). Serde serializes raw identifiers
    under their bare wire key (``"type"``) by default, so the user's
    ``alias="r#type"`` must lower to an explicit
    ``#[serde(rename = "r#type")]`` — otherwise the serialized payload
    would carry the bare ``"type"`` and silently drop the user's intent.
    """

    @Schema
    class Reserved:
        type: str = Field(alias="r#type")  # noqa: A003 — testing reserved-word handling

    out = RustGenerator().generate_file(SchemaParser().parse_schema(Reserved))
    # The struct field uses the raw-identifier form (Rust requires it).
    assert "pub r#type: String," in out
    # The rename attribute MUST be present because the alias doesn't
    # match serde's default wire key (``"type"``).
    assert '#[serde(rename = "r#type"' in out


def test_rust_alias_equal_to_default_wire_key_for_reserved_word_is_suppressed():
    """``alias="type"`` on a field named ``type`` is the serde default →
    no redundant rename emitted."""

    @Schema
    class Reserved:
        type: str = Field(alias="type")  # noqa: A003 — testing reserved-word handling

    out = RustGenerator().generate_file(SchemaParser().parse_schema(Reserved))
    assert "pub r#type: String," in out
    # alias matches serde's default wire key, so no rename is needed.
    assert "rename" not in out


def test_rust_alias_overrides_default_wire_heuristic():
    """``alias`` wins over the existing camelCase auto-rename behavior."""

    @Schema
    class Quote:
        # Without alias, the Rust generator would emit ``rename = "fooBar"``
        # because ``fooBar`` has uppercase. With alias, the user wins.
        fooBar: str = Field(alias="fooBarOverride")  # noqa: N815

    out = RustGenerator().generate_file(SchemaParser().parse_schema(Quote))
    assert '#[serde(rename = "fooBarOverride"' in out
    assert '#[serde(rename = "fooBar"' not in out


def test_rust_tag_constants_use_alias():
    """``_FIELDS`` constants surface the wire-format key, not the Python name."""

    @Schema
    class Tagged:
        kept: str = Field(tags=["wire"])
        renamed: str = Field(alias="_renamed", tags=["wire"])

    out = RustGenerator().generate_file(SchemaParser().parse_schema(Tagged))
    assert 'pub const WIRE_FIELDS: &[&str] = &["kept", "_renamed"];' in out


# ----------------------------------------------------------------------
# JSON Schema
# ----------------------------------------------------------------------


def test_jsonschema_emits_property_under_alias_key():
    out = JsonSchemaGenerator().generate_file(_build_alias_schema())
    parsed = json.loads(out)
    base = parsed["$defs"]["StrategyDef"]
    assert "_coalesce_reasoning" in base["properties"]
    assert "coalesce_reasoning" not in base["properties"]
    # The non-aliased field must be untouched.
    assert "name" in base["properties"]
    # ``required`` carries the wire name when the field is required.
    assert base["required"] == ["name"]


def test_jsonschema_required_uses_alias_for_required_aliased_field():
    @Schema
    class Mandatory:
        forced: str = Field(alias="_forced")

    out = JsonSchemaGenerator().generate_file(SchemaParser().parse_schema(Mandatory))
    parsed = json.loads(out)
    assert parsed["$defs"]["Mandatory"]["required"] == ["_forced"]


# ----------------------------------------------------------------------
# Zod
# ----------------------------------------------------------------------


def test_zod_emits_alias_as_property_key():
    out = ZodGenerator().generate_file(_build_alias_schema())
    # Underscore-prefixed identifiers are valid bare JS keys, so the
    # alias appears unquoted.
    assert re.search(r"^\s*_coalesce_reasoning:", out, re.MULTILINE)
    # The unaliased Python attribute name must NOT appear as a key —
    # use a word-boundary check so we don't false-match on the alias
    # which contains it as a suffix.
    assert not re.search(r"^\s*coalesce_reasoning:", out, re.MULTILINE)
    assert re.search(r"^\s*name:", out, re.MULTILINE)


def test_zod_quotes_alias_when_not_a_valid_js_identifier():
    @Schema
    class Hyphenated:
        # Hyphen → not a bare JS identifier → must be quoted.
        kebab: str = Field(alias="kebab-case-key")

    out = ZodGenerator().generate_file(SchemaParser().parse_schema(Hyphenated))
    assert "'kebab-case-key':" in out


def test_zod_tag_constants_use_alias():
    @Schema
    class Tagged:
        kept: str = Field(tags=["wire"])
        renamed: str = Field(alias="_renamed", tags=["wire"])

    out = ZodGenerator().generate_file(SchemaParser().parse_schema(Tagged))
    assert "export const WIRE_FIELDS = ['kept', '_renamed'] as const;" in out


# ----------------------------------------------------------------------
# Validation — alias collisions
# ----------------------------------------------------------------------


def test_two_fields_with_same_alias_rejected():
    """Two aliases pointing at the same wire key fail at parse time."""

    @Schema
    class Collide:
        a: str = Field(alias="shared")
        b: str = Field(alias="shared")

    with pytest.raises(ValueError, match="alias 'shared' collides"):
        SchemaParser().parse_schema(Collide)


def test_alias_collides_with_other_field_name_rejected():
    """An alias that shadows a sibling's Python name is rejected."""

    @Schema
    class Shadow:
        a: str = Field(alias="b")
        b: str = Field()

    with pytest.raises(ValueError, match="collides"):
        SchemaParser().parse_schema(Shadow)


def test_empty_alias_string_rejected():
    """Empty-string alias is a contract bug — reject at parse time."""

    @Schema
    class Empty:
        x: str = Field(alias="")

    with pytest.raises(ValueError, match="alias must be a non-empty string"):
        SchemaParser().parse_schema(Empty)


def test_rust_alias_with_special_chars_is_escaped():
    """Quotes / backslashes in an alias must not break the emitted Rust."""

    @Schema
    class Tricky:
        owner: str = Field(alias='owner"id')
        path: str = Field(alias=r"a\b")

    out = RustGenerator().generate_file(SchemaParser().parse_schema(Tricky))
    # The double-quote inside the alias is escaped so the rename
    # attribute remains a syntactically valid Rust string literal.
    assert r'#[serde(rename = "owner\"id"' in out
    assert r'#[serde(rename = "a\\b"' in out


def test_zod_alias_with_special_chars_is_escaped():
    """Apostrophe / backslash in an alias must not break the emitted TS."""

    @Schema
    class Tricky:
        owner: str = Field(alias="owner's-id")
        path: str = Field(alias=r"a\b")

    out = ZodGenerator().generate_file(SchemaParser().parse_schema(Tricky))
    # Single-quoted JS literals require apostrophes to be backslash-
    # escaped; backslashes must be doubled. Without escaping the
    # generated ``z.object`` would not parse as TypeScript.
    assert r"'owner\'s-id':" in out
    assert r"'a\\b':" in out


def test_alias_equal_to_own_field_name_is_no_op():
    """``alias=name`` is permitted (no-op) — the user may write it for
    documentation or as a defensive default."""

    @Schema
    class NoOp:
        x: str = Field(alias="x")

    schema = SchemaParser().parse_schema(NoOp)
    assert schema.fields[0].alias == "x"


# ----------------------------------------------------------------------
# Smoke test for generators that don't yet honor alias.
# ----------------------------------------------------------------------


def test_other_generators_do_not_crash_on_alias():
    """Non-Pydantic/Rust/JSON-Schema/Zod generators must remain operable.

    Per the issue scope they don't yet honor ``alias`` (they continue to
    emit the Python attribute name) but they MUST NOT crash.
    """
    schema = _build_alias_schema()

    from schema_gen.generators.avro_generator import AvroGenerator
    from schema_gen.generators.dataclasses_generator import DataclassesGenerator
    from schema_gen.generators.graphql_generator import GraphQLGenerator
    from schema_gen.generators.jackson_generator import JacksonGenerator
    from schema_gen.generators.kotlin_generator import KotlinGenerator
    from schema_gen.generators.pathway_generator import PathwayGenerator
    from schema_gen.generators.protobuf_generator import ProtobufGenerator
    from schema_gen.generators.sqlalchemy_generator import SqlAlchemyGenerator
    from schema_gen.generators.typeddict_generator import TypedDictGenerator

    for gen_cls in (
        AvroGenerator,
        DataclassesGenerator,
        GraphQLGenerator,
        JacksonGenerator,
        KotlinGenerator,
        PathwayGenerator,
        ProtobufGenerator,
        SqlAlchemyGenerator,
        TypedDictGenerator,
    ):
        out = gen_cls().generate_file(schema)
        assert isinstance(out, str)
        assert out  # non-empty
