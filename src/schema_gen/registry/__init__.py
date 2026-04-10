"""Contract Registry API for schema-gen.

Provides an index of all types, enums, cross-references, and query
capabilities for discovering and validating schemas.
"""

from .index import build_registry_index

__all__ = ["build_registry_index"]
