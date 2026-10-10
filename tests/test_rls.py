"""Step 2: PostgreSQL row-level security, proven with raw SQL as the database roles themselves.

Postgres only (SQLite has no RLS; these tests skip there). Run with TEST_DATABASE_URL set.
Two fresh organizations (A, B) get a row in every tenant table; then, connected as
talentmatch_app with only app.org_id / app.user_id set, plain `SELECT * FROM table` (no WHERE)
must never return the other tenant's rows, and inserts for the other tenant must be rejected.
"""
import uuid
from datetime import datetime, timedelta

import pytest
from sqlalchemy import Boolean, DateTime, Float, Integer, create_engine, text
from sqlalchemy.exc import DBAPIError

from app.core.config import settings
from app.core.database import Base, SessionLocal, admin_engine, engine, owner_engine, set_tenant, worker_engine
import app.models.db_models  # noqa: F401

pytestmark = pytest.mark.skipif(engine.dialect.name != "postgresql", reason="row-level security is PostgreSQL-only")

GLOBAL_TABLES = {"plans", "prompt_templates", "skill_aliases", "skill_relations", "skill_taxonomies"}
NO_APP_SELECT = {"audit_logs", "events_outbox", "events_dead_letter"}  # app role may insert, never read
PUBLIC_WITHOUT_ORG = {"jobs", "job_skills"}  # the public job board (Active jobs only)
TABLES = {t.name: t for t in Base.metadata.sorted_tables if not t.info.get("is_view")}
TENANT_TABLES = sorted(set(TABLES) - GLOBAL_TABLES)


def _short() -> str:
    return uuid.uuid4().hex[:8]


def _filler(column):
    """A valid value for a NOT NULL column with no explicit value (overrides set the meaningful ones)."""
    if column.name == "vector":
        return [0.01] * settings.embedding_dim
    t = column.type
    if isinstance(t, Boolean):
        return False
    if isinstance(t, Integer):
        return 0
    if isinstance(t, Float):
        return 0.0
    if isinstance(t, DateTime):
        return datetime.utcnow() + timedelta(days=1)
    return f"v{_short()}"


def insert_row(conn, table: str, **values) -> str:
    """Insert into any table, filling required columns; returns the primary key."""
    tbl = TABLES[table]
    row = dict(values)
    for col in tbl.columns:
        if col.name in row:
            continue
        if col.primary_key or not col.nullable:
            row[col.name] = _filler(col)
    conn.execute(tbl.insert().values(**row))
    pk = [c.name for c in tbl.primary_key.columns][0]
    return row[pk]


def _pk(table: str) -> str:
    return [c.name for c in TABLES[table].primary_key.columns][0]


