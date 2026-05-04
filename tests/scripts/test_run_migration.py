"""Phase 1 stabilization: schema_migrations must be keyed by (name, table_scope).

Without a real Postgres in CI, we verify the SQL strings the script issues:
- the DDL declares a composite primary key
- the upgrade DO-block detects single-column legacy PK and rewrites it
- record_applied uses ON CONFLICT (name, table_scope)
- already_applied filters by both name and table_scope
"""
from unittest.mock import MagicMock

import scripts.run_migration as rm


def test_ddl_uses_composite_primary_key():
    assert "PRIMARY KEY (name, table_scope)" in rm.SCHEMA_MIGRATIONS_DDL


def test_upgrade_block_detects_legacy_single_column_pk():
    upgrade = rm.SCHEMA_MIGRATIONS_UPGRADE
    # Detects the old shape...
    assert "pk_cols = 'name'" in upgrade
    # ...drops the existing primary key constraint...
    assert "DROP CONSTRAINT schema_migrations_pkey" in upgrade
    # ...and installs the composite one in the same transaction.
    assert "ADD PRIMARY KEY (name, table_scope)" in upgrade


def test_record_applied_uses_composite_conflict_target():
    cur = MagicMock()
    rm.record_applied(cur, "0003_pgvector.sql", "jobs_profile2")
    sql, params = cur.execute.call_args[0]
    assert "ON CONFLICT (name, table_scope)" in sql
    assert params == ("0003_pgvector.sql", "jobs_profile2")


def test_already_applied_filters_by_table_scope():
    cur = MagicMock()
    cur.fetchone.return_value = None
    rm.already_applied(cur, "0003_pgvector.sql", "jobs_profile2")
    sql, params = cur.execute.call_args[0]
    assert "name = %s" in sql
    assert "table_scope = %s" in sql
    assert params == ("0003_pgvector.sql", "jobs_profile2")


def test_ensure_tracking_table_runs_ddl_then_upgrade():
    # Ordering matters: legacy DBs need DDL noop'd first, then the upgrade
    # block detects and rewrites. Reversing would leave a broken state if
    # the table didn't exist yet.
    cur = MagicMock()
    rm.ensure_tracking_table(cur)
    calls = [c[0][0] for c in cur.execute.call_args_list]
    assert len(calls) == 2
    assert calls[0] is rm.SCHEMA_MIGRATIONS_DDL
    assert calls[1] is rm.SCHEMA_MIGRATIONS_UPGRADE
