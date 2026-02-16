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
from .core.schema import Field, Schema

__version__ = "0.2.0"
__all__ = ["Schema", "Field", "Config", "__version__"]
