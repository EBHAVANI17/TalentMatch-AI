"""Row-level security cost at scale: the heaviest request paths with RLS on vs app-only checks.

    python scripts/rls_benchmark.py seed  --owner-url postgresql+psycopg://talentmatch:talentmatch@localhost:5433/postgres
    python scripts/rls_benchmark.py run --rls on   --owner-url ...   # requests as talentmatch_app (RLS)
    python scripts/rls_benchmark.py run --rls off  --owner-url ...   # RLS_ENFORCED=false (admin role, app checks only)
    python scripts/rls_benchmark.py report

Seeds a separate database (talentmatch_bench): 20 organizations, 500 jobs, 50,000 candidates
(45,000 marketplace, 70% searchable; 5,000 sourced), ~20,000 applications, embeddings for all.
Each path is called through the real API (warm-up, then timed calls); the slowest SQL statement
of one call is re-run with EXPLAIN (ANALYZE, BUFFERS) on the same role and tenant context.
"""
import argparse
import json
import os
import random
import statistics
import sys
import time
from pathlib import Path

BENCH_DB = "talentmatch_bench"
ROLE_PASSWORD = "tm-bench-only"
OUT_DIR = Path(__file__).resolve().parent / "bench_results"
RECRUITER_EMAIL, RECRUITER_PASSWORD = "bench.recruiter@org00.example.com", "bench-password-1"


def _urls(owner_base: str) -> dict:
    from sqlalchemy.engine import make_url
    base = make_url(owner_base)
    owner = base.set(database=BENCH_DB)

    def role(name):
        return owner.set(username=name, password=ROLE_PASSWORD).render_as_string(hide_password=False)

    return {"owner": owner.render_as_string(hide_password=False), "server": base.render_as_string(hide_password=False),
            "app": role("talentmatch_app"), "admin": role("talentmatch_admin"), "worker": role("talentmatch_worker")}


def _configure_env(urls: dict, rls_on: bool) -> None:
    os.environ.update({
        "DATABASE_OWNER_URL": urls["owner"], "DATABASE_URL": urls["app"], "DATABASE_ADMIN_URL": urls["admin"],
        "DATABASE_WORKER_URL": urls["worker"], "RLS_ENFORCED": "true" if rls_on else "false",
        "DEMO_MODE": "false", "AUTO_MIGRATE": "false", "EMBEDDING_PROVIDER": "hashing", "ENVIRONMENT": "test",
        "RATE_LIMIT_DEFAULT": "1000000/minute", "RATE_LIMIT_AUTH": "1000000/minute",
        "RATE_LIMIT_COPILOT": "1000000/minute", "PASSWORD_HASH_ITERATIONS": "1000", "REDIS_URL": "",
        "GROQ_API_KEY": "", "GEMINI_API_KEY": "", "OPENROUTER_API_KEY": "", "LOG_LEVEL": "WARNING",
    })
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


