"""JSON Schema comparison engine for breaking change detection."""

from typing import Any

from .rules import (
    RULE_LEVELS,
    RuleId,
    StrictnessLevel,
    Violation,
    level_includes,
)

# Type widening is safe (e.g. integer -> number), narrowing is breaking.
# Maps JSON Schema type string to a numeric "width" — higher = wider.
_TYPE_WIDTH: dict[str, int] = {
    "integer": 1,
    "number": 2,  # number ⊃ integer
}


def compare_schemas(
    old: dict[str, dict[str, Any]],
    new: dict[str, dict[str, Any]],
    level: StrictnessLevel = StrictnessLevel.WIRE_JSON,
    ignore: list[str] | None = None,
) -> list[Violation]:
    """Compare two sets of JSON Schema files and return breaking change violations.

    Args:
        old: Baseline schemas ``{filename: parsed_json_dict}``.
        new: Current schemas ``{filename: parsed_json_dict}``.
        level: Strictness level controlling which rules are active.
        ignore: Rule IDs (strings) to suppress.

    Returns:
        List of :class:`Violation` instances, sorted by schema name.
    """
    ignore_set = set(ignore or [])
    violations: list[Violation] = []

    for filename, old_schema in old.items():
        new_schema = new.get(filename)
        if new_schema is None:
            # Entire file removed — each $defs type is a TYPE_NO_DELETE.
            violations.extend(
                _violations_for_deleted_file(old_schema, filename, level, ignore_set)
            )
            continue

        violations.extend(
            _compare_schema_file(old_schema, new_schema, level, ignore_set)
        )

    violations.sort(key=lambda v: (v.schema_name, v.field_name or ""))
    return violations


def _violations_for_deleted_file(
    old_schema: dict[str, Any],
    filename: str,
    level: StrictnessLevel,
    ignore_set: set[str],
) -> list[Violation]:
    """Generate TYPE_NO_DELETE violations for every type in a removed file."""
    violations: list[Violation] = []
    rule = RuleId.TYPE_NO_DELETE
    if not _should_check(rule, level, ignore_set):
        return violations

    defs = old_schema.get("$defs", {})
    for type_name in defs:
        violations.append(
            Violation(
                rule_id=rule,
                schema_name=type_name,
                field_name=None,
                message=f"Schema '{type_name}' was deleted (file {filename} removed)",
                level=RULE_LEVELS[rule],
            )
        )
    return violations


def _compare_schema_file(
    old: dict[str, Any],
    new: dict[str, Any],
    level: StrictnessLevel,
    ignore_set: set[str],
) -> list[Violation]:
    """Compare two JSON Schema file dicts and return violations."""
    violations: list[Violation] = []
    old_defs = old.get("$defs", {})
    new_defs = new.get("$defs", {})

    # Check for deleted types.
    if _should_check(RuleId.TYPE_NO_DELETE, level, ignore_set):
        for type_name in old_defs:
            if type_name not in new_defs:
                violations.append(
                    Violation(
                        rule_id=RuleId.TYPE_NO_DELETE,
                        schema_name=type_name,
                        field_name=None,
                        message=f"Schema '{type_name}' was deleted",
                        level=RULE_LEVELS[RuleId.TYPE_NO_DELETE],
                    )
                )

    # Compare shared types.
    for type_name in old_defs:
        if type_name not in new_defs:
            continue
        old_def = old_defs[type_name]
        new_def = new_defs[type_name]
        violations.extend(
            _compare_type_def(type_name, old_def, new_def, level, ignore_set)
        )

    return violations


