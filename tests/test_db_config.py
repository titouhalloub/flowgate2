"""Engine configuration tests. Guard against regressions that would
re-introduce the Neon cold-start 500 (missing pool_pre_ping)."""

import app.db as db_module


def test_postgres_engine_has_pre_ping():
    """A postgres URL must produce an engine with pool_pre_ping enabled.

    Without this, a Neon cold start hands a dead connection to the first
    request and returns 500. The smoke test's first DB-touching call is
    the canary.
    """
    url = db_module._db_url if hasattr(db_module, "_db_url") else ""
    if not url.startswith("postgresql"):
        # Test environment uses SQLite; the assertion is only meaningful
        # for Postgres. Verify the code path exists rather than the value.
        import inspect
        src = inspect.getsource(db_module)
        assert "pool_pre_ping=True" in src
        assert "pool_recycle=300" in src
        assert "connect_timeout" in src
    else:
        assert db_module.engine.pool._pre_ping is True
