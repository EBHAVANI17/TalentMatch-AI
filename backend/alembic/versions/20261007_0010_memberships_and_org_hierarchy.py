"""memberships and org hierarchy

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-07 13:00:00.000000

- organizations: org_type (standalone | parent | client), parent_id, allow_parent_access
- memberships: a user's role in each organization (many per user)
- user_tokens.organization_id: refresh tokens remember the active organization
- Backfill: one membership per user with an organization and an organization role.
  Idempotent (ON CONFLICT DO NOTHING); users whose organization is missing are skipped and counted.
"""
import logging
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0010'
down_revision: Union[str, None] = '0009'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

log = logging.getLogger("alembic.runtime.migration")

# Organization roles at the time of this migration (core/tenancy.py ORG_ROLES)
ORG_ROLES = ("ORG_ADMIN", "EMPLOYER_ADMIN", "RECRUITER", "HIRING_MANAGER", "INTERVIEWER", "ANALYST")


def upgrade() -> None:
    with op.batch_alter_table('organizations') as batch_op:
        batch_op.add_column(sa.Column('org_type', sa.String(length=16), server_default='standalone', nullable=False))
        batch_op.add_column(sa.Column('parent_id', sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column('allow_parent_access', sa.Boolean(), server_default=sa.false(), nullable=False))
        batch_op.create_index(batch_op.f('ix_organizations_parent_id'), ['parent_id'], unique=False)
        batch_op.create_foreign_key(batch_op.f('fk_organizations_parent_id_organizations'), 'organizations',
                                    ['parent_id'], ['id'], ondelete='RESTRICT')
        batch_op.create_check_constraint(op.f('ck_organizations_org_type_valid'), "org_type IN ('standalone', 'parent', 'client')")
        batch_op.create_check_constraint(
            op.f('ck_organizations_org_parent_matches_type'),
            "(org_type = 'client' AND parent_id IS NOT NULL) OR (org_type <> 'client' AND parent_id IS NULL)",
        )

    op.create_table('memberships',
        sa.Column('id', sa.String(length=64), nullable=False),
        sa.Column('user_id', sa.String(length=64), nullable=False),
        sa.Column('organization_id', sa.String(length=64), nullable=False),
        sa.Column('role', sa.String(length=32), nullable=False),
        sa.Column('status', sa.String(length=16), server_default='active', nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.CheckConstraint("status IN ('active', 'suspended')", name=op.f('ck_memberships_membership_status_valid')),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'],
                                name=op.f('fk_memberships_organization_id_organizations'), ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_memberships_user_id_users'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_memberships')),
    )
    op.create_index('ix_memberships_org_status', 'memberships', ['organization_id', 'status'], unique=False)
    op.create_index(op.f('ix_memberships_user_id'), 'memberships', ['user_id'], unique=False)
    op.create_index('uq_memberships_user_org', 'memberships', ['user_id', 'organization_id'], unique=True)

    with op.batch_alter_table('user_tokens') as batch_op:
        batch_op.add_column(sa.Column('organization_id', sa.String(length=64), nullable=True))
        batch_op.create_foreign_key(batch_op.f('fk_user_tokens_organization_id_organizations'), 'organizations',
                                    ['organization_id'], ['id'], ondelete='SET NULL')

    backfill_memberships(op.get_bind())


def backfill_memberships(conn) -> int:
    """Returns the number of memberships created. Also used by tests to prove re-runs are no-ops."""
    roles = ", ".join(f"'{r}'" for r in ORG_ROLES)
    skipped = conn.execute(sa.text(
        f"SELECT COUNT(*) FROM users u LEFT JOIN organizations o ON o.id = u.organization_id "
        f"WHERE u.organization_id IS NOT NULL AND u.role IN ({roles}) AND o.id IS NULL"
    )).scalar() or 0
    # Same statement on Postgres and SQLite (3.24+): both support ON CONFLICT ... DO NOTHING.
    # The membership id is derived from the user and organization, so re-running inserts nothing new.
    result = conn.execute(sa.text(
        f"INSERT INTO memberships (id, user_id, organization_id, role, status, created_at, updated_at) "
        f"SELECT 'mem_' || u.id || '_' || u.organization_id, u.id, u.organization_id, u.role, "
        f"CASE WHEN u.is_active THEN 'active' ELSE 'suspended' END, "
        f"COALESCE(u.created_at, CURRENT_TIMESTAMP), CURRENT_TIMESTAMP "
        f"FROM users u JOIN organizations o ON o.id = u.organization_id "
        f"WHERE u.role IN ({roles}) "
        f"ON CONFLICT (user_id, organization_id) DO NOTHING"
    ))
    created = result.rowcount or 0
    log.info("memberships backfill: %s created, %s users skipped (organization missing)", created, skipped)
    return created


def downgrade() -> None:
    # users.organization_id / users.role were kept in sync as a mirror, so nothing is lost.
    with op.batch_alter_table('user_tokens') as batch_op:
        batch_op.drop_constraint(batch_op.f('fk_user_tokens_organization_id_organizations'), type_='foreignkey')
        batch_op.drop_column('organization_id')
    op.drop_index('uq_memberships_user_org', table_name='memberships')
    op.drop_index(op.f('ix_memberships_user_id'), table_name='memberships')
    op.drop_index('ix_memberships_org_status', table_name='memberships')
    op.drop_table('memberships')
    with op.batch_alter_table('organizations') as batch_op:
        batch_op.drop_constraint(op.f('ck_organizations_org_parent_matches_type'), type_='check')
        batch_op.drop_constraint(op.f('ck_organizations_org_type_valid'), type_='check')
        batch_op.drop_constraint(batch_op.f('fk_organizations_parent_id_organizations'), type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_organizations_parent_id'))
        batch_op.drop_column('allow_parent_access')
        batch_op.drop_column('parent_id')
        batch_op.drop_column('org_type')
