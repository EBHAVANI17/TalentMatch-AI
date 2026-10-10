"""row level security

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-07 18:00:00.000000

Schema (every database):
  - job_private: interview criteria, screening questions, urgency move out of jobs (org-only)
  - organization_id copied onto application_stage_history, interviews, interview_feedback,
    copilot_messages (+ user_id) and notifications (sending org); backfilled from parents
  - embeddings.is_public (searchable marketplace candidates), backfilled
  - events_dead_letter; composite indexes for RLS-filtered queries
  - view public_org_profiles (id, name, domain, industry, logo_icon, website)

PostgreSQL only (row-level security):
  Roles (created if missing; passwords are set by operations, never here):
    talentmatch_app     LOGIN, NOBYPASSRLS. Every API request.
    talentmatch_worker  LOGIN, NOBYPASSRLS. Outbox/background workers; one extra policy on
                        events_outbox / events_dead_letter so it can claim any org's events.
    talentmatch_admin   LOGIN, BYPASSRLS. Platform-admin requests, seed, maintenance.
  The migration role owns tables, the view and all functions, and must have BYPASSRLS (or be a
  superuser): SECURITY DEFINER helpers and the view read across tenants as the owner even though
  every tenant table has FORCE ROW LEVEL SECURITY.

  GRANTs: tenant tables SELECT/INSERT/UPDATE/DELETE to app+worker (policies decide rows); global
  tables SELECT only; audit_logs INSERT only; events_outbox INSERT (app) / full (worker);
  users, user_tokens, invitations get column-level grants that exclude secrets
  (hashed_password, token_hash) and, for users, the columns only platform admins may change.

  Context: policies read app.org_id / app.user_id via current_setting(name, true) wrapped in a
  scalar subquery (evaluated once per query). Unset or '' => no tenant rows (fail closed).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0012'
down_revision: Union[str, None] = '0011'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

APP, WORKER, ADMIN = "talentmatch_app", "talentmatch_worker", "talentmatch_admin"
ORG = "(SELECT NULLIF(current_setting('app.org_id', true), ''))"
USR = "(SELECT NULLIF(current_setting('app.user_id', true), ''))"
MYCAND = "(SELECT tm_my_candidate_id())"

GLOBAL_TABLES = ["plans", "prompt_templates", "skill_aliases", "skill_relations", "skill_taxonomies"]

# table -> [(policy name, command, USING, WITH CHECK)]
CAND_SELECT = "tm_candidate_visible(candidate_id)"
CAND_WRITE = "tm_candidate_writable(candidate_id)"
POLICIES = {
    "organizations": [
        ("org_select", "SELECT", f"id = {ORG} OR id = ANY (COALESCE((SELECT tm_my_org_ids()), '{{}}'::text[])) OR parent_id = {ORG}", None),
        ("org_insert", "INSERT", None,
         f"(id = {ORG} AND parent_id IS NULL AND org_type = 'standalone') OR (parent_id = {ORG} AND org_type = 'client')"),
        ("org_update", "UPDATE", f"id = {ORG}", f"id = {ORG}"),
    ],
    "users": [
        ("users_select", "SELECT", "tm_user_visible(id)", None),
        # Only candidate accounts can be inserted directly (sign-up, sourcing); staff accounts go
        # through tm_create_staff_user(); platform admins through the admin role.
        ("users_insert", "INSERT", None,
         f"role = 'CANDIDATE' AND organization_id IS NULL AND (id = {USR} OR {ORG} IS NOT NULL)"),
        ("users_update", "UPDATE", "tm_user_editable(id)", "tm_user_editable(id)"),
    ],
    "memberships": [
        ("mem_select", "SELECT",
         f"organization_id = {ORG} OR user_id = {USR} OR tm_is_client_of_current_org(organization_id)", None),
        ("mem_write", "ALL", f"organization_id = {ORG} OR tm_is_client_of_current_org(organization_id)",
         f"organization_id = {ORG} OR tm_is_client_of_current_org(organization_id)"),
    ],
    "user_tokens": [("tok_own", "ALL", f"user_id = {USR}", f"user_id = {USR}")],
    "invitations": [("inv_org", "ALL", f"organization_id = {ORG}", f"organization_id = {ORG}")],
    "jobs": [
        ("jobs_select", "SELECT",
         f"organization_id = {ORG} OR status = 'Active' OR id = ANY (COALESCE((SELECT tm_my_applied_job_ids()), '{{}}'::text[]))", None),
        ("jobs_insert", "INSERT", None, f"organization_id = {ORG}"),
        ("jobs_update", "UPDATE", f"organization_id = {ORG}", f"organization_id = {ORG}"),
        ("jobs_delete", "DELETE", f"organization_id = {ORG}", None),
    ],
    "job_private": [("jobp_org", "ALL", f"organization_id = {ORG}", f"organization_id = {ORG}")],
    "job_skills": [
        ("jskill_select", "SELECT", "tm_job_visible(job_id)", None),
        ("jskill_insert", "INSERT", None, "tm_job_in_current_org(job_id)"),
        ("jskill_update", "UPDATE", "tm_job_in_current_org(job_id)", "tm_job_in_current_org(job_id)"),
        ("jskill_delete", "DELETE", "tm_job_in_current_org(job_id)", None),
    ],
    "candidate_profiles": [
        ("cand_select", "SELECT",
         f"owner_org_id = {ORG} OR (owner_org_id IS NULL AND {ORG} IS NOT NULL AND (is_searchable OR id = ANY (COALESCE((SELECT tm_applied_candidate_ids()), '{{}}'::text[])))) "
         f"OR user_id = {USR}", None),
        ("cand_insert", "INSERT", None, f"owner_org_id = {ORG} OR (owner_org_id IS NULL AND user_id = {USR})"),
        ("cand_update", "UPDATE", f"owner_org_id = {ORG} OR user_id = {USR}", f"owner_org_id = {ORG} OR user_id = {USR}"),
        ("cand_delete", "DELETE", f"owner_org_id = {ORG}", None),
    ],
    "applications": [
        ("app_select", "SELECT", f"organization_id = {ORG} OR candidate_id = {MYCAND}", None),
        ("app_insert", "INSERT", None, f"organization_id = {ORG} OR candidate_id = {MYCAND}"),
        ("app_update", "UPDATE", f"organization_id = {ORG}", f"organization_id = {ORG}"),
        ("app_delete", "DELETE", f"organization_id = {ORG}", None),
    ],
    "application_stage_history": [
        ("ash_select", "SELECT", f"organization_id = {ORG} OR tm_application_mine(application_id)", None),
        ("ash_insert", "INSERT", None, f"organization_id = {ORG} OR tm_application_mine(application_id)"),
        ("ash_update", "UPDATE", f"organization_id = {ORG}", f"organization_id = {ORG}"),
        ("ash_delete", "DELETE", f"organization_id = {ORG}", None),
    ],
    "interviews": [
        ("int_select", "SELECT", f"organization_id = {ORG} OR tm_application_mine(application_id)", None),
        ("int_insert", "INSERT", None, f"organization_id = {ORG}"),
        ("int_update", "UPDATE", f"organization_id = {ORG}", f"organization_id = {ORG}"),
        ("int_delete", "DELETE", f"organization_id = {ORG}", None),
    ],
    "interview_feedback": [("ifb_org", "ALL", f"organization_id = {ORG}", f"organization_id = {ORG}")],
    "matches": [
        ("match_select", "SELECT", f"organization_id = {ORG} OR candidate_id = {MYCAND}", None),
        ("match_insert", "INSERT", None, f"organization_id = {ORG} OR candidate_id = {MYCAND}"),
        ("match_update", "UPDATE", f"organization_id = {ORG}", f"organization_id = {ORG}"),
        ("match_delete", "DELETE", f"organization_id = {ORG}", None),
    ],
    "candidate_notes": [("note_org", "ALL", f"organization_id = {ORG}", f"organization_id = {ORG}")],
    "pipeline_stages": [("stage_org", "ALL", f"organization_id = {ORG}", f"organization_id = {ORG}")],
    "copilot_conversations": [("conv_own", "ALL", f"organization_id = {ORG} AND user_id = {USR}",
                               f"organization_id = {ORG} AND user_id = {USR}")],
    "copilot_messages": [("cmsg_own", "ALL", f"organization_id = {ORG} AND user_id = {USR}",
                          f"organization_id = {ORG} AND user_id = {USR}")],
    "documents": [
        ("doc_select", "SELECT", f"organization_id = {ORG} OR (candidate_id IS NOT NULL AND {CAND_SELECT})", None),
        ("doc_write", "ALL", f"organization_id = {ORG} OR (organization_id IS NULL AND candidate_id IS NOT NULL AND {CAND_WRITE})",
         f"organization_id = {ORG} OR (organization_id IS NULL AND candidate_id IS NOT NULL AND {CAND_WRITE})"),
    ],
    "embeddings": [
        ("emb_select", "SELECT",
         f"organization_id = {ORG} OR (is_public AND {ORG} IS NOT NULL) OR (entity_type = 'job' AND ({ORG} IS NOT NULL OR {USR} IS NOT NULL) AND tm_job_is_active(entity_id)) "
         f"OR (entity_type = 'candidate' AND (entity_id = {MYCAND} OR entity_id = ANY (COALESCE((SELECT tm_applied_candidate_ids()), '{{}}'::text[]))))",
         None),
        ("emb_write", "ALL",
         f"organization_id = {ORG} OR (entity_type = 'candidate' AND organization_id IS NULL AND tm_candidate_writable(entity_id))",
         f"organization_id = {ORG} OR (entity_type = 'candidate' AND organization_id IS NULL AND tm_candidate_writable(entity_id))"),
    ],
    "notifications": [
        ("notif_own", "SELECT", f"user_id = {USR}", None),
        ("notif_update", "UPDATE", f"user_id = {USR}", f"user_id = {USR}"),
        ("notif_delete", "DELETE", f"user_id = {USR}", None),
        ("notif_insert", "INSERT", None, f"organization_id = {ORG} OR (organization_id IS NULL AND {ORG} IS NULL)"),
    ],
    # Parent admins acting on a client (memberships, client creation) audit under the client
    "audit_logs": [("audit_insert", "INSERT", None, f"organization_id = {ORG} OR (organization_id IS NULL AND {ORG} IS NULL) "
                                                     f"OR tm_is_client_of_current_org(organization_id) "
                                                     f"OR ({ORG} IS NULL AND organization_id = ANY (COALESCE((SELECT tm_my_application_org_ids()), '{{}}'::text[])))")],
    "events_outbox": [
        # A candidate (no organization) may raise events for organizations they have applied to
        ("evt_insert", "INSERT", None, f"organization_id = {ORG} OR (organization_id IS NULL AND {ORG} IS NULL) "
                                       f"OR ({ORG} IS NULL AND organization_id = ANY (COALESCE((SELECT tm_my_application_org_ids()), '{{}}'::text[])))"),
        ("evt_worker", "ALL", "true", "true", WORKER),
    ],
    "events_dead_letter": [("dlq_worker", "ALL", "true", "true", WORKER)],
    "ai_requests": [
        ("air_select", "SELECT", f"organization_id = {ORG}", None),
        ("air_insert", "INSERT", None, f"organization_id = {ORG} OR (organization_id IS NULL AND {ORG} IS NULL)"),
    ],
    "ai_usage_records": [
        ("aiu_select", "SELECT", f"organization_id = {ORG}", None),
        ("aiu_insert", "INSERT", None, f"organization_id = {ORG} OR (organization_id IS NULL AND {ORG} IS NULL)"),
    ],
    "resumes": [("res_select", "SELECT", CAND_SELECT, None), ("res_write", "ALL", CAND_WRITE, CAND_WRITE)],
    "resume_versions": [("rv_select", "SELECT", "tm_resume_visible(resume_id)", None),
                        ("rv_write", "ALL", "tm_resume_writable(resume_id)", "tm_resume_writable(resume_id)")],
    "resume_analyses": [("ra_select", "SELECT", "tm_resume_visible(resume_id)", None),
                        ("ra_write", "ALL", "tm_resume_writable(resume_id)", "tm_resume_writable(resume_id)")],
}
for _child in ("candidate_skills", "work_experiences", "education_records", "candidate_projects",
               "certifications", "candidate_languages"):
    POLICIES[_child] = [(f"{_child[:10]}_select", "SELECT", CAND_SELECT, None),
                        (f"{_child[:10]}_write", "ALL", CAND_WRITE, CAND_WRITE)]

TENANT_TABLES = sorted(POLICIES)

# Helper functions used by policies. SECURITY DEFINER (run as the owner, which bypasses RLS) so a
# policy never queries another RLS table directly: no recursion, one indexed lookup per call.
_O = "NULLIF(current_setting('app.org_id', true), '')"
_U = "NULLIF(current_setting('app.user_id', true), '')"
POLICY_HELPERS = {
    "tm_my_candidate_id()": ("text", f"SELECT id FROM candidate_profiles WHERE user_id = {_U} LIMIT 1"),
    "tm_my_org_ids()": ("text[]", f"SELECT COALESCE(array_agg(organization_id), '{{}}') FROM memberships "
                                  f"WHERE user_id = {_U} AND status = 'active'"),
    "tm_applied_candidate_ids()": ("text[]", f"SELECT COALESCE(array_agg(DISTINCT candidate_id), '{{}}') FROM applications "
                                             f"WHERE organization_id = {_O}"),
    "tm_my_applied_job_ids()": ("text[]", "SELECT COALESCE(array_agg(DISTINCT job_id), '{}') FROM applications "
                                          "WHERE candidate_id = tm_my_candidate_id()"),
    "tm_my_application_org_ids()": ("text[]", "SELECT COALESCE(array_agg(DISTINCT organization_id), '{}') FROM applications "
                                              "WHERE candidate_id = tm_my_candidate_id() AND organization_id IS NOT NULL"),
    "tm_candidate_applied_to_org(p_candidate text)": (
        "boolean", f"SELECT EXISTS (SELECT 1 FROM applications WHERE candidate_id = p_candidate AND organization_id = {_O})"),
    "tm_is_client_of_current_org(p_org text)": (
        "boolean", f"SELECT EXISTS (SELECT 1 FROM organizations WHERE id = p_org AND parent_id = {_O} "
                   f"AND allow_parent_access AND status <> 'deleted')"),
    "tm_candidate_visible(p_candidate text)": (
        "boolean", f"SELECT EXISTS (SELECT 1 FROM candidate_profiles cp WHERE cp.id = p_candidate AND ("
                   f"cp.owner_org_id = {_O} OR cp.user_id = {_U} OR (cp.owner_org_id IS NULL AND {_O} IS NOT NULL AND (cp.is_searchable OR "
                   f"EXISTS (SELECT 1 FROM applications a WHERE a.candidate_id = cp.id AND a.organization_id = {_O})))))"),
    "tm_candidate_writable(p_candidate text)": (
        "boolean", f"SELECT EXISTS (SELECT 1 FROM candidate_profiles cp WHERE cp.id = p_candidate "
                   f"AND (cp.owner_org_id = {_O} OR cp.user_id = {_U}))"),
    "tm_job_visible(p_job text)": (
        "boolean", f"SELECT EXISTS (SELECT 1 FROM jobs j WHERE j.id = p_job AND (j.organization_id = {_O} OR j.status = 'Active' "
                   f"OR EXISTS (SELECT 1 FROM applications a WHERE a.job_id = j.id AND a.candidate_id = tm_my_candidate_id())))"),
    "tm_job_in_current_org(p_job text)": (
        "boolean", f"SELECT EXISTS (SELECT 1 FROM jobs WHERE id = p_job AND organization_id = {_O})"),
    "tm_job_is_active(p_job text)": ("boolean", "SELECT EXISTS (SELECT 1 FROM jobs WHERE id = p_job AND status = 'Active')"),
    "tm_application_mine(p_application text)": (
        "boolean", "SELECT EXISTS (SELECT 1 FROM applications WHERE id = p_application AND candidate_id = tm_my_candidate_id())"),
    "tm_resume_visible(p_resume text)": (
        "boolean", "SELECT EXISTS (SELECT 1 FROM resumes r WHERE r.id = p_resume AND tm_candidate_visible(r.candidate_id))"),
    "tm_resume_writable(p_resume text)": (
        "boolean", "SELECT EXISTS (SELECT 1 FROM resumes r WHERE r.id = p_resume AND tm_candidate_writable(r.candidate_id))"),
    "tm_user_visible(p_user text)": (
        "boolean", f"SELECT p_user = {_U} "
                   f"OR EXISTS (SELECT 1 FROM memberships m WHERE m.user_id = p_user AND (m.organization_id = {_O} "
                   f"OR tm_is_client_of_current_org(m.organization_id))) "
                   f"OR EXISTS (SELECT 1 FROM candidate_profiles cp WHERE cp.user_id = p_user AND tm_candidate_visible(cp.id))"),
    "tm_user_editable(p_user text)": (
        "boolean", f"SELECT p_user = {_U} OR EXISTS (SELECT 1 FROM candidate_profiles cp WHERE cp.user_id = p_user "
                   f"AND cp.owner_org_id = {_O})"),
    "tm_org_matching_weights(p_org text)": ("text", "SELECT matching_weights_json FROM organizations WHERE id = p_org"),
}

# Functions the application calls directly (pre-sign-in lookups and narrowly-scoped writes).
APP_FUNCTIONS = {
    "auth_user_by_email(p_email text)": (
        "TABLE(id text, hashed_password text, is_active boolean, email_verified boolean)", "sql", "STABLE",
        "SELECT u.id::text, u.hashed_password::text, u.is_active, u.email_verified FROM users u WHERE u.email = p_email"),
    "auth_account_by_email(p_email text)": (
        "TABLE(id text, role text, is_active boolean)", "sql", "STABLE",
        "SELECT u.id::text, u.role::text, u.is_active FROM users u WHERE u.email = p_email"),
    # Signed download links: the app checks the HMAC signature first; this returns only file metadata
    "tm_document_for_signed_download(p_document text)": (
        "TABLE(storage_key text, content_type text, filename text)", "sql", "STABLE",
        "SELECT d.storage_key::text, d.content_type::text, d.filename::text FROM documents d WHERE d.id = p_document"),
    "auth_email_exists(p_email text)": ("boolean", "sql", "STABLE", "SELECT EXISTS (SELECT 1 FROM users WHERE email = p_email)"),
    "auth_domain_exists(p_domain text)": ("boolean", "sql", "STABLE",
                                          "SELECT EXISTS (SELECT 1 FROM organizations WHERE domain = p_domain)"),
    "auth_token_owner(p_hash text, p_purpose text)": (
        "TABLE(id text, user_id text, expires_at timestamp, used_at timestamp, organization_id text)", "sql", "STABLE",
        "SELECT t.id::text, t.user_id::text, t.expires_at, t.used_at, t.organization_id::text FROM user_tokens t "
        "WHERE t.token_hash = p_hash AND t.purpose = p_purpose"),
    "auth_invitation(p_hash text)": (
        "TABLE(id text, organization_id text, email text, role text, status text, expires_at timestamp)", "sql", "STABLE",
        "SELECT i.id::text, i.organization_id::text, i.email::text, i.role::text, i.status::text, i.expires_at "
        "FROM invitations i WHERE i.token_hash = p_hash"),
    "tm_set_password_hash(p_user text, p_hash text)": ("void", "plpgsql", "VOLATILE", f"""
