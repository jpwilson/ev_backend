"""Add current_roles and previous_roles to Person

Revision ID: 1e787786a3a0
Revises: 2de6c73b3ad5
Create Date: 2024-08-31 17:30:15.570272

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "1e787786a3a0"
down_revision: Union[str, None] = "2de6c73b3ad5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column(
        "people",
        sa.Column(
            "current_roles", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
    )
    op.add_column(
        "people",
        sa.Column(
            "previous_roles", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
    )

    # Update existing records
    op.execute(
        'UPDATE people SET current_roles = \'[{"title": "Engineer", "company": "Company1"}]\'::jsonb WHERE current_roles IS NULL'
    )
    op.execute(
        "UPDATE people SET previous_roles = '[]'::jsonb WHERE previous_roles IS NULL"
    )
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column("people", "previous_roles")
    op.drop_column("people", "current_roles")
    # ### end Alembic commands ###