def _compare_type_def(
    type_name: str,
    old_def: dict[str, Any],
    new_def: dict[str, Any],
    level: StrictnessLevel,
    ignore_set: set[str],
) -> list[Violation]:
    """Compare two ``$defs`` type definitions."""
    violations: list[Violation] = []

    old_props = old_def.get("properties", {})
    new_props = new_def.get("properties", {})
    old_required = set(old_def.get("required", []))
    new_required = set(new_def.get("required", []))

    # --- FIELD_NO_DELETE ---
    if _should_check(RuleId.FIELD_NO_DELETE, level, ignore_set):
        for field_name in old_props:
            if field_name not in new_props:
                violations.append(
                    Violation(
                        rule_id=RuleId.FIELD_NO_DELETE,
                        schema_name=type_name,
                        field_name=field_name,
                        message=f"Field '{field_name}' was deleted from '{type_name}'",
                        level=RULE_LEVELS[RuleId.FIELD_NO_DELETE],
                    )
                )

    # --- Per-field checks on shared fields ---
    for field_name in old_props:
        if field_name not in new_props:
            continue
        old_field = old_props[field_name]
        new_field = new_props[field_name]

        # FIELD_SAME_TYPE — skip width changes (integer↔number) which are
        # handled exclusively by FIELD_TYPE_NARROWED. Widening is safe and
        # produces no violation; narrowing is flagged by FIELD_TYPE_NARROWED.
        if _should_check(RuleId.FIELD_SAME_TYPE, level, ignore_set):
            old_type = _effective_type(old_field)
            new_type = _effective_type(new_field)
            if old_type != new_type:
                if not _is_type_width_change(old_type, new_type):
                    violations.append(
                        Violation(
                            rule_id=RuleId.FIELD_SAME_TYPE,
                            schema_name=type_name,
                            field_name=field_name,
                            message=(
                                f"Field '{field_name}' in '{type_name}' changed type "
                                f"from '{old_type}' to '{new_type}'"
                            ),
                            level=RULE_LEVELS[RuleId.FIELD_SAME_TYPE],
                        )
                    )

        # FIELD_TYPE_NARROWED
        if _should_check(RuleId.FIELD_TYPE_NARROWED, level, ignore_set):
            old_type = _effective_type(old_field)
            new_type = _effective_type(new_field)
            if _is_narrowing(old_type, new_type):
                violations.append(
                    Violation(
                        rule_id=RuleId.FIELD_TYPE_NARROWED,
                        schema_name=type_name,
                        field_name=field_name,
                        message=(
                            f"Field '{field_name}' in '{type_name}' was narrowed "
                            f"from '{old_type}' to '{new_type}'"
                        ),
                        level=RULE_LEVELS[RuleId.FIELD_TYPE_NARROWED],
                    )
                )

    # --- FIELD_REQUIRED_ADDED ---
    if _should_check(RuleId.FIELD_REQUIRED_ADDED, level, ignore_set):
        added_required = new_required - old_required
        # Flags any field that is now required but wasn't before — both
        # brand-new required fields and existing optional fields promoted
        # to required. Both are breaking for consumers that don't send them.
        for field_name in sorted(added_required):
            violations.append(
                Violation(
                    rule_id=RuleId.FIELD_REQUIRED_ADDED,
                    schema_name=type_name,
                    field_name=field_name,
                    message=(
                        f"New required field '{field_name}' added to '{type_name}'"
                    ),
                    level=RULE_LEVELS[RuleId.FIELD_REQUIRED_ADDED],
                )
            )

    # --- Enum checks ---
    _check_enums(type_name, old_def, new_def, level, ignore_set, violations)

    # --- WIRE_JSON checks ---
    if _should_check(RuleId.FIELD_SAME_NAME, level, ignore_set):
        _check_field_renames(type_name, old_props, new_props, violations)

    return violations