BEGIN
  IF p_user IS NULL OR p_user IS DISTINCT FROM {_U} THEN
    RAISE EXCEPTION 'tm_set_password_hash: may only change the current user''s password' USING ERRCODE = '42501';
  END IF;
  UPDATE users SET hashed_password = p_hash, updated_at = now() AT TIME ZONE 'utc' WHERE id = p_user;
END"""),
    "tm_create_staff_user(p_id text, p_email text, p_hash text, p_full_name text, p_role text, p_org text, "
    "p_email_verified boolean, p_avatar text)": ("void", "plpgsql", "VOLATILE", f"""
BEGIN
  IF p_role NOT IN ('ORG_ADMIN', 'EMPLOYER_ADMIN', 'RECRUITER', 'HIRING_MANAGER', 'INTERVIEWER', 'ANALYST') THEN
    RAISE EXCEPTION 'tm_create_staff_user: % is not an organization role', p_role USING ERRCODE = '42501';
  END IF;
  IF p_org IS NULL OR p_org IS DISTINCT FROM {_O} THEN
    RAISE EXCEPTION 'tm_create_staff_user: organization must be the current organization' USING ERRCODE = '42501';
  END IF;
  INSERT INTO users (id, email, hashed_password, full_name, role, organization_id, avatar_url, status, is_active,
                     email_verified, created_at, updated_at)
  VALUES (p_id, p_email, p_hash, p_full_name, p_role, p_org, COALESCE(p_avatar, ''), 'Active', true,
          p_email_verified, now() AT TIME ZONE 'utc', now() AT TIME ZONE 'utc');
