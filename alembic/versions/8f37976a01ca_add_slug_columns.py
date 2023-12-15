"""Add slug columns

Revision ID: 8f37976a01ca
Revises: 7a920b3f1e8a
Create Date: 2023-12-15 13:19:25.602088

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "8f37976a01ca"
down_revision: Union[str, None] = "7a920b3f1e8a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("cars", sa.Column("full_slug", sa.String(), nullable=True))
    op.add_column("cars", sa.Column("make_model_slug", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("cars", "full_slug")
    op.drop_column("cars", "make_model_slug")