def build_tenant(conn, org_id: str, skill_id: str) -> dict:
    """One organization with a row in every tenant table. Returns {table: {pk, ...}} plus handy ids."""
    ids: dict = {t: set() for t in TENANT_TABLES}
    add = lambda table, **v: ids[table].add(insert_row(conn, table, **v)) or list(ids[table])[-1]  # noqa: E731

    def put(table, **v):
        pk = insert_row(conn, table, **v)
        ids[table].add(pk)
        return pk

    put("organizations", id=org_id, name=f"RLS {org_id}", domain=f"{org_id}.rls.example.com", org_type="standalone",
        status="Active", is_active=True, parent_id=None, allow_parent_access=False)
    staff = put("users", id=f"u_{org_id}", email=f"staff.{org_id}@rls.example.com", role="RECRUITER",
                organization_id=org_id, is_active=True, status="Active")
    put("memberships", id=f"m_{org_id}", user_id=staff, organization_id=org_id, role="ORG_ADMIN", status="active")
    cand_user = put("users", id=f"cu_{org_id}", email=f"cand.{org_id}@rls.example.com", role="CANDIDATE",
                    organization_id=None, is_active=True)
    cand = put("candidate_profiles", id=f"c_{org_id}", user_id=cand_user, owner_org_id=org_id, title="Engineer",
               is_searchable=False)
    for child in ("candidate_skills", "work_experiences", "education_records", "candidate_projects",
                  "certifications", "candidate_languages"):
        extra = {"skill_id": skill_id} if child == "candidate_skills" else {}
        put(child, candidate_id=cand, **extra)
    doc = put("documents", organization_id=org_id, candidate_id=cand, uploaded_by_user_id=staff)
    resume = put("resumes", candidate_id=cand, document_id=doc)
    put("resume_versions", resume_id=resume)
    job = put("jobs", id=f"j_{org_id}", organization_id=org_id, title="Internal role", status="Draft")
    put("job_private", job_id=job, organization_id=org_id)
    put("job_skills", job_id=job, skill_id=skill_id)
    put("resume_analyses", resume_id=resume, target_job_id=job)
    app_id = put("applications", job_id=job, candidate_id=cand, organization_id=org_id, stage="Applied")
    put("application_stage_history", application_id=app_id, organization_id=org_id)
    interview = put("interviews", application_id=app_id, organization_id=org_id)
    put("interview_feedback", interview_id=interview, organization_id=org_id, interviewer_id=staff)
    put("matches", organization_id=org_id, job_id=job, candidate_id=cand, score=50, status="new")
    put("candidate_notes", organization_id=org_id, candidate_id=cand, author_user_id=staff, application_id=None)
    put("pipeline_stages", organization_id=org_id, name=f"Stage {org_id}")
    put("invitations", organization_id=org_id, email=f"inv.{org_id}@rls.example.com", status="pending",
        invited_by_user_id=staff)
    conv = put("copilot_conversations", organization_id=org_id, user_id=staff)
    put("copilot_messages", conversation_id=conv, organization_id=org_id, user_id=staff, role="user")
    put("notifications", user_id=staff, organization_id=org_id)
    put("audit_logs", organization_id=org_id, user_id=staff)
    put("events_outbox", organization_id=org_id)
    put("events_dead_letter", organization_id=org_id)
    put("ai_requests", organization_id=org_id, user_id=staff)
    put("ai_usage_records", organization_id=org_id, user_id=staff)
    put("user_tokens", user_id=staff, organization_id=org_id, purpose="refresh")
    put("embeddings", entity_type="candidate", entity_id=cand, organization_id=org_id, is_public=False)
    missing = [t for t in TENANT_TABLES if not ids[t]]
    assert not missing, f"build_tenant must create a row in every tenant table; missing: {missing}"
    return {"ids": ids, "staff": staff, "candidate": cand, "candidate_user": cand_user, "job": job, "app": app_id}


@pytest.fixture(scope="module")
def tenants():
    a, b = f"orga{_short()}", f"orgb{_short()}"
    with admin_engine.begin() as conn:
        skill_id = conn.execute(text("SELECT id FROM skill_taxonomies LIMIT 1")).scalar()
        return {"A": (a, build_tenant(conn, a, skill_id)), "B": (b, build_tenant(conn, b, skill_id))}


def app_conn(org_id=None, user_id=None, eng=None):
    """A connection as talentmatch_app (or another role) with the given transaction-local context."""
    conn = (eng or engine).connect()
    conn.execute(text("SELECT set_config('app.org_id', :o, true), set_config('app.user_id', :u, true)"),
                 {"o": org_id or "", "u": user_id or ""})
    return conn


def _visible_pks(conn, table: str) -> set:
    return {r[0] for r in conn.execute(text(f"SELECT {_pk(table)} FROM {table}"))}  # no WHERE on purpose


def _is_rls_denial(exc: DBAPIError) -> bool:
    return getattr(exc.orig, "sqlstate", None) == "42501"


# ---------------------------------------------------------------- roles, coverage, functions

