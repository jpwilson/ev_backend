"""Add make status/description fields and car images/updated_at

Revision ID: a3f8b2c1d4e5
Revises: 1e787786a3a0
Create Date: 2026-02-05

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "a3f8b2c1d4e5"
down_revision: Union[str, None] = "1e787786a3a0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Make model: status, status_details, description, website_url, country, updated_at
    op.add_column("makes", sa.Column("status", sa.String(), nullable=True))
    op.add_column("makes", sa.Column("status_details", sa.Text(), nullable=True))
    op.add_column("makes", sa.Column("description", sa.Text(), nullable=True))
    op.add_column("makes", sa.Column("website_url", sa.String(), nullable=True))
    op.add_column("makes", sa.Column("country", sa.String(), nullable=True))
    op.add_column(
        "makes",
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=True,
        ),
    )

    # Set default status for existing makes
    op.execute("UPDATE makes SET status = 'active' WHERE status IS NULL")

    # Car model: images (JSON list), updated_at
    op.add_column(
        "cars",
        sa.Column(
            "images",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )
    op.add_column(
        "cars",
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=True,
        ),
    )

    # Set default empty list for images
    op.execute("UPDATE cars SET images = '[]'::jsonb WHERE images IS NULL")


def downgrade() -> None:
    op.drop_column("cars", "updated_at")
    op.drop_column("cars", "images")
    op.drop_column("makes", "updated_at")
    op.drop_column("makes", "country")
    op.drop_column("makes", "website_url")
    op.drop_column("makes", "description")
    op.drop_column("makes", "status_details")
    op.drop_column("makes", "status")
