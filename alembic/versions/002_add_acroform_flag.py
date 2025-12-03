"""Add acroform flag to documents

Revision ID: 002
Revises: 001
Create Date: 2024-12-03 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '002'
down_revision = '001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add acroform column to documents table
    op.add_column('documents', sa.Column('acroform', sa.Boolean(), nullable=False, server_default='false'))


def downgrade() -> None:
    # Remove acroform column
    op.drop_column('documents', 'acroform')
