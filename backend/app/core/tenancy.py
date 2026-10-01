"""Tenant-aware authorization.

Every request that touches tenant data resolves a TenantContext (who is calling,
which organization they belong to, what they may do). Routers use the helpers
below instead of hand-written checks, so the visibility rules live in one place:

  * SUPER_ADMIN            sees everything.
  * Organization members   see their own organization's jobs, applications and
                           users, plus candidates who are searchable or applied
                           to one of their jobs.
  * CANDIDATE              sees only their own profile/applications, and the
                           public (Active) job board.
  * Anonymous              sees only the public job board.

Resources the caller may not see are reported as 404, not 403, so their
existence isn't leaked across tenants.
"""
from dataclasses import dataclass
from typing import Callable, Optional

from fastapi import Depends, HTTPException, status
from sqlalchemy import and_, exists, or_
from sqlalchemy.orm import Query, Session

from app.core.security import ROLE_PERMISSIONS, get_current_user, get_current_user_optional
from app.models.db_models import Application, CandidateProfile, Job, User

SUPER_ADMIN = "SUPER_ADMIN"
CANDIDATE = "CANDIDATE"
ORG_ROLES = {"ORG_ADMIN", "EMPLOYER_ADMIN", "RECRUITER", "HIRING_MANAGER", "INTERVIEWER", "ANALYST"}
ORG_ADMIN_ROLES = {"ORG_ADMIN", "EMPLOYER_ADMIN"}

PUBLIC_JOB_STATUS = "Active"


@dataclass
class TenantContext:
    user: User

    @property
    def role(self) -> str:
        return self.user.role

    @property
    def org_id(self) -> Optional[str]:
        return self.user.organization_id

    @property
    def is_super_admin(self) -> bool:
        return self.role == SUPER_ADMIN

    @property
    def is_candidate(self) -> bool:
        return self.role == CANDIDATE

    @property
    def is_org_member(self) -> bool:
        return self.role in ORG_ROLES and self.org_id is not None

    @property
    def is_org_admin(self) -> bool:
        return self.role in ORG_ADMIN_ROLES and self.org_id is not None

    @property
    def candidate_id(self) -> Optional[str]:
        profile = self.user.candidate_profile
        return profile.id if profile else None

    def has(self, permission: str) -> bool:
        return permission in ROLE_PERMISSIONS.get(self.role, set())

    def require(self, permission: str) -> None:
        if not self.has(permission):
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Access denied. Missing permission: {permission}")


# ---------------------------------------------------------------------------
# FastAPI dependencies
# ---------------------------------------------------------------------------
def get_tenant(user: User = Depends(get_current_user)) -> TenantContext:
    org = user.organization
    if org is not None and not org.is_active and user.role != SUPER_ADMIN:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Organization is suspended")
    return TenantContext(user=user)


def get_tenant_optional(user: Optional[User] = Depends(get_current_user_optional)) -> Optional[TenantContext]:
    if user is None or not user.is_active:
        return None
    return get_tenant(user)


def require_permission(*permissions: str) -> Callable[..., TenantContext]:
    def checker(ctx: TenantContext = Depends(get_tenant)) -> TenantContext:
        for permission in permissions:
            ctx.require(permission)
        return ctx
    return checker


def require_super_admin(ctx: TenantContext = Depends(get_tenant)) -> TenantContext:
    if not ctx.is_super_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Super admin access required")
    return ctx


def not_found(entity: str) -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, f"{entity} not found")


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------
def scope_jobs(query: Query, ctx: Optional[TenantContext]) -> Query:
    if ctx and ctx.is_super_admin:
        return query
    if ctx and ctx.is_org_member:
        return query.filter(Job.organization_id == ctx.org_id)
    return query.filter(Job.status == PUBLIC_JOB_STATUS)


def can_view_job(ctx: Optional[TenantContext], job: Job) -> bool:
    if job.status == PUBLIC_JOB_STATUS:
        return True
    return bool(ctx and (ctx.is_super_admin or (ctx.is_org_member and job.organization_id == ctx.org_id)))


def can_manage_job(ctx: TenantContext, job: Job) -> bool:
    if ctx.is_super_admin:
        return True
    return ctx.is_org_member and job.organization_id == ctx.org_id and ctx.has("jobs:create_edit")


