"""Output formatters for breaking change violations."""

import json

from .rules import Violation


def format_text(violations: list[Violation]) -> str:
    """Format violations as human-readable text.

    Returns an empty string when there are no violations.
    """
    if not violations:
        return ""

    lines: list[str] = []
    lines.append(f"Found {len(violations)} breaking change(s):")

    for v in violations:
        location = v.schema_name
        if v.field_name:
            location = f"{v.schema_name}.{v.field_name}"
        lines.append(f"  {v.rule_id.value:30s} {location}")
        lines.append(f"    {v.message}")

    return "\n".join(lines)


def format_json(violations: list[Violation]) -> str:
    """Format violations as a JSON array."""
    items = [
        {
            "rule": v.rule_id.value,
            "level": v.level.value,
            "schema": v.schema_name,
            "field": v.field_name,
            "message": v.message,
        }
        for v in violations
    ]
    return json.dumps(items, indent=2)


def format_github(violations: list[Violation]) -> str:
    """Format violations as GitHub Actions workflow commands.

    Emits ``::error`` annotations that render as inline PR comments
    when the workflow runs on a pull request.
    """
    lines: list[str] = []
    for v in violations:
        location = v.schema_name
        if v.field_name:
            location = f"{v.schema_name}.{v.field_name}"
        # GitHub Actions workflow command format:
        # ::error title=RULE::message
        lines.append(f"::error title={v.rule_id.value} ({location})::{v.message}")
    return "\n".join(lines)
