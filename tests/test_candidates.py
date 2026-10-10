"""Candidate profiles: self-service editing, contact privacy, search, sourcing and recruiter notes."""
import uuid

from app.core.database import AdminSessionLocal as SessionLocal  # test setup bypasses RLS
from app.models.db_models import CandidateSkill, User


def _new_candidate(client):
    email = f"profile.{uuid.uuid4().hex[:8]}@example.com"
    res = client.post("/api/v1/auth/register/candidate", json={
        "email": email, "password": "candidate-pass-1", "full_name": "Riya Menon", "skills": ["Python"],
    })
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}, email


FULL_PROFILE = {
    "full_name": "Riya K. Menon",
    "title": "Senior Backend Engineer",
    "bio": "Backend engineer focused on payments infrastructure, reliability and developer experience.",
    "phone": "+91 98765 43210",
    "skills": ["Python", "Go", "PostgreSQL", "go"],
    "experience_years": 6.5,
    "location": "Bangalore, India",
    "remote_preference": "hybrid",
    "expected_salary": 4200000,
    "notice_period_days": 60,
    "availability": "passive",
    "preferred_locations": ["Bangalore", " Remote ", ""],
    "employment_types": ["Full-time"],
    "linkedin_url": "https://linkedin.com/in/riya",
    "work_experience": [
        {"company_name": "Razorpay", "job_title": "Backend Engineer", "start_date": "2021-04", "is_current": True,
         "achievements": ["Cut settlement latency by 40%"]},
        {"company_name": "Infosys", "job_title": "Software Engineer", "start_date": "2018-07", "end_date": "2021-03"},
    ],
    "education_records": [{"institution": "NIT Trichy", "degree": "B.Tech", "field_of_study": "CSE", "graduation_year": 2018}],
    "certifications": [{"name": "AWS Solutions Architect Associate", "issuer": "Amazon", "issued_on": "2023-02"}],
    "languages": [{"language": "English", "proficiency": "professional"}, {"language": "Malayalam", "proficiency": "native"}],
    "projects": [{"title": "Ledger service", "tech_stack": ["Go", "Kafka"]}],
}


def test_candidate_edits_full_profile(client):
    headers, email = _new_candidate(client)
    before = client.get("/api/v1/candidates/me", headers=headers).json()

    res = client.patch("/api/v1/candidates/me", headers=headers, json=FULL_PROFILE)
    assert res.status_code == 200, res.text
    p = res.json()
    assert p["name"] == "Riya K. Menon" and p["email"] == email and p["phone"] == "+91 98765 43210"
    assert p["skills"] == ["Python", "Go", "PostgreSQL"]
    assert p["remote_preference"] == "Hybrid"
    assert p["preferred_locations"] == ["Bangalore", "Remote"]
    assert [w["company_name"] for w in p["work_experience"]][0] == "Razorpay"
    assert p["work_experience"][0]["end_date"] == "" and p["work_experience"][0]["is_current"] is True
    assert p["certifications"][0]["issuer"] == "Amazon"
    assert {l["language"] for l in p["languages"]} == {"English", "Malayalam"}
    assert p["projects"][0]["tech_stack"] == ["Go", "Kafka"]
    assert p["profile_strength"] > before["profile_strength"]

    with SessionLocal() as db:
        assert db.query(CandidateSkill).filter(CandidateSkill.candidate_id == p["id"]).count() == 3

    # Lists are replaced, other fields untouched
    res = client.patch("/api/v1/candidates/me", headers=headers, json={"languages": []}).json()
    assert res["languages"] == [] and res["certifications"] and res["title"] == "Senior Backend Engineer"


def test_profile_validation(client):
    headers, _ = _new_candidate(client)
    assert client.patch("/api/v1/candidates/me", headers=headers, json={"remote_preference": "Mars"}).status_code == 422
    assert client.patch("/api/v1/candidates/me", headers=headers, json={"availability": "maybe"}).status_code == 422
    assert client.patch("/api/v1/candidates/me", headers=headers, json={"notice_period_days": -1}).status_code == 422


