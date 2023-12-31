"""Add description and default model rep

Revision ID: dad2c4b18f57
Revises: 8f37976a01ca
Create Date: 2023-12-16 21:08:37.546040

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "dad2c4b18f57"
down_revision: Union[str, None] = "8f37976a01ca"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column(
        "cars", sa.Column("is_model_rep", sa.Boolean(), nullable=True, index=True)
    )
    op.add_column("cars", sa.Column("desc", sa.Text(), nullable=True))
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column("cars", "is_model_rep")
    op.drop_column("cars", "desc")
    # ### end Alembic commands ###
