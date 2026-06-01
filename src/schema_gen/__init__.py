"""
Schema Gen - Universal schema converter for Python

Define schemas once, generate everywhere. Convert between Pydantic, SQLAlchemy,
Pathway, and other schema formats from a single source of truth.

Example:
    from schema_gen import Schema, Field

    @Schema
    class User:
        name: str = Field(max_length=100)
        email: str = Field(format="email")
        age: int | None = Field(default=None)
"""

from .core.config import Config
from .core.schema import Field, Schema, register_union

__version__ = "0.3.22"
__all__ = ["Schema", "Field", "Config", "register_union", "__version__"]