def test_recruiters_only_see_contacts_of_applicants(client, auth):
    h = auth("anthropic")
    applied = client.get("/api/v1/candidates/cand_001", headers=h).json()   # applied to Anthropic
    browsing = client.get("/api/v1/candidates/cand_002", headers=h).json()  # talent pool only
    assert applied["contact_visible"] and applied["email"] == "aarav@stanford.edu"
    assert not browsing["contact_visible"] and browsing["email"] == "" and browsing["phone"] == ""
    assert browsing["name"]  # the profile itself is still visible

    listing = {c["id"]: c for c in client.get("/api/v1/candidates", headers=h).json()}
    assert listing["cand_001"]["email"] and listing["cand_002"]["email"] == ""

    matches = client.get("/api/v1/recommendations/candidates-for-job/job_001", headers=h).json()
    by_id = {m["candidate"]["id"]: m["candidate"] for m in matches}
    assert by_id["cand_001"]["email"] and by_id["cand_002"]["email"] == ""

    assert client.get("/api/v1/candidates/cand_002", headers=auth("admin")).json()["email"] == "elena@cmu.edu"


def test_candidate_search_filters(client, auth):
    h = auth("admin")
    ids = lambda **params: {c["id"] for c in client.get("/api/v1/candidates", headers=h, params=params).json()}
    everyone = ids()
    assert ids(skills=["Python"]) <= everyone
    assert ids(skills=["Python", "No Such Skill"]) == set()          # all skills must match
    assert ids(min_experience=100) == set()
    assert ids(q="Aarav") == {"cand_001"}
    page_1 = client.get("/api/v1/candidates", headers=h, params={"sort": "name", "limit": 2}).json()
    page_2 = client.get("/api/v1/candidates", headers=h, params={"sort": "name", "limit": 2, "offset": 2}).json()
    assert len(page_1) == 2 and not {c["id"] for c in page_1} & {c["id"] for c in page_2}


def test_sourced_candidates_are_private_to_their_organization(client, auth):
    stripe, anthropic = auth("stripe"), auth("anthropic")
    email = f"sourced.{uuid.uuid4().hex[:8]}@example.com"
    res = client.post("/api/v1/candidates", headers=stripe, json={
        "full_name": "Sam Sourced", "email": email, "title": "SRE", "skills": ["Go", "Kubernetes"], "location": "Dublin",
    })
    assert res.status_code == 201, res.text
    cand = res.json()
    assert cand["source"] == "recruiter" and cand["owner_org_id"] == "org_stripe"
    assert cand["email"] == email and cand["skills"] == ["Go", "Kubernetes"]

    # Stripe can see and edit them; nobody else can see them
    assert client.patch(f"/api/v1/candidates/{cand['id']}", headers=stripe, json={"title": "Senior SRE"}).json()["title"] == "Senior SRE"
    assert client.get(f"/api/v1/candidates/{cand['id']}", headers=anthropic).status_code == 404
    assert cand["id"] not in {c["id"] for c in client.get("/api/v1/candidates", headers=anthropic).json()}
    assert cand["id"] in {c["id"] for c in client.get("/api/v1/candidates", headers=stripe, params={"source": "recruiter"}).json()}

    # The placeholder account cannot sign in, and the address can't be sourced twice
    with SessionLocal() as db:
        assert db.query(User).filter(User.email == email).one().is_active is False
    assert client.post("/api/v1/candidates", headers=stripe, json={"full_name": "Dup", "email": email}).status_code == 409
    assert client.post("/api/v1/candidates", headers=stripe, json={"full_name": "Aarav", "email": "aarav@stanford.edu"}).status_code == 409

    # Recruiters can add sourced candidates to their own jobs
    res = client.post("/api/v1/applications", headers=stripe, json={"job_id": "job_003", "candidate_id": cand["id"]})
    assert res.status_code == 200 and res.json()["stage"] == "Applied"