END"""),
    "tm_sync_default_org(p_user text)": ("void", "plpgsql", "VOLATILE", f"""
DECLARE
  v_role text; v_current text; v_org text; v_member_role text;
BEGIN
  SELECT role, organization_id INTO v_role, v_current FROM users WHERE id = p_user;
  IF NOT FOUND OR v_role IN ('SUPER_ADMIN', 'CANDIDATE') THEN RETURN; END IF;
  IF NOT (p_user = {_U} OR v_current = {_O} OR tm_is_client_of_current_org(v_current) OR EXISTS (
      SELECT 1 FROM memberships m WHERE m.user_id = p_user
      AND (m.organization_id = {_O} OR tm_is_client_of_current_org(m.organization_id)))) THEN
    RAISE EXCEPTION 'tm_sync_default_org: not allowed for this user' USING ERRCODE = '42501';
  END IF;
  SELECT m.organization_id, m.role INTO v_org, v_member_role FROM memberships m JOIN organizations o ON o.id = m.organization_id
   WHERE m.user_id = p_user AND m.status = 'active' AND o.status <> 'deleted'
   ORDER BY (m.organization_id = v_current) DESC, m.created_at, m.id LIMIT 1;
  IF v_org IS NULL THEN
    UPDATE users SET organization_id = NULL WHERE id = p_user;
  ELSE
    UPDATE users SET organization_id = v_org, role = v_member_role WHERE id = p_user;
  END IF;
