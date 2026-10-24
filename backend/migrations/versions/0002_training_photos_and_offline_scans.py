"""training photos table; scans.taken_at and scans.offline

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-24 10:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('training_photos',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('class_label', sa.String(length=80), nullable=False),
    sa.Column('crop', sa.String(length=40), nullable=True),
    sa.Column('leaf_id', sa.String(length=60), nullable=True),
    sa.Column('source', sa.String(length=200), nullable=True),
    sa.Column('licence', sa.String(length=80), nullable=True),
    sa.Column('confirmed_by', sa.String(length=80), nullable=True),
    sa.Column('original_name', sa.String(length=120), nullable=True),
    sa.Column('sha256', sa.String(length=64), nullable=False),
    sa.Column('path', sa.String(length=200), nullable=False),
    sa.Column('width', sa.Integer(), nullable=False),
    sa.Column('height', sa.Integer(), nullable=False),
    sa.Column('size_bytes', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('exported_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('sha256', name='uq_training_photos_sha256')
    )
    with op.batch_alter_table('training_photos', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_training_photos_class_label'), ['class_label'], unique=False)
        batch_op.create_index(batch_op.f('ix_training_photos_created_at'), ['created_at'], unique=False)

    with op.batch_alter_table('scans', schema=None) as batch_op:
        batch_op.add_column(sa.Column('taken_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column('offline', sa.Boolean(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('scans', schema=None) as batch_op:
        batch_op.drop_column('offline')
        batch_op.drop_column('taken_at')
    with op.batch_alter_table('training_photos', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_training_photos_created_at'))
        batch_op.drop_index(batch_op.f('ix_training_photos_class_label'))
    op.drop_table('training_photos')