def _check_enums(
    type_name: str,
    old_def: dict[str, Any],
    new_def: dict[str, Any],
    level: StrictnessLevel,
    ignore_set: set[str],
    violations: list[Violation],
) -> None:
    """Check enum-related rules on a type definition.

    Handles both inline enums (``{"enum": [...]}`` on a property) and
    top-level enum definitions in ``$defs``.
    """
    old_enum = old_def.get("enum")
    new_enum = new_def.get("enum")

    # Enum removed entirely (constrained → unconstrained) — all values deleted.
    if old_enum is not None and new_enum is None:
        if _should_check(RuleId.ENUM_VALUE_NO_DELETE, level, ignore_set):
            for val in sorted(old_enum, key=str):
                violations.append(
                    Violation(
                        rule_id=RuleId.ENUM_VALUE_NO_DELETE,
                        schema_name=type_name,
                        field_name=None,
                        message=(
                            f"Enum value '{val}' was removed from '{type_name}' "
                            "(enum constraint removed entirely)"
                        ),
                        level=RULE_LEVELS[RuleId.ENUM_VALUE_NO_DELETE],
                    )
                )

    if old_enum is not None and new_enum is not None:
        # ENUM_VALUE_NO_DELETE
        if _should_check(RuleId.ENUM_VALUE_NO_DELETE, level, ignore_set):
            removed = set(old_enum) - set(new_enum)
            for val in sorted(removed, key=str):
                violations.append(
                    Violation(
                        rule_id=RuleId.ENUM_VALUE_NO_DELETE,
                        schema_name=type_name,
                        field_name=None,
                        message=(f"Enum value '{val}' was removed from '{type_name}'"),
                        level=RULE_LEVELS[RuleId.ENUM_VALUE_NO_DELETE],
                    )
                )

        # ENUM_VALUE_SAME_NAME — detect value changes at same positions.
        if _should_check(RuleId.ENUM_VALUE_SAME_NAME, level, ignore_set):
            for i, old_val in enumerate(old_enum):
                if i < len(new_enum) and old_val != new_enum[i]:
                    # A value at the same position changed.
                    violations.append(
                        Violation(
                            rule_id=RuleId.ENUM_VALUE_SAME_NAME,
                            schema_name=type_name,
                            field_name=None,
                            message=(
                                f"Enum value at position {i} in '{type_name}' "
                                f"changed from '{old_val}' to '{new_enum[i]}'"
                            ),
                            level=RULE_LEVELS[RuleId.ENUM_VALUE_SAME_NAME],
                        )
                    )

    # Also check inline enums on properties.
    old_props = old_def.get("properties", {})
    new_props = new_def.get("properties", {})
    for field_name in old_props:
        if field_name not in new_props:
            continue
        old_field_enum = old_props[field_name].get("enum")
        new_field_enum = new_props[field_name].get("enum")
        if old_field_enum is not None and new_field_enum is None:
            if _should_check(RuleId.ENUM_VALUE_NO_DELETE, level, ignore_set):
                for val in sorted(old_field_enum, key=str):
                    violations.append(
                        Violation(
                            rule_id=RuleId.ENUM_VALUE_NO_DELETE,
                            schema_name=type_name,
                            field_name=field_name,
                            message=(
                                f"Enum value '{val}' was removed from "
                                f"field '{field_name}' in '{type_name}' "
                                "(enum constraint removed entirely)"
                            ),
                            level=RULE_LEVELS[RuleId.ENUM_VALUE_NO_DELETE],
                        )
                    )
        if old_field_enum is not None and new_field_enum is not None:
            if _should_check(RuleId.ENUM_VALUE_NO_DELETE, level, ignore_set):
                removed = set(old_field_enum) - set(new_field_enum)
                for val in sorted(removed, key=str):
                    violations.append(
                        Violation(
                            rule_id=RuleId.ENUM_VALUE_NO_DELETE,
                            schema_name=type_name,
                            field_name=field_name,
                            message=(
                                f"Enum value '{val}' was removed from "
                                f"field '{field_name}' in '{type_name}'"
                            ),
                            level=RULE_LEVELS[RuleId.ENUM_VALUE_NO_DELETE],
                        )
                    )
            if _should_check(RuleId.ENUM_VALUE_SAME_NAME, level, ignore_set):
                for i, old_val in enumerate(old_field_enum):
                    if i < len(new_field_enum) and old_val != new_field_enum[i]:
                        violations.append(
                            Violation(
                                rule_id=RuleId.ENUM_VALUE_SAME_NAME,
                                schema_name=type_name,
                                field_name=field_name,
                                message=(
                                    f"Enum value at position {i} in field "
                                    f"'{field_name}' of '{type_name}' changed "
                                    f"from '{old_val}' to '{new_field_enum[i]}'"
                                ),
                                level=RULE_LEVELS[RuleId.ENUM_VALUE_SAME_NAME],
                            )
                        )


