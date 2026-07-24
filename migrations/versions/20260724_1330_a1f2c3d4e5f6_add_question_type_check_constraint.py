"""add question_type check constraint on quiz_question

Revision ID: a1f2c3d4e5f6
Revises: 054ea7d49cfb
Create Date: 2026-07-24 13:30:00.000000

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = 'a1f2c3d4e5f6'
down_revision = '054ea7d49cfb'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('quiz_question', schema=None) as batch_op:
        batch_op.create_check_constraint(
            'ck_quiz_question_type',
            "question_type IN ('mcq', 'true_false', 'short_answer')",
        )


def downgrade():
    with op.batch_alter_table('quiz_question', schema=None) as batch_op:
        batch_op.drop_constraint('ck_quiz_question_type', type_='check')