def test_recruiters_cannot_edit_self_registered_profiles(client, auth):
    assert client.patch("/api/v1/candidates/cand_002", headers=auth("stripe"), json={"title": "x"}).status_code == 403
    assert client.post("/api/v1/candidates", headers=auth("aarav"), json={"full_name": "x", "email": "x@example.com"}).status_code == 403


def test_recruiter_notes_are_private_to_the_organization(client, auth):
    anthropic, stripe = auth("anthropic"), auth("stripe")
    res = client.post("/api/v1/candidates/cand_001/notes", headers=anthropic,
                      json={"body": "Strong systems design. Follow up on Rust experience.", "application_id": "app_001"})
    assert res.status_code == 201, res.text
    note = res.json()
    assert note["author_name"] == "Sarah Jenkins"

    assert note["id"] in [n["id"] for n in client.get("/api/v1/candidates/cand_001/notes", headers=anthropic).json()]
    assert note["id"] not in [n["id"] for n in client.get("/api/v1/candidates/cand_001/notes", headers=stripe).json()]
    assert client.patch(f"/api/v1/candidates/cand_001/notes/{note['id']}", headers=stripe, json={"body": "x"}).status_code == 404
    assert client.get("/api/v1/candidates/cand_001/notes", headers=auth("aarav")).status_code == 403
    # application must belong to the same candidate
    assert client.post("/api/v1/candidates/cand_002/notes", headers=anthropic,
                       json={"body": "wrong app", "application_id": "app_001"}).status_code in (404, 422)

    edited = client.patch(f"/api/v1/candidates/cand_001/notes/{note['id']}", headers=anthropic, json={"body": "Updated"})
    assert edited.json()["body"] == "Updated"
    assert client.delete(f"/api/v1/candidates/cand_001/notes/{note['id']}", headers=anthropic).status_code == 204


def test_bulk_resume_upload_multiple_files_and_zip(client, auth):
    import io
    import zipfile

    headers = auth("stripe")

    # 1. Multi-file upload
    resume1 = b"Alex River\nSenior Distributed Systems Engineer\nSkills: Python, Go, Docker, Kubernetes\nExperience: 7 years\nEngineered distributed key-value cache reducing latency by 45%.\nEmail: alex@example.com"
    resume2 = b"Priya Patel\nFull Stack AI Engineer\nSkills: TypeScript, React, PyTorch, FastAPI\nExperience: 5 years\nArchitected end-to-end vector search pipeline serving 10k QPS.\nEmail: priya@example.com"

    files = [
        ("files", ("resume_alex.txt", resume1, "text/plain")),
        ("files", ("resume_priya.txt", resume2, "text/plain")),
    ]

    res = client.post("/api/v1/candidates/bulk-upload-resumes", headers=headers, files=files)
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["total_files_received"] == 2
    assert data["successful_count"] == 2
    assert data["failed_count"] == 0
    names = [r["parsed"]["name"] for r in data["results"]]
    assert "Alex River" in names
    assert "Priya Patel" in names

    # 2. ZIP archive upload containing multiple resumes and 1 unreadable file
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as z:
        z.writestr("candidate1.txt", resume1)
        z.writestr("candidate2.txt", resume2)
        z.writestr("corrupted.txt", b"x")

    zip_buffer.seek(0)
    zip_files = [
        ("files", ("resumes_batch.zip", zip_buffer.getvalue(), "application/zip"))
    ]

    res_zip = client.post("/api/v1/candidates/bulk-upload-resumes", headers=headers, files=zip_files)
    assert res_zip.status_code == 200, res_zip.text
    zip_data = res_zip.json()
    assert zip_data["total_files_received"] == 3
    assert zip_data["successful_count"] == 2
    assert zip_data["failed_count"] == 1
    assert any(r["status"] == "error" for r in zip_data["results"])

