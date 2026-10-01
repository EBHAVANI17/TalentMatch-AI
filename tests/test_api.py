import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))

import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"

def test_auth_login_candidate():
    response = client.post("/api/v1/auth/login", json={
        "email": "aarav@stanford.edu",
        "password": "aarav123"
    })
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["user"]["role"] == "CANDIDATE"

def test_auth_login_employer():
    response = client.post("/api/v1/auth/login", json={
        "email": "recruiter@anthropic.com",
        "password": "anthropic123"
    })
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["user"]["role"] == "EMPLOYER_ADMIN"

def test_auth_login_super_admin():
    response = client.post("/api/v1/auth/login", json={
        "email": "admin@talentmatch.ai",
        "password": "admin123"
    })
    assert response.status_code == 200
    data = response.json()
    assert data["user"]["role"] == "SUPER_ADMIN"

def test_get_jobs():
    response = client.get("/api/v1/jobs")
    assert response.status_code == 200
    jobs = response.json()
    assert len(jobs) >= 5
    assert "required_skills" in jobs[0]

def test_get_candidates():
    response = client.get("/api/v1/candidates")
    assert response.status_code == 200
    candidates = response.json()
    assert len(candidates) >= 4

def test_ai_recommendations_for_candidate():
    response = client.get("/api/v1/recommendations/jobs-for-candidate/cand_001")
    assert response.status_code == 200
    matches = response.json()
    assert len(matches) > 0
    assert matches[0]["match_score"] >= 80
    assert "explanation" in matches[0]
    assert "breakdown" in matches[0]["explanation"]

def test_ai_outreach_generation():
    response = client.post("/api/v1/ai/generate-outreach", json={
        "candidate_id": "cand_001",
        "job_id": "job_001",
        "tone": "Compelling & Visionary"
    })
    assert response.status_code == 200
    data = response.json()
    assert "subject_line" in data
    assert "email_body" in data

def test_ai_resume_tailor():
    response = client.post("/api/v1/ai/tailor-resume", json={
        "candidate_id": "cand_001",
        "target_job_id": "job_001"
    })
    assert response.status_code == 200
    data = response.json()
    assert "ats_compatibility_score" in data
    assert len(data["bullet_point_enhancements"]) > 0

def test_ai_interview_prep():
    response = client.post("/api/v1/ai/interview-prep", json={
        "candidate_id": "cand_001",
        "job_id": "job_001"
    })
    assert response.status_code == 200
    data = response.json()
    assert "questions" in data
    assert len(data["questions"]) >= 3

def test_admin_system_stats():
    response = client.get("/api/v1/admin/stats")
    assert response.status_code == 200
    data = response.json()
    assert data["total_users"] >= 5
    assert data["total_jobs"] >= 5

def test_admin_audit_logs():
    response = client.get("/api/v1/admin/audit-logs")
    assert response.status_code == 200
    logs = response.json()
    assert len(logs) > 0

def test_ai_auto_screen_application():
    response = client.post("/api/v1/ai/auto-screen-application/app_001")
    assert response.status_code == 200
    data = response.json()
    assert "recommendation" in data
    assert "technical_fit_score" in data
    assert len(data["hiring_manager_probing_questions"]) > 0

def test_ai_autonomous_sourcing():
    response = client.post("/api/v1/ai/autonomous-sourcing", json={
        "job_id": "job_001",
        "target_count": 3
    })
    assert response.status_code == 200
    data = response.json()
    assert "sourced_candidates" in data
    assert len(data["sourced_candidates"]) > 0
    assert len(data["sourced_candidates"][0]["outreach_sequence"]) == 3

def test_ai_mock_interview_grader():
    response = client.post("/api/v1/ai/mock-interview/grade-answer", json={
        "question": "How do you handle distributed caching and cache invalidation?",
        "category": "System Design",
        "candidate_answer": "I use Redis cluster with write-through caching, consistent hashing for partitioning, and Kafka event stream invalidation to prevent stale data and maintain P99 latency.",
        "job_title": "Staff Backend Engineer",
        "target_company": "Anthropic"
    })
    assert response.status_code == 200
    data = response.json()
    assert data["composite_score"] >= 70
    assert "exemplary_model_answer" in data
    assert len(data["strengths"]) > 0

def test_ai_job_spec_optimizer():
    response = client.post("/api/v1/ai/optimize-job-spec", json={
        "raw_job_description": "Looking for a 10x rockstar ninja to dominate the market with 10+ years in Kubernetes and LLMs.",
        "job_title": "Staff AI Engineer"
    })
    assert response.status_code == 200
    data = response.json()
    assert data["optimized_inclusivity_score"] > data["original_inclusivity_score"]
    assert "rockstar" not in data["optimized_job_description"].lower()

def test_ai_learning_roadmap():
    response = client.post("/api/v1/ai/learning-roadmap", json={
        "candidate_id": "cand_001",
        "target_job_id": "job_001"
    })
    assert response.status_code == 200
    data = response.json()
    assert len(data["weeks"]) == 4
    assert data["projected_post_roadmap_score"] >= data["current_match_score"]

def test_candidate_executive_dossier():
    response = client.get("/api/v1/candidates/cand_001/dossier")
    assert response.status_code == 200
    data = response.json()
    assert "overall_readiness_grade" in data
    assert len(data["top_technical_superpowers"]) > 0

def test_organizations_api():
    response = client.get("/api/v1/organizations")
    assert response.status_code == 200
    orgs = response.json()
    assert len(orgs) >= 3
    assert orgs[0]["plan_tier"] is not None

def test_admin_users_api():
    response = client.get("/api/v1/admin/users")
    assert response.status_code == 200
    users = response.json()
    assert len(users) >= 5

