"""Phase 2.10 — persist jurisdictions on Instrument.

Adds an nullable ``jurisdictions`` JSON list column to ``instruments``.
The ORM default (``list``) covers new rows; existing rows read NULL,
which the route layer coerces to [] ("no extra jurisdictions").
Batch mode is the SQLite-safe path for ALTER TABLE.
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers
revision = 'a27cap000015'
down_revision = 'a27cap000014'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("instruments") as batch_op:
        batch_op.add_column(sa.Column("jurisdictions", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("instruments") as batch_op:
        batch_op.drop_column("jurisdictions")
