"""Shared pytest fixtures for the schema-gen test suite."""

import pytest

from schema_gen.core.schema import SchemaRegistry


@pytest.fixture(autouse=True)
def _clear_standalone_unions():
    """Clear the standalone-union registry between tests (#131).

    ``register_union`` writes to a process-global ``SchemaRegistry._unions``
    that ``parse_all_schemas`` reads. Most tests clear ``_schemas`` in their
    own ``setup_method`` but predate ``_unions``, so a union registered by
    one test would otherwise leak into every later test that calls
    ``parse_all_schemas``. Clearing after each test keeps suites isolated
    regardless of run order.
    """
    yield
    SchemaRegistry._unions.clear()