def test_request_role_cannot_bypass_rls_and_admin_role_can():
    with engine.connect() as conn:
        assert conn.execute(text("SELECT current_user")).scalar() == "talentmatch_app"
        assert conn.execute(text("SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = current_user")).scalar() is False
    with worker_engine.connect() as conn:
        assert conn.execute(text("SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = current_user")).scalar() is False
    with admin_engine.connect() as conn:
        assert conn.execute(text("SELECT rolbypassrls FROM pg_roles WHERE rolname = current_user")).scalar() is True


def test_every_table_is_rls_forced_or_explicitly_global():
    with owner_engine.connect() as conn:
        flags = {r[0]: (r[1], r[2]) for r in conn.execute(text(
            "SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class "
            "WHERE relnamespace = 'public'::regnamespace AND relkind = 'r'"))}
    problems = []
    for name in TABLES:
        enabled, forced = flags.get(name, (False, False))
        if name in GLOBAL_TABLES:
            continue
        if not (enabled and forced):
            problems.append(name)
    assert not problems, f"Tables neither RLS-enabled+forced nor on the global allowlist: {problems}"


def test_security_definer_functions_are_locked_down():
    with owner_engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT p.proname, p.proconfig, pg_get_userbyid(p.proowner), "
            "has_function_privilege('public', p.oid, 'EXECUTE') "
            "FROM pg_proc p WHERE p.pronamespace = 'public'::regnamespace AND p.prosecdef")).all()
        owner = conn.execute(text("SELECT current_user")).scalar()
    assert len(rows) >= 25
    for name, config, fn_owner, public_exec in rows:
        assert config and "search_path=pg_catalog, public" in config, name
        assert public_exec is False, f"{name} is executable by PUBLIC"
        assert fn_owner == owner, name


# ---------------------------------------------------------------- fail closed

def test_no_context_means_no_tenant_rows(tenants):
    with app_conn() as conn:
        for table in TENANT_TABLES:
            if table in NO_APP_SELECT:
                continue
            if table in PUBLIC_WITHOUT_ORG:
                if table == "jobs":
                    statuses = {r[0] for r in conn.execute(text("SELECT DISTINCT status FROM jobs"))}
                    assert statuses <= {"Active"}, statuses
                else:
                    hidden = conn.execute(text("SELECT COUNT(*) FROM job_skills js WHERE NOT EXISTS "
                                               "(SELECT 1 FROM jobs j WHERE j.id = js.job_id AND j.status = 'Active')")).scalar()
                    assert hidden == 0
                continue
            assert conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar() == 0, table


def test_empty_string_context_is_also_closed(tenants):
    with engine.connect() as conn:  # set, then cleared: current_setting returns '' rather than NULL
        conn.execute(text("SELECT set_config('app.org_id', 'x', true)"))
        conn.execute(text("SELECT set_config('app.org_id', '', true)"))
        assert conn.execute(text("SELECT COUNT(*) FROM candidate_notes")).scalar() == 0


# ---------------------------------------------------------------- isolation on every table

def test_org_a_cannot_see_any_org_b_row_on_any_table(tenants):
    (a, ta), (b, tb) = tenants["A"], tenants["B"]
    with app_conn(a, ta["staff"]) as conn:
        for table in TENANT_TABLES:
            if table in NO_APP_SELECT:
                with pytest.raises(DBAPIError) as exc:
                    conn.execute(text(f"SELECT 1 FROM {table} LIMIT 1"))
                assert "permission denied" in str(exc.value)
                conn.rollback()
                conn.execute(text("SELECT set_config('app.org_id', :o, true), set_config('app.user_id', :u, true)"),
                             {"o": a, "u": ta["staff"]})
                continue
            leaked = _visible_pks(conn, table) & tb["ids"][table]
            assert not leaked, f"{table}: org A sees org B rows {leaked}"


