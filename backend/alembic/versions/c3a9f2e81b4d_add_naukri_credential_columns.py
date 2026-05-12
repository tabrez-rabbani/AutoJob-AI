"""add naukri credential columns

Revision ID: c3a9f2e81b4d
Revises: 159c2e202cff
Create Date: 2026-03-15 01:28:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "c3a9f2e81b4d"
down_revision: Union[str, None] = "84f58b3bc3ba"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("naukri_email_enc", sa.String(500), nullable=True))
    op.add_column("users", sa.Column("naukri_password_enc", sa.String(500), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "naukri_password_enc")
    op.drop_column("users", "naukri_email_enc")
