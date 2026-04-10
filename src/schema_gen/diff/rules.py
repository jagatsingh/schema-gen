"""Rule definitions and strictness levels for breaking change detection."""

from dataclasses import dataclass
from enum import Enum


class StrictnessLevel(Enum):
    """Strictness levels for breaking change detection.

    Higher levels include all rules from lower levels.
    """

    WIRE = "WIRE"
    WIRE_JSON = "WIRE_JSON"
    SOURCE = "SOURCE"


class RuleId(Enum):
    """Identifiers for individual breaking change rules."""

    # WIRE level — serialization-breaking
    TYPE_NO_DELETE = "TYPE_NO_DELETE"
    FIELD_NO_DELETE = "FIELD_NO_DELETE"
    FIELD_SAME_TYPE = "FIELD_SAME_TYPE"
    FIELD_TYPE_NARROWED = "FIELD_TYPE_NARROWED"
    FIELD_REQUIRED_ADDED = "FIELD_REQUIRED_ADDED"
    ENUM_VALUE_NO_DELETE = "ENUM_VALUE_NO_DELETE"

    # WIRE_JSON level — adds JSON key identity
    FIELD_SAME_NAME = "FIELD_SAME_NAME"
    ENUM_VALUE_SAME_NAME = "ENUM_VALUE_SAME_NAME"


@dataclass(frozen=True)
class Violation:
    """A single breaking change violation."""

    rule_id: RuleId
    schema_name: str
    field_name: str | None
    message: str
    level: StrictnessLevel


# Maps each rule to the minimum strictness level that checks it.
RULE_LEVELS: dict[RuleId, StrictnessLevel] = {
    RuleId.TYPE_NO_DELETE: StrictnessLevel.WIRE,
    RuleId.FIELD_NO_DELETE: StrictnessLevel.WIRE,
    RuleId.FIELD_SAME_TYPE: StrictnessLevel.WIRE,
    RuleId.FIELD_TYPE_NARROWED: StrictnessLevel.WIRE,
    RuleId.FIELD_REQUIRED_ADDED: StrictnessLevel.WIRE,
    RuleId.ENUM_VALUE_NO_DELETE: StrictnessLevel.WIRE,
    RuleId.FIELD_SAME_NAME: StrictnessLevel.WIRE_JSON,
    RuleId.ENUM_VALUE_SAME_NAME: StrictnessLevel.WIRE_JSON,
}

# Ordered levels for comparison (lower index = less strict).
_LEVEL_ORDER = [StrictnessLevel.WIRE, StrictnessLevel.WIRE_JSON, StrictnessLevel.SOURCE]


def level_includes(active: StrictnessLevel, rule_level: StrictnessLevel) -> bool:
    """Return True if *active* strictness includes rules at *rule_level*."""
    return _LEVEL_ORDER.index(active) >= _LEVEL_ORDER.index(rule_level)
