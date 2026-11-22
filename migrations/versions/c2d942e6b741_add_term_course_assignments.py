"""Add term-specific instructor and section subject assignments.

Revision ID: c2d942e6b741
Revises: 84c097a3d3bb
Create Date: 2026-11-22
"""
from alembic import op
import sqlalchemy as sa


revision = 'c2d942e6b741'
down_revision = '84c097a3d3bb'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'faculty_course_assignment',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('term_id', sa.Integer(), nullable=False),
        sa.Column('faculty_id', sa.Integer(), nullable=False),
        sa.Column('course_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['course_id'], ['course.id']),
        sa.ForeignKeyConstraint(['faculty_id'], ['faculty.id']),
        sa.ForeignKeyConstraint(['term_id'], ['term.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('term_id', 'faculty_id', 'course_id', name='uq_term_faculty_course'),
    )
    op.create_table(
        'section_course_assignment',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('term_id', sa.Integer(), nullable=False),
        sa.Column('section_id', sa.Integer(), nullable=False),
        sa.Column('course_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['course_id'], ['course.id']),
        sa.ForeignKeyConstraint(['section_id'], ['section.id']),
        sa.ForeignKeyConstraint(['term_id'], ['term.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('term_id', 'section_id', 'course_id', name='uq_term_section_course'),
    )


def downgrade():
    op.drop_table('section_course_assignment')
    op.drop_table('faculty_course_assignment')