END"""),
    "tm_revoke_org_sessions(p_user text, p_org text)": ("void", "plpgsql", "VOLATILE", f"""
BEGIN
  IF NOT (p_user = {_U} OR p_org = {_O} OR tm_is_client_of_current_org(p_org)) THEN
    RAISE EXCEPTION 'tm_revoke_org_sessions: not allowed for this organization' USING ERRCODE = '42501';
  END IF;
  UPDATE user_tokens SET used_at = now() AT TIME ZONE 'utc'
   WHERE user_id = p_user AND purpose = 'refresh' AND organization_id = p_org AND used_at IS NULL;
END"""),
    "tm_refresh_applicants_count(p_job text)": ("void", "plpgsql", "VOLATILE", """
BEGIN
  -- Only recomputes a count; callable by anyone who can see the job (e.g. a candidate who just applied)
  IF NOT tm_job_visible(p_job) THEN
    RAISE EXCEPTION 'tm_refresh_applicants_count: job not visible' USING ERRCODE = '42501';
  END IF;
  UPDATE jobs SET applicants_count = (SELECT COUNT(*) FROM applications WHERE job_id = p_job) WHERE id = p_job;
END"""),
    "tm_notification_exists(p_event text, p_user text)": ("boolean", "sql", "STABLE",
        "SELECT EXISTS (SELECT 1 FROM notifications WHERE event_id = p_event AND user_id = p_user)"),
    "tm_user_ai_usage_today(p_user text)": ("integer", "plpgsql", "STABLE", f"""