# ---------------------------------------------------------------------------
def seed(owner_base: str) -> None:
    from sqlalchemy import create_engine, text
    urls = _urls(owner_base)
    server = create_engine(urls["server"], isolation_level="AUTOCOMMIT")
    with server.connect() as conn:
        conn.execute(text(f"DROP DATABASE IF EXISTS {BENCH_DB} WITH (FORCE)"))
        conn.execute(text(f"CREATE DATABASE {BENCH_DB}"))
        conn.execute(text(f"CREATE EXTENSION IF NOT EXISTS vector"))
    with create_engine(urls["owner"], isolation_level="AUTOCOMMIT").connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    _configure_env(urls, rls_on=True)

    from app.core.database import AdminSessionLocal, owner_engine
    from app.core.security import hash_password
    from app.db.migrations import run_migrations
    from app.db.reference_data import ensure_reference_data
    from app.matching import embeddings
    from app.models.db_models import (Application, CandidateProfile, Embedding, Job, Membership, Organization, User)

    run_migrations()
    with owner_engine.begin() as conn:
        for role in ("talentmatch_app", "talentmatch_worker", "talentmatch_admin"):
            conn.execute(text(f"ALTER ROLE {role} PASSWORD '{ROLE_PASSWORD}'"))
    rng = random.Random(42)
    skills_pool = ["Python", "Go", "Java", "TypeScript", "React", "Kubernetes", "AWS", "PostgreSQL", "Kafka", "Rust",
                   "Machine Learning", "PyTorch", "Docker", "GraphQL", "Node.js", "Spark", "Terraform", "Redis"]
    cities = ["Bengaluru, India", "Pune, India", "Hyderabad, India", "San Francisco, CA", "London, UK", "Berlin, Germany"]
    titles = ["Backend Engineer", "Data Scientist", "Frontend Engineer", "DevOps Engineer", "ML Engineer", "Platform Engineer"]
    t0 = time.time()
    with AdminSessionLocal() as db:
        ensure_reference_data(db)
        orgs = [f"org{n:02d}" for n in range(20)]
        db.bulk_insert_mappings(Organization, [dict(id=o, name=f"Bench {o}", domain=f"{o}.example.com",
                                                    status="Active", is_active=True, org_type="standalone",
                                                    max_recruiter_seats=50) for o in orgs])
        db.bulk_insert_mappings(User, [dict(id="usr_bench_rec", email=RECRUITER_EMAIL, full_name="Bench Recruiter",
                                            hashed_password=hash_password(RECRUITER_PASSWORD), role="EMPLOYER_ADMIN",
                                            organization_id="org00", is_active=True, status="Active", email_verified=True)])
        db.bulk_insert_mappings(Membership, [dict(id="mem_bench", user_id="usr_bench_rec", organization_id="org00",
                                                  role="EMPLOYER_ADMIN", status="active")])
        jobs = []
        for i in range(500):
            jobs.append(dict(id=f"job{i:03d}", organization_id=orgs[i % 20], title=rng.choice(titles),
                             department="Engineering", description="Build reliable systems at scale.",
                             required_skills_json=json.dumps(rng.sample(skills_pool, 4)),
                             preferred_skills_json=json.dumps(rng.sample(skills_pool, 2)),
                             min_experience_years=rng.choice([1, 3, 5]), location=rng.choice(cities),
                             workplace_type=rng.choice(["Remote", "Hybrid", "Onsite"]), status="Active"))
        db.bulk_insert_mappings(Job, jobs)
        db.commit()
        users, cands = [], []
        for i in range(50000):
            owner = orgs[i % 20] if i < 5000 else None
            users.append(dict(id=f"usr_c{i:05d}", email=f"cand{i:05d}@bench.example.com", full_name=f"Candidate {i}",
                              hashed_password="x", role="CANDIDATE", is_active=True, status="Active"))
            cands.append(dict(id=f"cand{i:05d}", user_id=f"usr_c{i:05d}", owner_org_id=owner, title=rng.choice(titles),
                              bio="Engineer who ships production systems.",
                              skills_json=json.dumps(rng.sample(skills_pool, 6)),
                              experience_years=rng.randint(0, 15), location=rng.choice(cities),
                              remote_preference=rng.choice(["Remote", "Hybrid", "Onsite"]),
                              is_searchable=(owner is None and rng.random() < 0.7)))
        for start in range(0, 50000, 5000):
            db.bulk_insert_mappings(User, users[start:start + 5000])
            db.bulk_insert_mappings(CandidateProfile, cands[start:start + 5000])
            db.commit()
        apps = []
        for i in range(20000):
            job = jobs[rng.randrange(500)]
            apps.append(dict(id=f"app{i:05d}", job_id=job["id"], candidate_id=f"cand{rng.randrange(5000, 50000):05d}",
                             organization_id=job["organization_id"], stage=rng.choice(["Applied", "Screening", "Interview", "Hired"]),
                             match_score=rng.randint(40, 95)))
        db.bulk_insert_mappings(Application, apps)
        db.commit()
        print(f"rows inserted in {time.time() - t0:.0f}s; embedding...")
        for start in range(0, 50000, 2000):
            batch = db.query(CandidateProfile).order_by(CandidateProfile.id).offset(start).limit(2000).all()
            embeddings.refresh(db, "candidate", batch)
            db.commit()
        embeddings.refresh(db, "job", db.query(Job).all())
        db.commit()
        print(f"embeddings done in {time.time() - t0:.0f}s; warming matches for job000 (org00)...")
    # Matches for the benchmark job, computed once as the organization (so both runs measure the read path)
    _warm_matches()
    with owner_engine.begin() as conn:
        conn.execute(text("ANALYZE"))
    print(f"seeded in {time.time() - t0:.0f}s")


def _warm_matches() -> None:
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as client:
        token = _login(client)
        r = client.get("/api/v1/matching/jobs/job000/candidates", headers=token, params={"limit": 50})
        assert r.status_code == 200, r.text


