"""add plans table

Revision ID: 52f9c8d7e6a5
Revises: f4ef4d0a88cd
Create Date: 2026-10-24 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision: str = '52f9c8d7e6a5'
down_revision: Union[str, Sequence[str], None] = 'f4ef4d0a88cd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'plans',
        sa.Column('id', UUID(as_uuid=True), nullable=False),
        sa.Column('org_id', UUID(as_uuid=True), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('engagement_id', UUID(as_uuid=True), sa.ForeignKey('engagements.id'), nullable=False),
        sa.Column('source', sa.String(length=255), nullable=False),
        sa.Column('target', sa.String(length=255), nullable=False),
        sa.Column('rag_used', sa.Boolean(), nullable=False),
        sa.Column('used_llm', sa.Boolean(), nullable=False),
        sa.Column('path_json', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    op.drop_table('plans')