def get_visible_job(db: Session, ctx: Optional[TenantContext], job_id: str) -> Job:
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job or not can_view_job(ctx, job):
        raise not_found("Job requisition")
    return job


def get_managed_job(db: Session, ctx: TenantContext, job_id: str) -> Job:
    job = db.query(Job).filter(Job.id == job_id).first()
    in_tenant = job is not None and (ctx.is_super_admin or (ctx.is_org_member and job.organization_id == ctx.org_id))
    if not in_tenant:
        raise not_found("Job requisition")
    if not can_manage_job(ctx, job):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You cannot manage this job requisition")
    return job


# ---------------------------------------------------------------------------
# Candidates
# ---------------------------------------------------------------------------
def _applied_to_org(org_id: str):
    return exists().where(
        Application.candidate_id == CandidateProfile.id,
        Application.organization_id == org_id,
    )


def scope_candidates(query: Query, ctx: TenantContext) -> Query:
    if ctx.is_super_admin:
        return query
    if ctx.is_org_member:
        # Own sourced candidates, plus marketplace talent that is searchable or applied to us.
        return query.filter(or_(
            CandidateProfile.owner_org_id == ctx.org_id,
            and_(
                CandidateProfile.owner_org_id.is_(None),
                or_(CandidateProfile.is_searchable.is_(True), _applied_to_org(ctx.org_id)),
            ),
        ))
    if ctx.is_candidate:
        return query.filter(CandidateProfile.user_id == ctx.user.id)
    return query.filter(False)


def can_view_candidate(db: Session, ctx: TenantContext, candidate: CandidateProfile) -> bool:
    if ctx.is_super_admin or candidate.user_id == ctx.user.id:
        return True
    if not ctx.is_org_member:
        return False
    if candidate.owner_org_id is not None:
        return candidate.owner_org_id == ctx.org_id
    if candidate.is_searchable:
        return True
    return db.query(
        exists().where(
            Application.candidate_id == candidate.id,
            Application.organization_id == ctx.org_id,
        )
    ).scalar()


def get_visible_candidate(db: Session, ctx: TenantContext, candidate_id: str) -> CandidateProfile:
    candidate = db.query(CandidateProfile).filter(CandidateProfile.id == candidate_id).first()
    if not candidate or not can_view_candidate(db, ctx, candidate):
        raise not_found("Candidate profile")
    return candidate


def is_own_candidate_profile(ctx: TenantContext, candidate: CandidateProfile) -> bool:
    return candidate.user_id == ctx.user.id


# ---------------------------------------------------------------------------
# Applications
# ---------------------------------------------------------------------------
def scope_applications(query: Query, ctx: TenantContext) -> Query:
    if ctx.is_super_admin:
        return query
    if ctx.is_org_member:
        return query.filter(Application.organization_id == ctx.org_id)
    if ctx.is_candidate and ctx.candidate_id:
        return query.filter(Application.candidate_id == ctx.candidate_id)
    return query.filter(False)


def can_view_application(ctx: TenantContext, application: Application) -> bool:
    if ctx.is_super_admin:
        return True
    if ctx.is_org_member:
        return application.organization_id == ctx.org_id
    return ctx.candidate_id is not None and application.candidate_id == ctx.candidate_id


def get_visible_application(db: Session, ctx: TenantContext, application_id: str) -> Application:
    application = db.query(Application).filter(Application.id == application_id).first()
    if not application or not can_view_application(ctx, application):
        raise not_found("Application record")
    return application


def get_org_application(db: Session, ctx: TenantContext, application_id: str) -> Application:
    """An application the caller may act on as the hiring side (not as the candidate)."""
    application = get_visible_application(db, ctx, application_id)
    if not (ctx.is_super_admin or ctx.is_org_member):
        raise not_found("Application record")
    return application


# ---------------------------------------------------------------------------
# Users / organizations
# ---------------------------------------------------------------------------
def can_view_org(ctx: TenantContext, org_id: str) -> bool:
    return ctx.is_super_admin or (ctx.org_id is not None and ctx.org_id == org_id)


def can_manage_user(ctx: TenantContext, target: User) -> bool:
    if target.id == ctx.user.id:
        return False  # nobody suspends or re-roles themselves
    if ctx.is_super_admin:
        return True
    return ctx.is_org_admin and target.organization_id == ctx.org_id and target.role != SUPER_ADMIN
