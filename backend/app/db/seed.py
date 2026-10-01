import json
import uuid
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.database import SessionLocal
from app.core.security import hash_password
from app.db.migrations import run_migrations
from app.db.reference_data import ensure_reference_data
from app.models.db_models import (
    Organization, User, CandidateProfile, WorkExperience, EducationRecord,
    CandidateProject, Resume, ResumeVersion, ResumeAnalysis, Job, Application,
    ApplicationStageHistory, Interview, InterviewFeedback, Plan, AIUsageRecord,
    Notification, AuditLog, SkillTaxonomy
)

def init_db():
    """Bring the schema up to date, then load demo data when DEMO_MODE is on."""
    if settings.auto_migrate:
        run_migrations()
    if settings.demo_mode:
        seed_demo_data()
    with SessionLocal() as db:
        ensure_reference_data(db)  # platform data (skill ontology); idempotent


def seed_demo_data():
    """Idempotent: does nothing if the database already has users.

    Run manually with:  python -m app.db.seed   (from the backend/ folder)
    """
    db = SessionLocal()
    try:
        # Check if already seeded
        if db.query(User).count() > 0:
            print("Database already initialized with records.")
            return

        print("Seeding production enterprise database with authentic multi-tenant records...")

        # 1. Seed Plans & Entitlements Catalog
        plans_data = [
            Plan(id="free", name="Free Starter", monthly_price=0, max_recruiter_seats=1, max_active_jobs=2, monthly_ai_credits=200, allow_autonomous_sourcing=False, allow_custom_roadmaps=False),
            Plan(id="pro", name="Growth Pro", monthly_price=299, max_recruiter_seats=5, max_active_jobs=15, monthly_ai_credits=2000, allow_autonomous_sourcing=True, allow_custom_roadmaps=True),
            Plan(id="business", name="Business Scale", monthly_price=899, max_recruiter_seats=15, max_active_jobs=50, monthly_ai_credits=8000, allow_autonomous_sourcing=True, allow_custom_roadmaps=True),
            Plan(id="enterprise", name="Enterprise Ultra", monthly_price=2499, max_recruiter_seats=50, max_active_jobs=200, monthly_ai_credits=30000, allow_autonomous_sourcing=True, allow_custom_roadmaps=True)
        ]
        for p in plans_data:
            db.add(p)
        db.flush()

        # 2. Seed Organizations (Tenants)
        orgs_data = [
            {
                "id": "org_anthropic",
                "name": "Anthropic AI",
                "domain": "anthropic.com",
                "industry": "Frontier AI & Safety",
                "plan_tier": "Enterprise Ultra",
                "logo_icon": "sparkles",
                "website": "https://anthropic.com",
                "status": "Active",
                "max_recruiter_seats": 25,
                "max_active_jobs": 100,
                "monthly_ai_credits": 25000,
                "monthly_ai_credits_used": 4820
            },
            {
                "id": "org_stripe",
                "name": "Stripe",
                "domain": "stripe.com",
                "industry": "Financial Infrastructure",
                "plan_tier": "Enterprise Ultra",
                "logo_icon": "credit-card",
                "website": "https://stripe.com",
                "status": "Active",
                "max_recruiter_seats": 20,
                "max_active_jobs": 80,
                "monthly_ai_credits": 20000,
                "monthly_ai_credits_used": 3410
            },
            {
                "id": "org_vercel",
                "name": "Vercel",
                "domain": "vercel.com",
                "industry": "Cloud & Edge Frameworks",
                "plan_tier": "Enterprise",
                "logo_icon": "triangle",
                "website": "https://vercel.com",
                "status": "Active",
                "max_recruiter_seats": 15,
                "max_active_jobs": 50,
                "monthly_ai_credits": 15000,
                "monthly_ai_credits_used": 2190
            },
            {
                "id": "org_databricks",
                "name": "Databricks",
                "domain": "databricks.com",
                "industry": "Lakehouse & AI Data",
                "plan_tier": "Enterprise",
                "logo_icon": "boxes",
                "website": "https://databricks.com",
                "status": "Active",
                "max_recruiter_seats": 15,
                "max_active_jobs": 40,
                "monthly_ai_credits": 12000,
                "monthly_ai_credits_used": 1840
            },
            {
                "id": "org_supabase",
                "name": "Supabase",
                "domain": "supabase.com",
                "industry": "Open Source Cloud DB",
                "plan_tier": "Growth",
                "logo_icon": "database",
                "website": "https://supabase.com",
                "status": "Active",
                "max_recruiter_seats": 8,
                "max_active_jobs": 20,
                "monthly_ai_credits": 6000,
                "monthly_ai_credits_used": 950
            }
        ]

        for o in orgs_data:
            db.add(Organization(**o))
        db.flush()

        # 3. Seed Super Admin
        super_admin = User(
            id="usr_superadmin",
            email="admin@talentmatch.ai",
            hashed_password=hash_password("admin123"),
            full_name="Alexander Wright (Super Admin)",
            role="SUPER_ADMIN",
            organization_id=None,
            avatar_url="https://images.unsplash.com/photo-1472099645785-5658abf4ff4e?w=200",
            status="Active",
            is_active=True,
            email_verified=True,
            last_login_at=datetime.utcnow()
        )
        db.add(super_admin)

        # 4. Seed Employer & Recruiter Users
        employers = [
            ("usr_rec_anthropic", "recruiter@anthropic.com", "anthropic123", "Sarah Jenkins", "EMPLOYER_ADMIN", "org_anthropic", "https://images.unsplash.com/photo-1573496359142-b8d87734a5a2?w=200"),
            ("usr_rec_stripe", "recruiter@stripe.com", "stripe123", "David Sterling", "EMPLOYER_ADMIN", "org_stripe", "https://images.unsplash.com/photo-1500648767791-00dcc994a43e?w=200"),
            ("usr_rec_vercel", "recruiter@vercel.com", "vercel123", "Guillermo Rauch", "EMPLOYER_ADMIN", "org_vercel", "https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=200"),
            ("usr_rec_databricks", "recruiter@databricks.com", "databricks123", "Ali Ghodsi", "EMPLOYER_ADMIN", "org_databricks", "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=200"),
            ("usr_rec_supabase", "recruiter@supabase.com", "supabase123", "Paul Copplestone", "EMPLOYER_ADMIN", "org_supabase", "https://images.unsplash.com/photo-1580489944761-15a19d654956?w=200"),
        ]

        for uid, email, pwd, name, role, org_id, avatar in employers:
            db.add(User(
                id=uid,
                email=email,
                hashed_password=hash_password(pwd),
                full_name=name,
                role=role,
                organization_id=org_id,
                avatar_url=avatar,
                status="Active",
                is_active=True,
                email_verified=True,
                last_login_at=datetime.utcnow()
            ))
        db.flush()

        # 5. Seed Candidates & Sub-Entities
        pending_resume_analyses = []
        candidates_raw = [
            {
                "user_id": "usr_cand_aarav",
                "email": "aarav@stanford.edu",
                "password": "aarav123",
                "full_name": "Aarav Sharma",
                "profile_id": "cand_001",
                "title": "Staff AI Infrastructure & LLM Systems Engineer",
                "bio": "Specialized in high-throughput LLM inference, vLLM / TensorRT-LLM optimizations, distributed RAG vector indexing, and low-latency API architectures.",
                "skills": ["Python", "PyTorch", "LLMs & RAG", "CUDA & GPU Optimization", "Vector Databases", "FastAPI", "Docker", "Kubernetes", "PostgreSQL & pgvector"],
                "experience_years": 6.0,
                "location": "San Francisco, CA",
                "remote_preference": "Remote",
                "expected_salary": 185000,
                "education": "Master's in Computer Science (Stanford)",
                "github": "https://github.com/aarav-sharma-ai",
                "linkedin": "https://linkedin.com/in/aarav-sharma-ml",
                "portfolio": "https://aaravsharma.io",
                "avatar": "https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=200",
                "ats_score": 96,
                "work": [
                    {
                        "company": "Scale AI",
                        "title": "Senior Machine Learning Systems Engineer",
                        "start": "2022-01",
                        "end": "Present",
                        "is_current": True,
                        "desc": "Led LLM inference acceleration cluster reducing P99 latency by 35%.",
                        "achievements": ["Engineered TensorRT-LLM kernels for 70B parameter models", "Scaled vLLM cluster serving 40k QPS with zero downtime"]
                    },
                    {
                        "company": "Amazon AWS",
                        "title": "Software Engineer II - SageMaker",
                        "start": "2019-06",
                        "end": "2021-12",
                        "is_current": False,
                        "desc": "Built distributed model training primitives and GPU orchestration pipelines.",
                        "achievements": ["Automated spot instance recovery saving $1.2M in annual cluster spend"]
                    }
                ],
                "edu_list": [
                    {"inst": "Stanford University", "degree": "Master of Science", "field": "Computer Science (AI Specialization)", "year": 2019, "gpa": "3.92"}
                ],
                "proj_list": [
                    {"title": "vLLM-FlashRouter", "desc": "Sub-millisecond token routing proxy across multi-node GPU clusters.", "stack": ["Python", "CUDA", "FastAPI", "Docker"], "live": "https://vllm-flash.io", "repo": "https://github.com/aarav-sharma-ai/vllm-flashrouter"}
                ]
            },
            {
                "user_id": "usr_cand_elena",
                "email": "elena@cmu.edu",
                "password": "elena123",
                "full_name": "Elena Rostova",
                "profile_id": "cand_002",
                "title": "Principal Full Stack & Distributed Platform Architect",
                "bio": "Architecting resilient multi-tenant enterprise platforms, real-time collaboration engines, and developer-first cloud applications serving millions of users.",
                "skills": ["TypeScript", "Next.js", "React", "Node.js", "PostgreSQL & pgvector", "Distributed Systems", "AWS", "Docker", "Kubernetes", "Microservices"],
                "experience_years": 7.5,
                "location": "New York, NY",
                "remote_preference": "Remote",
                "expected_salary": 195000,
                "education": "Bachelor's in Software Engineering (CMU)",
                "github": "https://github.com/elena-rostova",
                "linkedin": "https://linkedin.com/in/elena-rostova",
                "portfolio": "https://elenarostova.dev",
                "avatar": "https://images.unsplash.com/photo-1580489944761-15a19d654956?w=200",
                "ats_score": 94,
                "work": [
                    {
                        "company": "Linear",
                        "title": "Staff Platform Engineer",
                        "start": "2021-08",
                        "end": "Present",
                        "is_current": True,
                        "desc": "Designed offline-first synchronization architecture and Edge rendering pipelines.",
                        "achievements": ["Reduced sync conflict resolution latency to under 8ms", "Scaled Next.js platform to 3M daily active developers"]
                    }
                ],
                "edu_list": [
                    {"inst": "Carnegie Mellon University", "degree": "Bachelor of Science", "field": "Software Engineering", "year": 2018, "gpa": "3.88"}
                ],
                "proj_list": [
                    {"title": "SyncEngine Edge", "desc": "Zero-latency real-time collaborative state synchronization framework.", "stack": ["TypeScript", "Next.js", "Rust", "WebSockets"], "live": "https://syncengine.dev", "repo": "https://github.com/elena-rostova/syncengine"}
                ]
            },
            {
                "user_id": "usr_cand_marcus",
                "email": "marcus@berkeley.edu",
                "password": "marcus123",
                "full_name": "Marcus Chen",
                "profile_id": "cand_003",
                "title": "Senior Distributed Systems & Core Backend Engineer",
                "bio": "Passionate about zero-downtime distributed consensus (Raft/Paxos), low-latency ledger backends, and lock-free concurrency.",
                "skills": ["Go", "Rust", "Distributed Systems", "System Design", "Microservices", "PostgreSQL & pgvector", "Kubernetes", "Docker", "SQL"],
                "experience_years": 5.0,
                "location": "Seattle, WA",
                "remote_preference": "Hybrid",
                "expected_salary": 165000,
                "education": "Bachelor's in Computer Engineering (UC Berkeley)",
                "github": "https://github.com/marcus-chen-core",
                "linkedin": "https://linkedin.com/in/marcus-chen-systems",
                "portfolio": "https://marcuschen.me",
                "avatar": "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=200",
                "ats_score": 92,
                "work": [
                    {
                        "company": "Robinhood",
                        "title": "Senior Backend Systems Engineer",
                        "start": "2020-04",
                        "end": "Present",
                        "is_current": True,
                        "desc": "Led core order routing ledger engine processing $2B+ in daily transactions.",
                        "achievements": ["Achieved P99 latency < 5ms for order routing", "Migrated critical path services from Python to Go"]
                    }
                ],
                "edu_list": [
                    {"inst": "UC Berkeley", "degree": "Bachelor of Science", "field": "Computer Engineering", "year": 2020, "gpa": "3.85"}
                ],
                "proj_list": [
                    {"title": "RaftLite", "desc": "High-throughput, zero-allocation Raft consensus library in Go.", "stack": ["Go", "Distributed Systems", "gRPC"], "live": "", "repo": "https://github.com/marcus-chen-core/raftlite"}
                ]
            },
            {
                "user_id": "usr_cand_sophia",
                "email": "sophia@austin.io",
                "password": "sophia123",
                "full_name": "Sophia Vance",
                "profile_id": "cand_004",
                "title": "Staff Cloud Platform & Site Reliability Engineer",
                "bio": "DevOps & SRE leader orchestrating global multi-cloud infrastructure, zero-trust security meshes, automated chaos engineering, and 99.999% uptime SLAs.",
                "skills": ["AWS", "Kubernetes", "Terraform", "Docker", "CI/CD & GitOps", "Python", "Go", "Distributed Systems"],
                "experience_years": 8.0,
                "location": "Austin, TX",
                "remote_preference": "Remote",
                "expected_salary": 180000,
                "education": "Bachelor's in Computer Science",
                "github": "https://github.com/sophia-vance-devops",
                "linkedin": "https://linkedin.com/in/sophia-vance",
                "portfolio": "https://sophiavance.dev",
                "avatar": "https://images.unsplash.com/photo-1573496359142-b8d87734a5a2?w=200",
                "ats_score": 95,
                "work": [
                    {
                        "company": "HashiCorp",
                        "title": "Staff Platform SRE",
                        "start": "2019-01",
                        "end": "Present",
                        "is_current": True,
                        "desc": "Architected multi-region Kubernetes control planes spanning 50,000+ nodes.",
                        "achievements": ["Maintained 99.999% SLA across 4 global cloud regions", "Created automated chaos testing framework reducing incident MTTR by 48%"]
                    }
                ],
                "edu_list": [
                    {"inst": "University of Texas at Austin", "degree": "Bachelor of Science", "field": "Computer Science", "year": 2017, "gpa": "3.80"}
                ],
                "proj_list": [
                    {"title": "KubeMesh-Guard", "desc": "Automated zero-trust policy enforcement for multi-tenant Kubernetes clusters.", "stack": ["Go", "Kubernetes", "Terraform", "Docker"], "live": "", "repo": "https://github.com/sophia-vance-devops/kubemesh-guard"}
                ]
            }
        ]

        for c in candidates_raw:
            user = User(
                id=c["user_id"],
                email=c["email"],
                hashed_password=hash_password(c["password"]),
                full_name=c["full_name"],
                role="CANDIDATE",
                organization_id=None,
                avatar_url=c["avatar"],
                status="Active",
                is_active=True,
                email_verified=True,
                last_login_at=datetime.utcnow()
            )
            db.add(user)
            db.flush()

            profile = CandidateProfile(
                id=c["profile_id"],
                user_id=c["user_id"],
                title=c["title"],
                bio=c["bio"],
                skills_json=json.dumps(c["skills"]),
                experience_years=c["experience_years"],
                location=c["location"],
                remote_preference=c["remote_preference"],
                expected_salary=c["expected_salary"],
                education=c["education"],
                github_url=c["github"],
                linkedin_url=c["linkedin"],
                portfolio_url=c["portfolio"],
                ats_score=c["ats_score"]
            )
            db.add(profile)
            db.flush()

            # Seed Work Experiences
            for w in c.get("work", []):
                db.add(WorkExperience(
                    id=f"exp_{uuid.uuid4().hex[:8]}",
                    candidate_id=profile.id,
                    company_name=w["company"],
                    job_title=w["title"],
                    start_date=w["start"],
                    end_date=w["end"],
                    is_current=w["is_current"],
                    description=w["desc"],
                    achievements_json=json.dumps(w["achievements"])
                ))

            # Seed Education
            for edu in c.get("edu_list", []):
                db.add(EducationRecord(
                    id=f"edu_{uuid.uuid4().hex[:8]}",
                    candidate_id=profile.id,
                    institution=edu["inst"],
                    degree=edu["degree"],
                    field_of_study=edu["field"],
                    graduation_year=edu["year"],
                    gpa=edu["gpa"]
                ))

            # Seed Projects
            for proj in c.get("proj_list", []):
                db.add(CandidateProject(
                    id=f"proj_{uuid.uuid4().hex[:8]}",
                    candidate_id=profile.id,
                    title=proj["title"],
                    description=proj["desc"],
                    tech_stack_json=json.dumps(proj["stack"]),
                    live_url=proj["live"],
                    repo_url=proj["repo"]
                ))

            # Seed Resume & Analysis
            resume = Resume(
                id=f"res_{uuid.uuid4().hex[:8]}",
                candidate_id=profile.id,
                title=f"{c['full_name']} — Master CV 2026",
                original_filename=f"{c['full_name'].replace(' ', '_')}_Resume_2026.pdf",
                file_format="pdf",
                file_size_bytes=425000,
                file_storage_path=f"/storage/resumes/{profile.id}/v1.pdf",
                current_version=1,
                is_primary=True,
                processing_status="Parsed"
            )
            db.add(resume)
            db.flush()

            db.add(ResumeVersion(
                id=f"rver_{uuid.uuid4().hex[:8]}",
                resume_id=resume.id,
                version_number=1,
                storage_path=resume.file_storage_path,
                extracted_text=f"{c['title']} with {c['experience_years']} years experience in {', '.join(c['skills'])}.",
                parsed_payload_json=json.dumps({"skills": c["skills"], "experience_years": c["experience_years"]})
            ))

            # Added after jobs exist: target_job_id has a foreign key to jobs
            pending_resume_analyses.append(ResumeAnalysis(
                id=f"ranal_{uuid.uuid4().hex[:8]}",
                resume_id=resume.id,
                target_job_id="job_001",
                ats_compatibility_score=c["ats_score"],
                skills_coverage_score=94,
                experience_presentation_score=90,
                achievement_strength_score=88,
                keyword_alignment_score=92,
                formatting_completeness_score=96,
                overall_quality_score=92,
                findings_json=json.dumps([
                    "Strong section heading structure and ATS machine-readable fonts",
                    "Dense, verified technical skills in high-demand domains",
                    "Quantified metrics across performance gains and scale"
                ]),
                missing_items_json=json.dumps([
                    "Specify exact CUDA version (e.g. CUDA 12.2 vs 11.8)",
                    "Include quantifiable cloud budget savings on GPU clusters"
                ]),
                suggestions_json=json.dumps([
                    "Quantify vLLM throughput improvements in token/sec per GPU",
                    "Highlight distributed fault tolerance mechanisms during node eviction"
                ]),
                raw_analysis_notes="Excellent candidate resume with top-tier technical depth and verified open-source contributions."
            ))

        db.flush()

        # 6. Seed Jobs
        jobs_raw = [
            {
                "id": "job_001",
                "org_id": "org_anthropic",
                "title": "Staff AI Infrastructure & Inference Engineer",
                "dept": "Foundation AI Research",
                "desc": "Join our Core Systems team to scale large-scale generative model inference, build ultra-low-latency distributed RAG systems, and optimize GPU cluster throughput.",
                "resp": [
                    "Architect and optimize multi-GPU inference kernels using CUDA, PyTorch, and TensorRT.",
                    "Design distributed vector retrieval pipelines supporting billions of embeddings.",
                    "Collaborate with research scientists to productionize frontier reasoning models."
                ],
                "req_skills": ["Python", "PyTorch", "LLMs & RAG", "CUDA & GPU Optimization", "Vector Databases", "FastAPI"],
                "pref_skills": ["Kubernetes", "Docker", "PostgreSQL & pgvector", "Distributed Systems"],
                "min_exp": 5.0,
                "location": "San Francisco, CA",
                "workplace": "Remote",
                "sal_min": 180000,
                "sal_max": 230000,
                "equity": "0.1% - 0.25%",
                "edu": "Master's",
                "benefits": ["Unlimited PTO", "$10k Learning Stipend", "Top-tier Health/Dental/Vision", "Comprehensive 401(k) Match"],
                "applicants": 28
            },
            {
                "id": "job_002",
                "org_id": "org_vercel",
                "title": "Principal Full Stack Cloud Platform Architect",
                "dept": "Core Framework & Edge Infrastructure",
                "desc": "Architect next-generation edge rendering engines, high-performance Next.js primitives, and developer tooling trusted by millions of engineers globally.",
                "resp": [
                    "Spearhead architecture of Next.js edge runtimes and server actions.",
                    "Build zero-latency global state synchronization engines for web applications.",
                    "Lead and mentor senior engineering squads across full-stack distributed domains."
                ],
                "req_skills": ["TypeScript", "Next.js", "React", "Node.js", "Distributed Systems", "AWS"],
                "pref_skills": ["PostgreSQL & pgvector", "Docker", "Kubernetes", "Microservices"],
                "min_exp": 6.0,
                "location": "San Francisco, CA",
                "workplace": "Remote",
                "sal_min": 190000,
                "sal_max": 240000,
                "equity": "0.15% - 0.35%",
                "edu": "Bachelor's",
                "benefits": ["Work from anywhere worldwide", "Home Office Setup Grant ($5,000)", "Annual Team Retreats", "Parental Leave (16 Weeks)"],
                "applicants": 42
            },
            {
                "id": "job_003",
                "org_id": "org_stripe",
                "title": "Lead Distributed Ledger & Systems Engineer",
                "dept": "Global Financial Infrastructure",
                "desc": "Engineer zero-fault transactional ledgers, global clearing systems, and fault-tolerant financial pipelines processing trillions in gross volume annually.",
                "resp": [
                    "Build lock-free, ultra-durable transactional ledger services in Go and Rust.",
                    "Ensure sub-10ms P99 API latency across global multi-region deployments.",
                    "Implement automated formal verification and chaos engineering simulations."
                ],
                "req_skills": ["Go", "Rust", "Distributed Systems", "System Design", "PostgreSQL & pgvector", "Microservices"],
                "pref_skills": ["Kubernetes", "Docker", "SQL"],
                "min_exp": 5.0,
                "location": "Seattle, WA",
                "workplace": "Remote",
                "sal_min": 175000,
                "sal_max": 225000,
                "equity": "0.1% - 0.2%",
                "edu": "Bachelor's",
                "benefits": ["401(k) 100% Match up to 6%", "Wellness & Fitness Reimbursement", "Comprehensive Family Health Cover"],
                "applicants": 35
            },
            {
                "id": "job_004",
                "org_id": "org_databricks",
                "title": "Staff Platform & Multi-Cloud Infrastructure Engineer",
                "dept": "Lakehouse Cloud Infrastructure",
                "desc": "Design resilient multi-cloud Kubernetes control planes, automated GitOps deployments, and infrastructure scaling across millions of compute cores.",
                "resp": [
                    "Orchestrate enterprise Kubernetes clusters across AWS, GCP, and Azure.",
                    "Standardize Terraform and GitOps automation for mission-critical platform components.",
                    "Drive SRE best practices, observability tooling, and automated remediation."
                ],
                "req_skills": ["AWS", "Kubernetes", "Terraform", "Docker", "CI/CD & GitOps", "Distributed Systems"],
                "pref_skills": ["Python", "Go"],
                "min_exp": 7.0,
                "location": "Austin, TX",
                "workplace": "Remote",
                "sal_min": 180000,
                "sal_max": 235000,
                "equity": "0.1% - 0.3%",
                "edu": "Bachelor's",
                "benefits": ["Generous Stock Options (Pre-IPO)", "Catered Lunches / DoorDash Allowance", "Full Medical Coverage"],
                "applicants": 19
            },
            {
                "id": "job_005",
                "org_id": "org_supabase",
                "title": "Senior AI Database & Vector Engine Engineer",
                "dept": "Database Core & AI Extensions",
                "desc": "Scale open-source PostgreSQL, pgvector search acceleration, and serverless vector indexing for millions of AI developers worldwide.",
                "resp": [
                    "Contribute to pgvector performance optimization and HNSW indexing.",
                    "Build real-time vector streaming engines and embedding pipelines.",
                    "Engage directly with the open-source community to solve frontier database scaling challenges."
                ],
                "req_skills": ["Python", "PostgreSQL & pgvector", "Vector Databases", "FastAPI", "Docker"],
                "pref_skills": ["Rust", "PyTorch", "LLMs & RAG", "Distributed Systems"],
                "min_exp": 4.0,
                "location": "San Francisco, CA",
                "workplace": "Remote",
                "sal_min": 165000,
                "sal_max": 210000,
                "equity": "0.1% - 0.25%",
                "edu": "Bachelor's",
                "benefits": ["100% Remote Anywhere", "Flexible Hours", "Open Source Sponsorship", "Hardware Budget"],
                "applicants": 16
            }
        ]

        for j in jobs_raw:
            job = Job(
                id=j["id"],
                organization_id=j["org_id"],
                created_by_user_id=None,
                title=j["title"],
                department=j["dept"],
                description=j["desc"],
                responsibilities_json=json.dumps(j["resp"]),
                required_skills_json=json.dumps(j["req_skills"]),
                preferred_skills_json=json.dumps(j["pref_skills"]),
                min_experience_years=j["min_exp"],
                location=j["location"],
                workplace_type=j["workplace"],
                salary_min=j["sal_min"],
                salary_max=j["sal_max"],
                equity=j["equity"],
                required_education=j["edu"],
                urgency="High",
                status="Active",
                benefits_json=json.dumps(j["benefits"]),
                applicants_count=j["applicants"]
            )
            db.add(job)
        db.flush()
        db.add_all(pending_resume_analyses)
        db.flush()

        # 7. Seed Applications, Stage Histories & Interviews
        apps_raw = [
            {
                "id": "app_001",
                "job_id": "job_001",
                "candidate_id": "cand_001",
                "match_score": 96,
                "stage": "Interview",
                "cover_note": "Excited to apply my experience in vLLM / TensorRT-LLM and distributed vector indexing to Anthropic's core inference systems.",
                "score_breakdown": {
                    "skills_score": 98.0,
                    "experience_score": 100.0,
                    "location_score": 100.0,
                    "salary_score": 95.0,
                    "education_score": 100.0
                }
            },
            {
                "id": "app_002",
                "job_id": "job_002",
                "candidate_id": "cand_002",
                "match_score": 95,
                "stage": "Offered",
                "cover_note": "Passionate about edge runtimes and developer productivity. Built SyncEngine to power real-time collaborative state.",
                "score_breakdown": {
                    "skills_score": 96.0,
                    "experience_score": 100.0,
                    "location_score": 100.0,
                    "salary_score": 92.0,
                    "education_score": 100.0
                }
            },
            {
                "id": "app_003",
                "job_id": "job_003",
                "candidate_id": "cand_003",
                "match_score": 94,
                "stage": "Interview",
                "cover_note": "Focused on low-latency transactional consensus and lock-free systems.",
                "score_breakdown": {
                    "skills_score": 95.0,
                    "experience_score": 100.0,
                    "location_score": 100.0,
                    "salary_score": 95.0,
                    "education_score": 100.0
                }
            }
        ]

        for a in apps_raw:
            app = Application(
                id=a["id"],
                job_id=a["job_id"],
                candidate_id=a["candidate_id"],
                match_score=a["match_score"],
                stage=a["stage"],
                cover_note=a["cover_note"],
                score_breakdown_json=json.dumps(a["score_breakdown"])
            )
            db.add(app)
            db.flush()

            # Add Stage Transition History
            db.add(ApplicationStageHistory(
                id=f"hist_{uuid.uuid4().hex[:8]}",
                application_id=app.id,
                from_stage="Applied",
                to_stage="AI Screened",
                changed_by_user_id="usr_rec_anthropic",
                reason="Auto-screened by Autonomous AI screener with 96% score."
            ))
            if a["stage"] in ["Interview", "Offered"]:
                db.add(ApplicationStageHistory(
                    id=f"hist_{uuid.uuid4().hex[:8]}",
                    application_id=app.id,
                    from_stage="AI Screened",
                    to_stage="Interview",
                    changed_by_user_id="usr_rec_anthropic",
                    reason="Advanced to Technical Architecture interview."
                ))

            # Add Interview Record
            if a["stage"] == "Interview":
                interview = Interview(
                    id=f"int_{uuid.uuid4().hex[:8]}",
                    application_id=app.id,
                    interviewer_user_id="usr_rec_anthropic",
                    round_name="Technical Architecture & Kernel Optimization",
                    scheduled_at=datetime.utcnow() + timedelta(days=2),
                    status="Scheduled",
                    meeting_link="https://meet.google.com/xyz-anthropic-tech"
                )
                db.add(interview)
                db.flush()

                db.add(InterviewFeedback(
                    id=f"feed_{uuid.uuid4().hex[:8]}",
                    interview_id=interview.id,
                    interviewer_id="usr_rec_anthropic",
                    rating=5,
                    technical_score=96,
                    communication_score=92,
                    strengths="Exceptional understanding of GPU memory hierarchy, vLLM paging, and CUDA streams.",
                    growth_areas="Could deepen familiarity with Triton custom kernels.",
                    decision="Strong Hire",
                    notes="Recommended for Staff level AI Infrastructure position."
                ))

        db.flush()

        # 8. Seed AI Telemetry Records
        ai_telemetry_samples = [
            ("org_anthropic", "usr_rec_anthropic", "autonomous_sourcing", "NexusNLP-v2.5", "SUCCESS", 18, 420),
            ("org_anthropic", "usr_rec_anthropic", "resume_parsing", "NexusNLP-v2.5", "SUCCESS", 12, 380),
            ("org_stripe", "usr_rec_stripe", "job_matching", "NexusVector-v2.0", "SUCCESS", 9, 290),
            ("org_vercel", "usr_rec_vercel", "dei_optimization", "NexusDEI-v1.4", "SUCCESS", 14, 340),
            (None, "usr_cand_aarav", "mock_interview_grading", "NexusInterviewer-v2.5", "SUCCESS", 22, 510)
        ]
        for org_id, uid, op, prov, st, lat, tok in ai_telemetry_samples:
            db.add(AIUsageRecord(
                id=f"ai_{uuid.uuid4().hex[:8]}",
                organization_id=org_id,
                user_id=uid,
                operation_type=op,
                provider=prov,
                status=st,
                latency_ms=lat,
                tokens_consumed=tok
            ))

        # 9. Seed Skill Taxonomies
        taxonomies = [
            ("Python", "Languages", "Very High", "+18%"),
            ("TypeScript", "Languages", "Very High", "+20%"),
            ("Rust", "Languages", "Very High", "+28%"),
            ("Go", "Languages", "Very High", "+22%"),
            ("React", "Frameworks", "Very High", "+18%"),
            ("Next.js", "Frameworks", "Very High", "+22%"),
            ("FastAPI", "Frameworks", "Very High", "+19%"),
            ("PyTorch", "Data & AI", "Very High", "+32%"),
            ("LLMs & RAG", "Data & AI", "Extremely High", "+35%"),
            ("Vector Databases", "Data & AI", "Very High", "+25%"),
            ("CUDA & GPU Optimization", "Data & AI", "Extremely High", "+40%"),
            ("PostgreSQL & pgvector", "Data & AI", "Very High", "+18%"),
            ("Distributed Systems", "Architecture", "Extremely High", "+30%"),
            ("Kubernetes", "Cloud & DevOps", "Very High", "+22%"),
            ("AWS", "Cloud & DevOps", "Very High", "+18%"),
            ("Terraform", "Cloud & DevOps", "High", "+16%"),
            ("Docker", "Cloud & DevOps", "Very High", "+15%"),
            ("CI/CD & GitOps", "Cloud & DevOps", "High", "+14%")
        ]

        for name, cat, demand, boost in taxonomies:
            db.add(SkillTaxonomy(
                id=f"tax_{uuid.uuid4().hex[:8]}",
                name=name,
                category=cat,
                demand_level=demand,
                avg_salary_boost=boost
            ))

        # 10. Seed Notifications & Audit Logs
        db.add(Notification(
            id=f"notif_{uuid.uuid4().hex[:8]}",
            user_id="usr_cand_aarav",
            title="Interview Invitation Received!",
            message="Anthropic AI has advanced your application for Staff AI Infrastructure Engineer to the Tech Interview round.",
            type="stage_change",
            link="/applications"
        ))

        db.add(AuditLog(
            id=f"audit_{uuid.uuid4().hex[:8]}",
            organization_id="org_anthropic",
            user_id="usr_superadmin",
            user_email="admin@talentmatch.ai",
            action="SYSTEM_INIT",
            module="Core",
            entity="System",
            entity_id="prod_cluster",
            details_json=json.dumps({"version": "3.0.0", "status": "Initialized Enterprise Multi-Tenant Store"}),
            ip_address="127.0.0.1",
            status="SUCCESS"
        ))

        db.commit()
        _finalize_demo_data(db)
        print("Production enterprise database seeded successfully with normalized models!")

    except Exception as e:
        db.rollback()
        print(f"Error seeding database: {e}")
        raise e
    finally:
        db.close()

def _finalize_demo_data(db):
    """Fill fields the seed lists above don't set: normalized skills, tenant on applications, publish dates."""
    from app.services.skills_service import sync_all_skill_links

    from app.services.pipeline_service import STAGE_ALIASES

    for application in db.query(Application).all():
        application.organization_id = application.job.organization_id if application.job else None
        application.stage = STAGE_ALIASES.get((application.stage or "").lower(), application.stage)
    for job in db.query(Job).filter(Job.status == "Active", Job.published_at.is_(None)).all():
        job.published_at = job.created_at
    db.commit()
    sync_all_skill_links(db)

    from app.matching import embeddings

    embeddings.refresh(db, "candidate", db.query(CandidateProfile).all())
    embeddings.refresh(db, "job", db.query(Job).all())
    db.commit()


if __name__ == "__main__":
    run_migrations()
    seed_demo_data()