def test_each_org_sees_its_own_rows(tenants):
    """Positive control, so the isolation test can't pass by hiding everything."""
    for name in ("A", "B"):
        org, t = tenants[name]
        with app_conn(org, t["staff"]) as conn:
            for table in TENANT_TABLES:
                if table in NO_APP_SELECT:
                    continue
                if table == "users":
                    assert t["staff"] in _visible_pks(conn, table)
                    continue
                missing = t["ids"][table] - _visible_pks(conn, table)
                assert not missing, f"{table}: org {name} can't see its own rows {missing}"


def test_worker_can_claim_any_orgs_events_but_nothing_else(tenants):
    (a, ta), (b, tb) = tenants["A"], tenants["B"]
    with app_conn(eng=worker_engine) as conn:
        outbox = _visible_pks(conn, "events_outbox")
        assert ta["ids"]["events_outbox"] <= outbox and tb["ids"]["events_outbox"] <= outbox
        assert conn.execute(text("SELECT COUNT(*) FROM candidate_notes")).scalar() == 0


# ---------------------------------------------------------------- WITH CHECK

INSERT_FOR_OTHER_ORG = {
    "jobs": lambda b, t: dict(organization_id=b, title="x", status="Draft"),
    "job_private": lambda b, t: dict(job_id=t["job"], organization_id=b),
    "applications": lambda b, t: dict(job_id=t["job"], candidate_id=t["candidate"], organization_id=b),
    "application_stage_history": lambda b, t: dict(application_id=t["app"], organization_id=b),
    "interviews": lambda b, t: dict(application_id=t["app"], organization_id=b),
    "matches": lambda b, t: dict(organization_id=b, job_id=t["job"], candidate_id=t["candidate"], score=1),
    "candidate_notes": lambda b, t: dict(organization_id=b, candidate_id=t["candidate"]),
    "pipeline_stages": lambda b, t: dict(organization_id=b, name=f"s{_short()}"),
    "memberships": lambda b, t: dict(user_id=t["staff"], organization_id=b, role="ORG_ADMIN", status="active"),
    "invitations": lambda b, t: dict(organization_id=b, email=f"{_short()}@x.com", status="pending"),
    "copilot_conversations": lambda b, t: dict(organization_id=b, user_id=t["staff"]),
    "documents": lambda b, t: dict(organization_id=b),
    "embeddings": lambda b, t: dict(entity_type="job", entity_id=t["job"], organization_id=b),
    "notifications": lambda b, t: dict(user_id=t["staff"], organization_id=b),
    "audit_logs": lambda b, t: dict(organization_id=b),
    "events_outbox": lambda b, t: dict(organization_id=b),
    "ai_requests": lambda b, t: dict(organization_id=b),
    "ai_usage_records": lambda b, t: dict(organization_id=b),
    "candidate_profiles": lambda b, t: dict(user_id=t["candidate_user"], owner_org_id=b, title="x"),
    "candidate_skills": lambda b, t: dict(candidate_id=t["candidate"]),
    "resumes": lambda b, t: dict(candidate_id=t["candidate"]),
    "user_tokens": lambda b, t: dict(user_id=t["staff"], purpose="refresh"),
}


@pytest.mark.parametrize("table", sorted(INSERT_FOR_OTHER_ORG))
def test_inserting_a_row_for_another_org_is_rejected(tenants, table):
    (a, ta), (b, tb) = tenants["A"], tenants["B"]
    values = INSERT_FOR_OTHER_ORG[table](b, tb)
    if table == "candidate_skills":
        with admin_engine.connect() as c:
            values["skill_id"] = c.execute(text("SELECT id FROM skill_taxonomies LIMIT 1")).scalar()
    with app_conn(a, ta["staff"]) as conn:
        with pytest.raises(DBAPIError) as exc:
            insert_row(conn, table, **values)
        assert _is_rls_denial(exc.value), str(exc.value)[:300]


