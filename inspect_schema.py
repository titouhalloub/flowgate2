"""Read-only schema inspector: diffs the live DB against the ORM metadata and
prints idempotent SQL to reconcile it. NEVER executes DDL.

Why: production (Neon) was built by create_all() only, so columns added by
ALTER-type migrations may be missing. This script reports exactly what is
missing (mapped to the migration revision that added it) and prints the Step A
SQL. After applying it, run `alembic stamp a27cap000010` (Step B) so future
migrations apply cleanly on top.

Usage:
    python inspect_schema.py                          # uses DATABASE_URL
    python inspect_schema.py --url sqlite:///./a27.db # local override
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import sqlalchemy as sa  # noqa: E402
from sqlalchemy import inspect  # noqa: E402

from app.db import Base  # noqa: E402
from app import models  # noqa: E402,F401  (register tables on metadata)

HEAD = "a27cap000010"

# (table, column) -> revision that ALTER-added it. Columns of create-only
# tables have no entry here; they are labeled "create_all-era" if missing.
ALTER_SOURCE = {
    ("securities", "par_value"): "a27cap000003",
    ("cap_table_events", "target_security_id"): "a27cap000003",
    ("cap_table_events", "from_holder_id"): "a27cap000003",
    ("cap_table_events", "notes"): "a27cap000003",
    ("cap_table_events", "recorded_at"): "a27cap000003",
    ("investors", "kyc_verified"): "a27cap000004",
    ("cap_table_events", "vesting_start_date"): "a27cap000008",
    ("cap_table_events", "vesting_period_months"): "a27cap000008",
    ("cap_table_events", "cliff_months"): "a27cap000008",
    ("cap_table_events", "acceleration_clause"): "a27cap000008",
    ("cap_table_events", "is_repurchase"): "a27cap000008",
    ("cap_table_events", "repurchase_approver"): "a27cap000008",
    ("cap_table_events", "related_convertible_id"): "a27cap000010",
    ("cap_table_events", "related_round_id"): "a27cap000010",
}


def norm_type(raw) -> str:
    """Collapse dialect type spellings into a comparable bucket."""
    s = str(raw).upper()
    if "TIMESTAMP" in s:
        return "timestamp"
    if "VARCHAR" in s or "CHARACTER VARYING" in s or s.startswith("CHAR"):
        return "varchar"
    if "TEXT" in s:
        return "text"
    if "BOOL" in s:
        return "bool"
    if "DATE" in s:
        return "date"
    if "DOUBLE" in s or "FLOAT" in s or "NUMERIC" in s or "REAL" in s:
        return "float"
    if "INT" in s:
        return "int"
    if "JSON" in s:
        return "json"
    return s


def pg_type(t) -> str:
    """Postgres DDL spelling for a SQLAlchemy column type."""
    if isinstance(t, sa.Enum):
        return f"VARCHAR({t.length or 32})"
    if isinstance(t, sa.Text):
        return "TEXT"
    if isinstance(t, sa.String):
        return f"VARCHAR({t.length})" if t.length else "VARCHAR"
    if isinstance(t, sa.Boolean):
        return "BOOLEAN"
    if isinstance(t, sa.Float):
        return "DOUBLE PRECISION"
    if isinstance(t, sa.DateTime):
        return "TIMESTAMPTZ" if t.timezone else "TIMESTAMP"
    if isinstance(t, sa.Date):
        return "DATE"
    if isinstance(t, sa.Integer):
        return "INTEGER"
    if isinstance(t, sa.JSON):
        return "JSON"
    return str(t).upper()


def pg_default(col) -> str | None:
    sd = col.server_default
    if sd is None:
        return None
    arg = sd.arg
    if hasattr(arg, "text"):
        return f"DEFAULT {arg.text}"
    return f"DEFAULT {arg!r}"


def add_column_sql(table: str, col) -> str:
    parts = [
        f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col.name} {pg_type(col.type)}"
    ]
    dflt = pg_default(col)
    if dflt:
        parts.append(dflt)
    if col.nullable is False and dflt is not None:
        parts.append("NOT NULL")
    return " ".join(parts) + ";"


def needs_backfill(col) -> bool:
    """ORM NOT NULL but no server default: rows may exist, so add the column
    nullable, backfill, then SET NOT NULL in a review step."""
    return col.nullable is False and col.server_default is None


def fk_sig(cols, ref_table: str, ref_cols):
    return (tuple(sorted(cols)), ref_table, tuple(sorted(ref_cols)))


def main() -> int:
    ap = argparse.ArgumentParser(description="Read-only schema diff vs ORM metadata.")
    ap.add_argument("--url", default=None, help="DB URL; overrides DATABASE_URL env var")
    args = ap.parse_args()
    url = args.url or os.environ.get("DATABASE_URL")
    if not url:
        print("ERROR: no --url given and DATABASE_URL is not set. Nothing inspected.", file=sys.stderr)
        return 2

    engine = sa.create_engine(url)
    insp = inspect(engine)
    db_tables = set(insp.get_table_names())
    print(f"dialect: {engine.dialect.name}   tables on server: {len(db_tables)}")

    fixes: list[str] = []
    review: list[str] = []
    for table in sorted(Base.metadata.tables):
        expected = Base.metadata.tables[table]
        print(f"\n=== TABLE {table} ===")
        if table not in db_tables:
            print("  MISSING ENTIRELY (create_all() would create it at next boot)")
            review.append(f"-- TABLE {table} missing entirely; verify with app team before creating")
            continue
        actual = {c["name"]: c for c in insp.get_columns(table)}
        actual_names = set(actual)
        for col in expected.columns:
            if col.name not in actual_names:
                rev = ALTER_SOURCE.get((table, col.name))
                tag = f"ALTER-migration {rev}" if rev else "create_all-era (no chain migration adds it)"
                extra = "  (ORM NOT NULL, no server default)" if needs_backfill(col) else ""
                print(f"  MISSING COLUMN: {col.name} {pg_type(col.type)}   [{tag}]{extra}")
                fixes.append(add_column_sql(table, col))
                if needs_backfill(col):
                    review.append(
                        f"UPDATE {table} SET {col.name} = <backfill-value> WHERE {col.name} IS NULL;  -- then:\n"
                        f"-- ALTER TABLE {table} ALTER COLUMN {col.name} SET NOT NULL;"
                    )
        for name in sorted(actual_names - {c.name for c in expected.columns}):
            print(f"  EXTRA COLUMN (in DB, not in ORM): {name}")
            review.append(f"ALTER TABLE {table} DROP COLUMN IF EXISTS {name};  -- review data first")
        for col in expected.columns:
            act = actual.get(col.name)
            if act is None:
                continue
            if bool(col.nullable) and not bool(act.get("nullable")):
                print(f"  NULLABILITY: {col.name} NOT NULL on DB, ORM allows NULL")
                fixes.append(f"ALTER TABLE {table} ALTER COLUMN {col.name} DROP NOT NULL;")
            elif not bool(col.nullable) and bool(act.get("nullable")):
                print(f"  NULLABILITY: {col.name} nullable on DB, ORM requires NOT NULL (backfill needed)")
                review.append(f"-- ALTER TABLE {table} ALTER COLUMN {col.name} SET NOT NULL;  -- backfill NULLs first")
            exp_t, act_t = norm_type(col.type), norm_type(act["type"])
            if exp_t != act_t:
                print(f"  TYPE: {col.name} ORM={exp_t} DB={act_t}")
                review.append(f"-- ALTER TABLE {table} ALTER COLUMN {col.name} TYPE {pg_type(col.type)};")
            elif engine.dialect.name == "postgresql" and exp_t == "timestamp":
                exp_tz = bool(getattr(col.type, "timezone", False))
                act_tz = "TIME ZONE" in str(act["type"]).upper()
                if exp_tz != act_tz:
                    print(f"  TIMEZONE: {col.name} ORM tz={exp_tz} DB tz={act_tz}")
                    review.append(f"-- ALTER TABLE {table} ALTER COLUMN {col.name} TYPE {'TIMESTAMPTZ' if exp_tz else 'TIMESTAMP'};")
        have_idx = {i["name"] for i in insp.get_indexes(table)}
        for idx in expected.indexes:
            if idx.name and idx.name not in have_idx:
                cols = ", ".join(c.name for c in idx.columns)
                print(f"  MISSING INDEX: {idx.name} ({cols})")
                fixes.append(f'CREATE INDEX IF NOT EXISTS "{idx.name}" ON {table} ({cols});')
        want = {fk_sig([fk.parent.name], fk.column.table.name, [fk.column.name]) for fk in expected.foreign_keys}
        have = {fk_sig(f["constrained_columns"], f["referred_table"], f["referred_columns"]) for f in insp.get_foreign_keys(table)}
        for cols, ref_table, ref_cols in sorted(want - have):
            name = f"fk_{table}_" + "_".join(cols)
            print(f"  MISSING FK: {name} -> {ref_table}({', '.join(ref_cols)})")
            fixes.append(
                f"DO $$ BEGIN\n  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = '{name}') THEN\n"
                f"    ALTER TABLE {table} ADD CONSTRAINT {name} FOREIGN KEY ({', '.join(cols)}) "
                f"REFERENCES {ref_table} ({', '.join(ref_cols)});\n  END IF;\nEND $$;"
            )

    print("\n=== alembic chain state ===")
    if "alembic_version" not in db_tables:
        print("  alembic_version: ABSENT (this DB has never run the Alembic chain)")
    else:
        with engine.connect() as conn:
            row = conn.execute(sa.text("SELECT version_num FROM alembic_version")).first()
        print(f"  current revision: {row[0] if row else '(table empty)'}")

    print("\n=== STEP A SQL (review, then run manually against the DB) ===")
    print("\n".join(fixes) if fixes else "(no schema fixes needed)")
    if review:
        print("\n=== REVIEW / OPTIONAL ===")
        print("\n".join(review))
    print("\n=== VERDICT ===")
    if fixes:
        print(f"{len(fixes)} fix(es) required. After applying: python -m alembic stamp {HEAD}")
    else:
        print("schema matches ORM head; run stamp only if alembic_version is absent or stale.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

