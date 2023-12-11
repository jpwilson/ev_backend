"""add tenure dates to make_ceo_association

Revision ID: 7a920b3f1e8a
Revises: fef08c46f1fd
Create Date: 2023-12-10 14:53:37.520388

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "7a920b3f1e8a"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    # Add start_date and end_date columns to make_ceo_association table
    op.add_column(
        "make_ceo_association", sa.Column("start_date", sa.Date(), nullable=True)
    )
    op.add_column(
        "make_ceo_association", sa.Column("end_date", sa.Date(), nullable=True)
    )


def downgrade():
    # Remove start_date and end_date columns from make_ceo_association table
    op.drop_column("make_ceo_association", "start_date")
    op.drop_column("make_ceo_association", "end_date")