@pytest.mark.parametrize("role", ["SUPER_ADMIN", "ORG_ADMIN", "RECRUITER"])
def test_org_members_cannot_insert_staff_or_admin_accounts(tenants, role):
    a, ta = tenants["A"]
    with app_conn(a, ta["staff"]) as conn:
        with pytest.raises(DBAPIError) as exc:
            insert_row(conn, "users", email=f"{_short()}@x.com", role=role, organization_id=None)
        assert _is_rls_denial(exc.value)
    with app_conn(a, ta["staff"]) as conn:  # but sourcing a candidate account is allowed
        insert_row(conn, "users", email=f"{_short()}@x.com", role="CANDIDATE", organization_id=None)
        conn.rollback()


# ---------------------------------------------------------------- secrets

def test_password_hashes_and_token_hashes_are_not_readable(tenants):
    a, ta = tenants["A"]
    for sql in ("SELECT hashed_password FROM users", "SELECT token_hash FROM user_tokens",
                "SELECT token_hash FROM invitations"):
        with app_conn(a, ta["staff"]) as conn:
            with pytest.raises(DBAPIError) as exc:
                conn.execute(text(sql))
            assert "permission denied" in str(exc.value)
    with app_conn(a, ta["staff"]) as conn:
        with pytest.raises(DBAPIError):
            conn.execute(text("UPDATE users SET hashed_password = 'x' WHERE id = :u"), {"u": ta["staff"]})
    with app_conn(a, ta["staff"]) as conn:  # the helper only changes the current user's own hash
        with pytest.raises(DBAPIError) as exc:
            conn.execute(text("SELECT tm_set_password_hash(:u, 'x')"), {"u": tenants["B"][1]["staff"]})
        assert "current user" in str(exc.value)


def test_users_cannot_raise_their_own_role(tenants):
    a, ta = tenants["A"]
    with app_conn(a, ta["staff"]) as conn:
        with pytest.raises(DBAPIError) as exc:
            conn.execute(text("UPDATE users SET role = 'SUPER_ADMIN' WHERE id = :u"), {"u": ta["staff"]})
        assert "permission denied" in str(exc.value)


# ---------------------------------------------------------------- pooling, recursion

def test_pooled_connection_does_not_keep_the_previous_tenant(tenants):
    a, ta = tenants["A"]
    pooled = create_engine(engine.url, pool_size=1, max_overflow=0)
    try:
        with pooled.connect() as conn:
            pid = conn.execute(text("SELECT pg_backend_pid()")).scalar()
            conn.execute(text("SELECT set_config('app.org_id', :o, true)"), {"o": a})
            assert conn.execute(text("SELECT COUNT(*) FROM candidate_notes")).scalar() >= 1
            conn.commit()
        with pooled.connect() as conn:  # same physical connection, next request
            assert conn.execute(text("SELECT pg_backend_pid()")).scalar() == pid
            assert conn.execute(text("SELECT current_setting('app.org_id', true)")).scalar() in ("", None)
            assert conn.execute(text("SELECT COUNT(*) FROM candidate_notes")).scalar() == 0
    finally:
        pooled.dispose()


def test_session_context_is_reapplied_after_a_mid_request_commit(tenants):
    a, ta = tenants["A"]
    with SessionLocal() as db:
        set_tenant(db, org_id=a, user_id=ta["staff"])
        assert db.execute(text("SELECT COUNT(*) FROM candidate_notes")).scalar() >= 1
        db.commit()  # new transaction afterwards: context must come back, not vanish
        assert db.execute(text("SELECT current_setting('app.org_id', true)")).scalar() == a
        assert db.execute(text("SELECT COUNT(*) FROM candidate_notes")).scalar() >= 1