def _check_field_renames(
    type_name: str,
    old_props: dict[str, Any],
    new_props: dict[str, Any],
    violations: list[Violation],
) -> None:
    """Detect potential field renames (WIRE_JSON level).

    Heuristic: for each effective type, if there is exactly one removed
    field and exactly one added field with that type, it's likely a rename.
    When there are multiple removed/added fields of the same type (e.g.
    two ``string`` fields), the match is ambiguous and we skip it to avoid
    false positives.
    """
    removed = {k: v for k, v in old_props.items() if k not in new_props}
    added = {k: v for k, v in new_props.items() if k not in old_props}

    if not removed or not added:
        return

    # Group removed and added fields by effective type.
    removed_by_type: dict[str, list[str]] = {}
    for name, field in removed.items():
        t = _effective_type(field)
        removed_by_type.setdefault(t, []).append(name)

    added_by_type: dict[str, list[str]] = {}
    for name, field in added.items():
        t = _effective_type(field)
        added_by_type.setdefault(t, []).append(name)

    # Only flag renames when there is an unambiguous 1:1 match.
    for etype, removed_names in removed_by_type.items():
        added_names = added_by_type.get(etype, [])
        if len(removed_names) == 1 and len(added_names) == 1:
            violations.append(
                Violation(
                    rule_id=RuleId.FIELD_SAME_NAME,
                    schema_name=type_name,
                    field_name=removed_names[0],
                    message=(
                        f"Field '{removed_names[0]}' in '{type_name}' may have been "
                        f"renamed to '{added_names[0]}' (same type: {etype})"
                    ),
                    level=RULE_LEVELS[RuleId.FIELD_SAME_NAME],
                )
            )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _effective_type(field_schema: dict[str, Any]) -> str:
    """Return the effective JSON Schema type string for a field.

    Handles ``$ref``, ``anyOf``, plain ``type`` (string), multi-type
    arrays (e.g. ``["string", "null"]``), and ``array`` with ``items``.

    .. note::
        Inline nested objects (``{"type": "object", "properties": {...}}``)
        are represented as ``"object"`` without recursing into their
        properties.  schema-gen's own output always uses ``$ref`` +
        ``$defs`` for nested types, so this is not a practical limitation
        for generated schemas.  If a future generator emits inline nested
        objects, this function should be extended to recurse.
    """
    if "$ref" in field_schema:
        return f"$ref:{field_schema['$ref']}"
    if "anyOf" in field_schema:
        parts = sorted(_effective_type(s) for s in field_schema["anyOf"])
        return f"anyOf({','.join(parts)})"
    raw = field_schema.get("type", "any")
    if isinstance(raw, list):
        return ",".join(sorted(raw))
    type_str = str(raw)
    # Include element type for arrays so that array<string> != array<integer>.
    if type_str == "array" and "items" in field_schema:
        item_type = _effective_type(field_schema["items"])
        return f"array({item_type})"
    return type_str


def _is_type_width_change(old_type: str, new_type: str) -> bool:
    """Return True if *old_type* → *new_type* is a width change (narrowing or widening)."""
    return old_type in _TYPE_WIDTH and new_type in _TYPE_WIDTH


def _is_narrowing(old_type: str, new_type: str) -> bool:
    """Return True if *old_type* → *new_type* is a type narrowing (breaking)."""
    old_w = _TYPE_WIDTH.get(old_type)
    new_w = _TYPE_WIDTH.get(new_type)
    if old_w is not None and new_w is not None:
        return new_w < old_w
    return False


def _should_check(
    rule: RuleId,
    level: StrictnessLevel,
    ignore_set: set[str],
) -> bool:
    """Return True if *rule* should be checked given *level* and *ignore_set*."""
    if rule.value in ignore_set:
        return False
    return level_includes(level, RULE_LEVELS[rule])