def test_admin_plans_api():
    response = client.get("/api/v1/admin/plans")
    assert response.status_code == 200
    plans = response.json()
    assert len(plans) >= 3
    plan_names = [p["name"] for p in plans]
    assert any("Enterprise" in name for name in plan_names)


def test_resume_upload_and_intelligence():
    sample_resume = b"""
    Aarav Sharma
    Senior AI & Distributed Systems Engineer
    San Francisco, CA | aarav@stanford.edu
    
    Summary: 6+ years of production experience architecting high-throughput vector search engines,
    distributed LLM serving infrastructure, and real-time Kafka event streams.
    
    Skills: Python, PyTorch, LLMs & RAG, FastAPI, CUDA & GPU Optimization, Vector Databases, PostgreSQL & pgvector, Kubernetes, Docker, AWS
    
    Experience:
    Staff AI Engineer - Anthropic (2022 - Present)
    - Architected low-latency LLM inference engines scaling to 50k QPS.
    - Optimized P99 latency by 42% through custom Triton kernel optimizations and multi-tier Redis caching.
    
    Education:
    M.S. in Computer Science - Stanford University (2020)
    """
    response = client.post(
        "/api/v1/resumes/upload",
        files={"file": ("aarav_resume.txt", sample_resume, "text/plain")},
        data={"candidate_id": "cand_001", "target_job_id": "job_001"}
    )
    assert response.status_code == 200
    data = response.json()
    assert "latest_analysis" in data
    analysis = data["latest_analysis"]
    assert analysis["overall_quality_score"] >= 70
    assert analysis["ats_compatibility_score"] >= 70
    assert len(analysis["findings"]) > 0

def test_application_lifecycle_and_audit():
    from app.core.database import SessionLocal
    from app.models.db_models import Application, ApplicationStageHistory
    
    # Clean up test application record to ensure test idempotency across runs
    with SessionLocal() as db:
        existing_apps = db.query(Application).filter(Application.candidate_id == "cand_002", Application.job_id == "job_003").all()
        for a in existing_apps:
            db.query(ApplicationStageHistory).filter(ApplicationStageHistory.application_id == a.id).delete()
            db.delete(a)
        db.commit()

    # 1. Submit Application
    app_res = client.post("/api/v1/applications", json={
        "candidate_id": "cand_002",
        "job_id": "job_003",
        "cover_note": "Thrilled to apply for the Staff Systems role."
    })
    assert app_res.status_code == 200
    app_data = app_res.json()
    app_id = app_data["id"]
    assert app_data["stage"] == "Applied"

    # 2. Advance Stage to Interview
    stage_res = client.patch(f"/api/v1/applications/{app_id}/stage", json={
        "stage": "Interviewing",
        "reason": "Strong portfolio review and architectural screening"
    })
    assert stage_res.status_code == 200
    assert stage_res.json()["stage"] == "Interviewing"

    # 3. Verify Stage History Audit Trail
    history_res = client.get(f"/api/v1/applications/{app_id}/history")
    assert history_res.status_code == 200
    history = history_res.json()
    assert len(history) >= 1
    assert history[0]["to_stage"] == "Interviewing"


def test_job_creation_with_copilot_spec():
    # 1. Test AI Spec Generation
    spec_res = client.post("/api/v1/ai/generate-job-spec", json={
        "title": "Principal Distributed Systems Architect"
    })
    assert spec_res.status_code == 200
    spec = spec_res.json()
    assert "title" in spec
    assert len(spec["required_skills"]) > 0

    # 2. Test Publishing Job
    create_res = client.post("/api/v1/jobs", json={
        "title": spec["title"],
        "department": spec.get("department", "Infrastructure"),
        "description": spec["description"],
        "required_skills": spec["required_skills"],
        "preferred_skills": spec.get("preferred_skills", ["Rust"]),
        "min_experience_years": 8.0,
        "location": "San Francisco, CA",
        "workplace_type": "Hybrid",
        "salary_min": 240000,
        "salary_max": 320000,
        "equity": "0.2%",
        "required_education": "B.S. in Computer Science",
        "urgency": "High",
        "key_responsibilities": spec.get("key_responsibilities", ["Scale cluster throughput"]),
        "benefits": ["Medical", "401(k)"]
    })
    assert create_res.status_code == 200
    job = create_res.json()
    assert job["title"] == spec["title"]
    assert job["salary_max"] == 320000


def test_notifications_lifecycle():
    # 1. Fetch In-App Notifications
    notifs_res = client.get("/api/v1/notifications")
    assert notifs_res.status_code == 200
    notifs = notifs_res.json()
    assert len(notifs) > 0

    # 2. Mark First Notification as Read
    first_id = notifs[0]["id"]
    patch_res = client.patch(f"/api/v1/notifications/{first_id}/read")
    assert patch_res.status_code == 200
    assert patch_res.json()["is_read"] is True


def test_admin_taxonomies_creation():
    response = client.post("/api/v1/admin/taxonomies?name=Mojo&category=Languages&demand_level=High&avg_salary_boost=%2B20%25")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Mojo"
    assert data["category"] == "Languages"


def test_organization_plan_update():
    patch_res = client.patch("/api/v1/organizations/org_anthropic", json={
        "plan_tier": "Enterprise"
    })
    assert patch_res.status_code == 200
    assert patch_res.json()["plan_tier"] == "Enterprise"


def test_user_status_update():
    patch_res = client.patch("/api/v1/users/usr_cand_aarav/status", json={
        "status": "Active"
    })
    assert patch_res.status_code == 200
    assert patch_res.json()["status"] == "Active"