@pytest.mark.parametrize("who", ["anonymous", "org_member", "candidate"])
def test_every_table_queries_without_recursion_errors(tenants, who):
    a, ta = tenants["A"]
    org, user = {"anonymous": (None, None), "org_member": (a, ta["staff"]),
                 "candidate": (None, ta["candidate_user"])}[who]
    for table in TENANT_TABLES + sorted(GLOBAL_TABLES):
        if table in NO_APP_SELECT:
            continue
        with app_conn(org, user) as conn:
            conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()  # raises on infinite recursion


# ---------------------------------------------------------------- marketplace and candidates

def test_marketplace_visibility_rules(tenants):
    (a, ta), (b, tb) = tenants["A"], tenants["B"]
    with admin_engine.begin() as conn:
        searchable_user = insert_row(conn, "users", email=f"{_short()}@m.com", role="CANDIDATE", organization_id=None)
        searchable = insert_row(conn, "candidate_profiles", user_id=searchable_user, owner_org_id=None,
                                is_searchable=True, title="x")
        hidden_user = insert_row(conn, "users", email=f"{_short()}@m.com", role="CANDIDATE", organization_id=None)
        hidden = insert_row(conn, "candidate_profiles", user_id=hidden_user, owner_org_id=None,
                            is_searchable=False, title="x")
        applied_user = insert_row(conn, "users", email=f"{_short()}@m.com", role="CANDIDATE", organization_id=None)
        applied = insert_row(conn, "candidate_profiles", user_id=applied_user, owner_org_id=None,
                             is_searchable=False, title="x")
        insert_row(conn, "applications", job_id=ta["job"], candidate_id=applied, organization_id=a)
        for cand, public in ((searchable, True), (hidden, False), (applied, False)):
            insert_row(conn, "embeddings", entity_type="candidate", entity_id=cand, organization_id=None, is_public=public)
    with app_conn(a, ta["staff"]) as conn:
        visible = _visible_pks(conn, "candidate_profiles")
        assert {searchable, applied, ta["candidate"]} <= visible
        assert hidden not in visible and tb["candidate"] not in visible
        vectors = {r[0] for r in conn.execute(text("SELECT entity_id FROM embeddings WHERE entity_type = 'candidate'"))}
        assert searchable in vectors and applied in vectors and hidden not in vectors
    with app_conn(b, tb["staff"]) as conn:  # B: the applicant applied to A, not B
        visible = _visible_pks(conn, "candidate_profiles")
        assert searchable in visible and applied not in visible and hidden not in visible
        vectors = {r[0] for r in conn.execute(text("SELECT entity_id FROM embeddings WHERE entity_type = 'candidate'"))}
        assert hidden not in vectors and applied not in vectors


def test_candidate_sees_own_profile_applications_and_resumes_only(tenants):
    (a, ta), (b, tb) = tenants["A"], tenants["B"]
    with app_conn(None, ta["candidate_user"]) as conn:
        assert _visible_pks(conn, "candidate_profiles") == {ta["candidate"]}
        assert _visible_pks(conn, "applications") == ta["ids"]["applications"]
        assert _visible_pks(conn, "resumes") == ta["ids"]["resumes"]
        assert not (_visible_pks(conn, "interview_feedback") | _visible_pks(conn, "candidate_notes"))
        # and the job they applied to, even though it isn't Active
        assert ta["job"] in _visible_pks(conn, "jobs") and tb["job"] not in _visible_pks(conn, "jobs")


def test_candidates_and_visitors_see_public_org_profiles_not_org_settings(tenants):
    a, ta = tenants["A"]
    with app_conn() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM organizations")).scalar() == 0
        cols = [r[0] for r in conn.execute(text(
            "SELECT column_name FROM information_schema.columns WHERE table_name = 'public_org_profiles' ORDER BY 1"))]
        assert cols == ["domain", "id", "industry", "logo_icon", "name", "website"]
        assert conn.execute(text("SELECT name FROM public_org_profiles WHERE id = :o"), {"o": a}).scalar()
        assert conn.execute(text("SELECT COUNT(*) FROM job_private")).scalar() == 0
