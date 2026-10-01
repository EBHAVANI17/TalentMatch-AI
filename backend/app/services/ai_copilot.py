import re
from typing import List, Dict
from app.db.repository import repo
from app.models.schemas import (
    OutreachPitchResponse, ResumeTailorResponse, InterviewPrepResponse,
    InterviewQuestion, JobSpecGenerateResponse
)

class AICopilotService:

    @staticmethod
    def generate_outreach_pitch(candidate_id: str, job_id: str, tone: str) -> OutreachPitchResponse:
        candidate = repo.get_candidate(candidate_id) or repo.get_all_candidates()[0]
        job = repo.get_job(job_id) or repo.get_all_jobs()[0]

        # Identify overlap skills
        overlap = [s for s in job.required_skills if s.lower() in [c.lower() for c in candidate.skills]]
        top_skill = overlap[0] if overlap else "distributed systems"
        
        project_name = candidate.featured_projects[0]["name"] if candidate.featured_projects else "your recent high-throughput systems"

        subject = f"Scaling {job.department} at {job.company} — Impressed by {candidate.name.split()[0]}'s work on {project_name}"
        
        hook = f"I came across your work on {project_name} and your deep expertise in {top_skill} and {', '.join(overlap[:2])}."
        
        if "casual" in tone.lower():
            salutation = f"Hey {candidate.name.split()[0]},"
            closing = "Best,\nTalent Acquisition Team"
        elif "direct" in tone.lower():
            salutation = f"Hi {candidate.name.split()[0]},"
            closing = "Looking forward to connecting,\nEngineering Leadership"
        else:
            salutation = f"Dear {candidate.name},"
            closing = f"Warm regards,\nExecutive Talent Partner @ {job.company}"

        email_body = f"""{salutation}

{hook} We are currently scaling our core team for the {job.title} position at {job.company} ({job.workplace_type}).

Why this is an exceptional match for you:
• Ownership & Impact: Lead technical decisions on {job.description.split('.')[0].lower()}.
• Real-World Tech Stack: Deep hands-on development with {', '.join(job.required_skills[:4])}.
• Top-of-Market Package: Target compensation of ${job.salary_min:,} - ${job.salary_max:,}/year + {job.equity} equity.

Given your {candidate.experience_years} years of proven expertise in {', '.join(candidate.skills[:3])}, we believe you would play a defining role in shaping our next engineering milestones.

Would you be open to an informal 15-minute sync with our VP of Engineering this Thursday or Friday?

{closing}
{job.company} | {job.company_domain}"""

        selling_points = [
            f"Directly leverages {candidate.name.split()[0]}'s mastery of {top_skill}",
            f"100% {job.workplace_type} flexibility with ${job.salary_min:,}-${job.salary_max:,} compensation",
            f"Immediate leadership visibility in {job.department}"
        ]

        return OutreachPitchResponse(
            subject_line=subject,
            email_body=email_body,
            personalized_hook=hook,
            key_selling_points=selling_points
        )

    @staticmethod
    def tailor_resume(candidate_id: str, resume_text: str, target_job_id: str) -> ResumeTailorResponse:
        job = repo.get_job(target_job_id) or repo.get_all_jobs()[0]
        
        # Get candidate text or provided text
        if candidate_id and not resume_text:
            cand = repo.get_candidate(candidate_id)
            if cand:
                resume_text = f"{cand.name} - {cand.title}\n{cand.bio}\nSkills: {', '.join(cand.skills)}"

        text_lower = resume_text.lower()
        
        matched_kw = []
        missing_kw = []
        for s in job.required_skills + job.preferred_skills:
            if s.lower() in text_lower:
                matched_kw.append(s)
            else:
                missing_kw.append(s)

        matched_kw = list(set(matched_kw))
        missing_kw = list(set(missing_kw))

        ats_score = int(min(98, max(45, (len(matched_kw) / max(len(job.required_skills), 1)) * 100)))

        opt_summary = (
            f"High-impact {job.title} with proven track record in {', '.join(matched_kw[:3]) if matched_kw else 'distributed engineering'}. "
            f"Experienced in architecting mission-critical {job.department.lower()} platforms, optimizing latency, and scaling {job.required_skills[0]} applications."
        )

        bullet_enhancements = [
            {
                "original": "Worked on backend microservices and improved API response times.",
                "optimized": f"Architected high-throughput {job.required_skills[0]} services and distributed vector pipelines, reducing P99 latency by 42% under 50k QPS load.",
                "impact": "Quantifies business metric and highlights target role requirements"
            },
            {
                "original": "Helped deploy applications using Docker and cloud services.",
                "optimized": f"Engineered automated GitOps CI/CD workflows and resilient {job.required_skills[-1]} infrastructure, ensuring 99.99% service availability across multi-region deployments.",
                "impact": "Demonstrates enterprise DevOps rigor and reliability standard"
            }
        ]

        return ResumeTailorResponse(
            ats_compatibility_score=ats_score,
            matched_keywords=matched_kw,
            missing_keywords=missing_kw,
            optimized_summary=opt_summary,
            bullet_point_enhancements=bullet_enhancements
        )

    @staticmethod
    def generate_interview_prep(candidate_id: str, job_id: str) -> InterviewPrepResponse:
        candidate = repo.get_candidate(candidate_id) or repo.get_all_candidates()[0]
        job = repo.get_job(job_id) or repo.get_all_jobs()[0]

        # Determine missing or gap skills
        cand_skills_lower = {s.lower() for s in candidate.skills}
        missing = [s for s in job.required_skills if s.lower() not in cand_skills_lower]

        questions = [
            InterviewQuestion(
                category="System Design & Architecture",
                question=f"How would you design a distributed, low-latency {job.title.split()[-1]} system capable of scaling to 100M daily active requests while maintaining strict consistency?",
                why_asked=f"Assesses architectural depth for {job.company}'s high-throughput infrastructure.",
                expected_answer_points=[
                    "Discuss partitioning strategies (consistent hashing), caching layers (Redis/Memcached), and async queues.",
                    "Tradeoffs between horizontal scaling vs hardware acceleration (GPU/vLLM if AI role).",
                    "Observability, SLOs/SLAs, and automated failover mechanics."
                ]
            ),
            InterviewQuestion(
                category="Core Technical Competency",
                question=f"Explain how you optimize memory allocation and concurrency bottlenecks in {job.required_skills[0]} when handling concurrent async requests.",
                why_asked=f"Verifies hands-on senior mastery of {job.required_skills[0]}.",
                expected_answer_points=[
                    "Connection pooling, event loop non-blocking operations, and profiling memory leaks.",
                    "Garbage collection tuning or lock-free concurrency primitives.",
                    "Real production incident examples where this was debugged."
                ]
            )
        ]

        if missing:
            questions.append(
                InterviewQuestion(
                    category="Targeted Gap Probing",
                    question=f"While your background in {candidate.skills[0]} is stellar, this role heavily leverages {missing[0]}. How have you approached quickly ramping up on or bridging technical gaps in {missing[0]} in past projects?",
                    why_asked=f"Validates learning velocity and adaptability for missing competency: {missing[0]}.",
                    expected_answer_points=[
                        f"Demonstrates mental model transfer from existing skills to {missing[0]}.",
                        "Mentions hands-on POCs, open-source code reading, and rapid production deployment.",
                        "Humility, coachability, and proactive technical curiosity."
                    ]
                )
            )

        questions.append(
            InterviewQuestion(
                category="Behavioral & Engineering Leadership",
                question=f"Tell us about a time you led a high-stakes technical migration with tight deadlines where engineering tradeoffs had to be negotiated with product managers.",
                why_asked="Evaluates seniority, stakeholder management, and technical pragmatism.",
                expected_answer_points=[
                    "STAR method (Situation, Task, Action, Result) with quantified business outcome.",
                    "Clear articulation of why specific technical debt was accepted or avoided.",
                    "Alignment of engineering health with company revenue/delivery goals."
                ]
            )
        )

        return InterviewPrepResponse(
            role_title=job.title,
            candidate_name=candidate.name,
            overall_readiness_score=94 if not missing else 86,
            technical_focus_areas=job.required_skills[:4],
            questions=questions
        )

    @staticmethod
    def generate_job_spec(prompt: str, department: str, workplace_type: str) -> JobSpecGenerateResponse:
        p_lower = prompt.lower()
        
        if "ai" in p_lower or "llm" in p_lower or "machine learning" in p_lower:
            title = "Staff AI Systems & LLM Platform Engineer"
            desc = "Architect high-performance generative AI pipelines, model inference accelerators, and enterprise retrieval engines at scale."
            req = ["Python", "PyTorch", "LLMs & RAG", "CUDA & GPU Optimization", "FastAPI", "Vector Databases"]
            pref = ["Kubernetes", "Docker", "PostgreSQL & pgvector"]
            sal_min, sal_max = 185000, 235000
        elif "frontend" in p_lower or "full stack" in p_lower or "react" in p_lower or "next" in p_lower:
            title = "Principal Full Stack & Web Architecture Engineer"
            desc = "Lead full-stack engineering, interactive design systems, and resilient cloud services trusted by thousands of enterprise clients."
            req = ["TypeScript", "Next.js", "React", "Node.js", "PostgreSQL & pgvector", "AWS"]
            pref = ["Distributed Systems", "Docker", "CI/CD & GitOps"]
            sal_min, sal_max = 175000, 220000
        elif "rust" in p_lower or "go" in p_lower or "backend" in p_lower or "distributed" in p_lower:
            title = "Staff Distributed Systems & Infrastructure Engineer"
            desc = "Engineer high-throughput transactional backends, distributed consensus clusters, and fault-tolerant cloud services."
            req = ["Go", "Rust", "Distributed Systems", "System Design", "Microservices", "PostgreSQL & pgvector"]
            pref = ["Kubernetes", "Docker", "AWS"]
            sal_min, sal_max = 180000, 230000
        else:
            title = "Senior Platform & Cloud Reliability Engineer"
            desc = "Design multi-region cloud infrastructure, automated GitOps deployment pipelines, and zero-trust security architecture."
            req = ["AWS", "Kubernetes", "Terraform", "Docker", "CI/CD & GitOps", "Python"]
            pref = ["Go", "Distributed Systems", "System Design"]
            sal_min, sal_max = 170000, 215000

        return JobSpecGenerateResponse(
            title=title,
            department=department or "Engineering",
            description=desc,
            key_responsibilities=[
                f"Lead architectural design and development of core {req[0]} services.",
                "Collaborate cross-functionally with Product, Design, and Security squads.",
                "Mentor senior engineers and drive engineering excellence and reliability."
            ],
            required_skills=req,
            preferred_skills=pref,
            min_experience_years=5.5,
            salary_min=sal_min,
            salary_max=sal_max,
            equity="0.1% - 0.25%",
            benefits=["100% Remote Flexibility", "Unlimited PTO", "Full Medical/Dental/Vision", "Annual Tech & Home Office Stipend"]
        )

ai_copilot = AICopilotService()