def _login(client) -> dict:
    r = client.post("/api/v1/auth/login", json={"email": RECRUITER_EMAIL, "password": RECRUITER_PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


# ---------------------------------------------------------------------------
PATHS = {
    "match_list": ("GET", "/api/v1/matching/jobs/job000/candidates", {"params": {"limit": 50}}),
    "hybrid_search": ("GET", "/api/v1/search", {"params": {"q": "senior python engineer in Pune with 5 years", "limit": 20}}),
    "skill_ranking_search": ("GET", "/api/v1/search", {"params": {"q": "Kubernetes Kafka Go Terraform", "limit": 20}}),
    "pipeline_summary": ("GET", "/api/v1/dashboard/recruiter", {"params": {"job_id": "job000"}}),
    "dashboard": ("GET", "/api/v1/dashboard/recruiter", {}),
    "copilot_top_matches": ("POST", "/api/v1/copilot/messages",
                            {"json": {"message": "Who are the best candidates?", "context": {"job_id": "job000"}}}),
}


def run(owner_base: str, rls_on: bool, calls: int) -> None:
    urls = _urls(owner_base)
    _configure_env(urls, rls_on)
    from fastapi.testclient import TestClient
    from sqlalchemy import event, text

    from app.core.database import engine
    from app.main import app

    captured = []

    @event.listens_for(engine, "before_cursor_execute")
    def _before(conn, cursor, statement, parameters, context, executemany):
        context._bench_start = time.perf_counter()

    @event.listens_for(engine, "after_cursor_execute")
    def _after(conn, cursor, statement, parameters, context, executemany):
        captured.append((time.perf_counter() - context._bench_start, statement, parameters))

    results = {}
    with TestClient(app) as client:
        headers = _login(client)
        for name, (method, path, kwargs) in PATHS.items():
            for _ in range(2):  # warm-up
                client.request(method, path, headers=headers, **kwargs)
            timings = []
            for _ in range(calls):
                started = time.perf_counter()
                r = client.request(method, path, headers=headers, **kwargs)
                timings.append((time.perf_counter() - started) * 1000)
                assert r.status_code == 200, (name, r.status_code, r.text[:300])
            captured.clear()
            client.request(method, path, headers=headers, **kwargs)
            app_sql = [c for c in captured if "set_config(" not in c[1]]
            slowest = max(app_sql, key=lambda c: c[0])
            plan = _explain(engine, slowest[1], slowest[2], rls_on)
            results[name] = {
                "p50_ms": round(statistics.median(timings), 1),
                "p95_ms": round(sorted(timings)[max(0, int(len(timings) * 0.95) - 1)], 1),
                "statements": len(app_sql),
                "sql_total_ms": round(sum(c[0] for c in app_sql) * 1000, 1),
                "slowest_sql_ms": round(slowest[0] * 1000, 1),
                "explain_execution_ms": plan["execution_ms"],
                "explain_planning_ms": plan["planning_ms"],
                "slowest_sql": slowest[1][:400],
                "plan_head": plan["head"],
            }
            print(f"{name:22s} p50 {results[name]['p50_ms']:8.1f} ms  slowest SQL {results[name]['explain_execution_ms']} ms")
    OUT_DIR.mkdir(exist_ok=True)
    (OUT_DIR / f"rls_{'on' if rls_on else 'off'}.json").write_text(json.dumps(results, indent=2))


def _explain(engine, statement: str, parameters, rls_on: bool) -> dict:
    from sqlalchemy import text
    with engine.connect() as conn:
        raw = conn.connection.dbapi_connection
        with raw.cursor() as cur:
            if rls_on:
                cur.execute("SELECT set_config('app.org_id', 'org00', true), set_config('app.user_id', 'usr_bench_rec', true)")
            cur.execute("EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + statement, parameters)
            plan = cur.fetchone()[0][0]
        raw.rollback()
    head = plan["Plan"]
    return {"execution_ms": round(plan["Execution Time"], 2), "planning_ms": round(plan["Planning Time"], 2),
            "head": f"{head['Node Type']} rows={head.get('Actual Rows')} loops={head.get('Actual Loops')}"}


def report() -> None:
    on = json.loads((OUT_DIR / "rls_on.json").read_text())
    off = json.loads((OUT_DIR / "rls_off.json").read_text())
    print(f"{'path':22s} {'p50 off':>9s} {'p50 on':>9s} {'ratio':>6s} | {'SQL off':>8s} {'SQL on':>8s} {'ratio':>6s}")
    for name in PATHS:
        a, b = off[name], on[name]
        r1 = b["p50_ms"] / a["p50_ms"] if a["p50_ms"] else 0
        r2 = b["explain_execution_ms"] / a["explain_execution_ms"] if a["explain_execution_ms"] else 0
        print(f"{name:22s} {a['p50_ms']:9.1f} {b['p50_ms']:9.1f} {r1:6.2f} | {a['explain_execution_ms']:8.2f} "
              f"{b['explain_execution_ms']:8.2f} {r2:6.2f}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["seed", "run", "report"])
    parser.add_argument("--owner-url", default="postgresql+psycopg://talentmatch:talentmatch@localhost:5433/postgres")
    parser.add_argument("--rls", choices=["on", "off"], default="on")
    parser.add_argument("--calls", type=int, default=10)
    args = parser.parse_args()
    if args.command == "seed":
        seed(args.owner_url)
    elif args.command == "run":
        run(args.owner_url, args.rls == "on", args.calls)
    else:
        report()