BEGIN
  IF p_user IS DISTINCT FROM {_U} THEN
    RAISE EXCEPTION 'tm_user_ai_usage_today: only for the current user' USING ERRCODE = '42501';
  END IF;
  RETURN (SELECT COUNT(*)::integer FROM ai_requests WHERE user_id = p_user AND status = 'success'
          AND created_at >= date_trunc('day', now() AT TIME ZONE 'utc'));
END"""),
}


def _is_pg() -> bool:
    return op.get_bind().dialect.name == "postgresql"


# ---------------------------------------------------------------------------
def upgrade() -> None:
    _schema_upgrade()
    if _is_pg():
        _rls_upgrade()


def _schema_upgrade() -> None:
    op.create_table('job_private',
        sa.Column('job_id', sa.String(length=64), nullable=False),
        sa.Column('organization_id', sa.String(length=64), nullable=False),
        sa.Column('urgency', sa.String(length=32), nullable=True),
        sa.Column('screening_questions_json', sa.Text(), nullable=True),
        sa.Column('interview_criteria_json', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['job_id'], ['jobs.id'], name=op.f('fk_job_private_job_id_jobs'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'],
                                name=op.f('fk_job_private_organization_id_organizations'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('job_id', name=op.f('pk_job_private')),
    )
    op.create_index(op.f('ix_job_private_organization_id'), 'job_private', ['organization_id'], unique=False)
    op.execute("INSERT INTO job_private (job_id, organization_id, urgency, screening_questions_json, interview_criteria_json) "
               "SELECT id, organization_id, urgency, screening_questions_json, interview_criteria_json FROM jobs")
    with op.batch_alter_table('jobs') as batch_op:
        batch_op.drop_column('urgency')
        batch_op.drop_column('screening_questions_json')
        batch_op.drop_column('interview_criteria_json')

    for table in ('application_stage_history', 'interviews', 'interview_feedback', 'copilot_messages', 'notifications'):
        with op.batch_alter_table(table) as batch_op:
            batch_op.add_column(sa.Column('organization_id', sa.String(length=64), nullable=True))
            batch_op.create_index(batch_op.f(f'ix_{table}_organization_id'), ['organization_id'], unique=False)
            batch_op.create_foreign_key(batch_op.f(f'fk_{table}_organization_id_organizations'), 'organizations',
                                        ['organization_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('copilot_messages') as batch_op:
        batch_op.add_column(sa.Column('user_id', sa.String(length=64), nullable=True))
        batch_op.create_index(batch_op.f('ix_copilot_messages_user_id'), ['user_id'], unique=False)
        batch_op.create_foreign_key(batch_op.f('fk_copilot_messages_user_id_users'), 'users', ['user_id'], ['id'],
                                    ondelete='CASCADE')
    op.execute("UPDATE application_stage_history SET organization_id = "
               "(SELECT a.organization_id FROM applications a WHERE a.id = application_stage_history.application_id)")
    op.execute("UPDATE interviews SET organization_id = "
               "(SELECT a.organization_id FROM applications a WHERE a.id = interviews.application_id)")
    op.execute("UPDATE interview_feedback SET organization_id = "
               "(SELECT i.organization_id FROM interviews i WHERE i.id = interview_feedback.interview_id)")
    op.execute("UPDATE copilot_messages SET "
               "organization_id = (SELECT c.organization_id FROM copilot_conversations c WHERE c.id = copilot_messages.conversation_id), "
               "user_id = (SELECT c.user_id FROM copilot_conversations c WHERE c.id = copilot_messages.conversation_id)")

    with op.batch_alter_table('embeddings') as batch_op:
        batch_op.add_column(sa.Column('is_public', sa.Boolean(), server_default=sa.false(), nullable=False))
    op.execute("UPDATE embeddings SET is_public = TRUE WHERE entity_type = 'candidate' AND entity_id IN "
               "(SELECT id FROM candidate_profiles WHERE owner_org_id IS NULL AND is_searchable)")

    op.create_table('events_dead_letter',
        sa.Column('id', sa.String(length=64), nullable=False),
        sa.Column('event_id', sa.String(length=64), nullable=False),
        sa.Column('type', sa.String(length=64), nullable=False),
        sa.Column('organization_id', sa.String(length=64), nullable=True),
        sa.Column('payload_json', sa.Text(), nullable=False),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_events_dead_letter')),
    )
    op.create_index(op.f('ix_events_dead_letter_created_at'), 'events_dead_letter', ['created_at'], unique=False)
    op.create_index(op.f('ix_events_dead_letter_event_id'), 'events_dead_letter', ['event_id'], unique=False)
    op.create_index(op.f('ix_events_dead_letter_organization_id'), 'events_dead_letter', ['organization_id'], unique=False)

    # Composite indexes that start with the RLS column
    op.create_index('ix_applications_candidate_org', 'applications', ['candidate_id', 'organization_id'], unique=False)
    op.create_index('ix_matches_org_job_score', 'matches', ['organization_id', 'job_id', 'score'], unique=False)
    op.create_index('ix_copilot_messages_org_conv', 'copilot_messages', ['organization_id', 'conversation_id', 'created_at'],
                    unique=False)

    op.execute("CREATE VIEW public_org_profiles AS SELECT id, name, domain, industry, logo_icon, website "
               "FROM organizations WHERE is_active AND status <> 'deleted'")


def _create_function(signature: str, returns: str, language: str, volatility: str, body: str) -> None:
    op.execute(
        f"CREATE OR REPLACE FUNCTION {signature} RETURNS {returns} LANGUAGE {language} {volatility} "
        f"SECURITY DEFINER SET search_path = pg_catalog, public AS $fn${body}$fn$"
    )
    op.execute(f"REVOKE ALL ON FUNCTION {signature} FROM PUBLIC")


def _rls_upgrade() -> None:
    # Roles (cluster-wide; created once). Passwords: ALTER ROLE ... PASSWORD by operations.
    for role, attrs in ((APP, "LOGIN NOBYPASSRLS"), (WORKER, "LOGIN NOBYPASSRLS"), (ADMIN, "LOGIN BYPASSRLS")):
        op.execute(f"""DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN
                CREATE ROLE {role} {attrs} NOSUPERUSER NOCREATEDB NOCREATEROLE;
            END IF; END $$""")
    op.execute(f"DO $$ BEGIN EXECUTE format('GRANT CONNECT ON DATABASE %I TO {APP}, {WORKER}, {ADMIN}', current_database()); END $$")
    op.execute(f"GRANT USAGE ON SCHEMA public TO {APP}, {WORKER}, {ADMIN}")

    # Table privileges
    special = {"users", "user_tokens", "invitations", "audit_logs", "events_outbox", "events_dead_letter",
               "ai_requests", "ai_usage_records"}
    for table in TENANT_TABLES:
        if table not in special:
            op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO {APP}, {WORKER}")
        op.execute(f"GRANT ALL ON {table} TO {ADMIN}")
    for table in GLOBAL_TABLES:
        op.execute(f"GRANT SELECT ON {table} TO {APP}, {WORKER}")
        op.execute(f"GRANT ALL ON {table} TO {ADMIN}")
    op.execute(f"GRANT SELECT ON public_org_profiles TO {APP}, {WORKER}, {ADMIN}")
    op.execute(f"GRANT INSERT ON audit_logs TO {APP}, {WORKER}")
    op.execute(f"GRANT INSERT ON events_outbox TO {APP}")
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON events_outbox TO {WORKER}")
    op.execute(f"GRANT SELECT, INSERT ON events_dead_letter TO {WORKER}")
    op.execute(f"GRANT SELECT, INSERT ON ai_requests, ai_usage_records TO {APP}, {WORKER}")
    # Column-level grants: secrets are never readable or updatable by the request/worker roles
    _column_grants("users", select_except={"hashed_password"},
                   update_except={"id", "hashed_password", "role", "organization_id", "is_active", "status"})
    _column_grants("user_tokens", select_except={"token_hash"}, update_only={"used_at"}, delete=True)
    _column_grants("invitations", select_except={"token_hash"}, update_only={"status", "accepted_at"}, delete=False)
    # talentmatch_admin keeps table-level access (a column REVOKE can't narrow a table-level GRANT);
    # the ORM never loads hashed_password (deferred) on any role.

    # Functions (owned by this migration's role)
    for signature, (returns, body) in POLICY_HELPERS.items():
        _create_function(signature, returns, "sql", "STABLE", body)
        op.execute(f"GRANT EXECUTE ON FUNCTION {signature} TO {APP}, {WORKER}")
    for signature, (returns, language, volatility, body) in APP_FUNCTIONS.items():
        _create_function(signature, returns, language, volatility, body)
        op.execute(f"GRANT EXECUTE ON FUNCTION {signature} TO {APP}, {WORKER}, {ADMIN}")

    # Policies
    for table, policies in POLICIES.items():
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        for policy in policies:
            name, command, using, check = policy[:4]
            role = policy[4] if len(policy) > 4 else "PUBLIC"
            sql = f"CREATE POLICY {name} ON {table} FOR {command} TO {role}"
            if using:
                sql += f" USING ({using})"
            if check:
                sql += f" WITH CHECK ({check})"
            op.execute(sql)


def _column_grants(table: str, *, select_except=(), update_except=None, update_only=None, delete=False) -> None:
    roles = f"{APP}, {WORKER}"
    cols = [r[0] for r in op.get_bind().execute(sa.text(
        "SELECT column_name FROM information_schema.columns WHERE table_schema = 'public' AND table_name = :t "
        "ORDER BY ordinal_position"), {"t": table})]
    select_cols = [c for c in cols if c not in set(select_except)]
    op.execute(f"GRANT SELECT ({', '.join(select_cols)}) ON {table} TO {roles}")
    op.execute(f"GRANT INSERT ON {table} TO {roles}")
    if update_only is not None:
        update_cols = [c for c in cols if c in set(update_only)]
    else:
        update_cols = [c for c in cols if c not in set(update_except or ())]
    op.execute(f"GRANT UPDATE ({', '.join(update_cols)}) ON {table} TO {roles}")
    if delete:
        op.execute(f"GRANT DELETE ON {table} TO {roles}")


# ---------------------------------------------------------------------------
def downgrade() -> None:
    if _is_pg():
        for table, policies in POLICIES.items():
            for policy in policies:
                op.execute(f"DROP POLICY IF EXISTS {policy[0]} ON {table}")
            op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
            op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
        for signature in list(APP_FUNCTIONS) + list(reversed(list(POLICY_HELPERS))):
            op.execute(f"DROP FUNCTION IF EXISTS {signature.split('(')[0]}({_arg_types(signature)})")
        for role in (APP, WORKER, ADMIN):
            op.execute(f"REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {role}")
            op.execute(f"REVOKE ALL ON SCHEMA public FROM {role}")
        # Roles are cluster-wide and may serve other databases: they are kept.

    op.execute("DROP VIEW IF EXISTS public_org_profiles")
    op.drop_index('ix_copilot_messages_org_conv', table_name='copilot_messages')
    op.drop_index('ix_matches_org_job_score', table_name='matches')
    op.drop_index('ix_applications_candidate_org', table_name='applications')
    op.drop_index(op.f('ix_events_dead_letter_organization_id'), table_name='events_dead_letter')
    op.drop_index(op.f('ix_events_dead_letter_event_id'), table_name='events_dead_letter')
    op.drop_index(op.f('ix_events_dead_letter_created_at'), table_name='events_dead_letter')
    op.drop_table('events_dead_letter')
    with op.batch_alter_table('embeddings') as batch_op:
        batch_op.drop_column('is_public')
    with op.batch_alter_table('copilot_messages') as batch_op:
        batch_op.drop_constraint(batch_op.f('fk_copilot_messages_user_id_users'), type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_copilot_messages_user_id'))
        batch_op.drop_column('user_id')
    for table in ('notifications', 'copilot_messages', 'interview_feedback', 'interviews', 'application_stage_history'):
        with op.batch_alter_table(table) as batch_op:
            batch_op.drop_constraint(batch_op.f(f'fk_{table}_organization_id_organizations'), type_='foreignkey')
            batch_op.drop_index(batch_op.f(f'ix_{table}_organization_id'))
            batch_op.drop_column('organization_id')
    with op.batch_alter_table('jobs') as batch_op:
        batch_op.add_column(sa.Column('urgency', sa.String(length=32), nullable=True))
        batch_op.add_column(sa.Column('screening_questions_json', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('interview_criteria_json', sa.Text(), nullable=True))
    op.execute("UPDATE jobs SET "
               "urgency = (SELECT p.urgency FROM job_private p WHERE p.job_id = jobs.id), "
               "screening_questions_json = (SELECT p.screening_questions_json FROM job_private p WHERE p.job_id = jobs.id), "
               "interview_criteria_json = (SELECT p.interview_criteria_json FROM job_private p WHERE p.job_id = jobs.id)")
    op.drop_index(op.f('ix_job_private_organization_id'), table_name='job_private')
    op.drop_table('job_private')


def _arg_types(signature: str) -> str:
    args = signature.split("(", 1)[1].rstrip(")")
    return ", ".join(part.strip().split(" ", 1)[1] for part in args.split(",") if part.strip())
