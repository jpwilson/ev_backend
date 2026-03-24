"""add newsletter and contact tables

Revision ID: c4e9a1b2f3d6
Revises: 2de6c73b3ad5
Create Date: 2026-03-24 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "c4e9a1b2f3d6"
down_revision = "2de6c73b3ad5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "newsletter_subscribers",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("email", sa.String(), nullable=False, unique=True, index=True),
        sa.Column("subscribed_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("unsubscribed_at", sa.DateTime(), nullable=True),
    )

    op.create_table(
        "contact_submissions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("submitted_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("contact_submissions")
    op.drop_table("newsletter_subscribers")
