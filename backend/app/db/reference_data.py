"""Platform reference data loaded in every environment (not only demo mode).

ensure_reference_data() is idempotent: it only inserts what is missing, so admin
edits made later are never overwritten.
"""
import uuid
from typing import Dict, List, Tuple

from sqlalchemy.orm import Session

from app.models.db_models import SkillAlias, SkillRelation, SkillTaxonomy

# name -> (category, aliases)
SKILLS: Dict[str, Tuple[str, List[str]]] = {
    # Languages
    "Python": ("Languages", ["py", "python3"]),
    "JavaScript": ("Languages", ["js", "ecmascript", "es6"]),
    "TypeScript": ("Languages", ["ts"]),
    "Java": ("Languages", []),
    "C#": ("Languages", ["csharp", "c sharp"]),
    "Go": ("Languages", ["golang"]),
    "Rust": ("Languages", []),
    "C++": ("Languages", ["cpp"]),
    "Kotlin": ("Languages", []),
    "Swift": ("Languages", []),
    "Ruby": ("Languages", []),
    "PHP": ("Languages", []),
    "Scala": ("Languages", []),
    "SQL": ("Languages", ["structured query language"]),
    # Frontend
    "React": ("Frontend", ["reactjs", "react.js"]),
    "Next.js": ("Frontend", ["nextjs", "next"]),
    "Vue.js": ("Frontend", ["vue", "vuejs"]),
    "Angular": ("Frontend", ["angularjs"]),
    "HTML": ("Frontend", ["html5"]),
    "CSS": ("Frontend", ["css3"]),
    "Tailwind CSS": ("Frontend", ["tailwind", "tailwindcss"]),
    # Backend
    "Node.js": ("Backend", ["node", "nodejs"]),
    "Express": ("Backend", ["express.js", "expressjs"]),
    "Django": ("Backend", []),
    "FastAPI": ("Backend", []),
    "Flask": ("Backend", []),
    "Spring Boot": ("Backend", ["spring", "springboot"]),
    ".NET": ("Backend", ["dotnet", "asp.net"]),
    "Ruby on Rails": ("Backend", ["rails", "ror"]),
    "GraphQL": ("Backend", []),
    "REST APIs": ("Backend", ["rest", "restful apis", "rest api"]),
    "Microservices": ("Architecture", ["microservice architecture"]),
    "Distributed Systems": ("Architecture", []),
    "System Design": ("Architecture", []),
    # Data
    "PostgreSQL": ("Data", ["postgres", "psql"]),
    "MySQL": ("Data", []),
    "MongoDB": ("Data", ["mongo"]),
    "Redis": ("Data", []),
    "Kafka": ("Data", ["apache kafka"]),
    "Spark": ("Data", ["apache spark", "pyspark"]),
    "Elasticsearch": ("Data", ["elastic", "opensearch"]),
    "Snowflake": ("Data", []),
    "Airflow": ("Data", ["apache airflow"]),
    "dbt": ("Data", []),
    "Pandas": ("Data", []),
    "Data Engineering": ("Data", ["etl", "data pipelines"]),
    "pgvector": ("Data", []),
    "Vector Databases": ("Data", ["vector db", "vector database"]),
    # Cloud & DevOps
    "AWS": ("Cloud & DevOps", ["amazon web services"]),
    "Azure": ("Cloud & DevOps", ["microsoft azure"]),
    "GCP": ("Cloud & DevOps", ["google cloud", "google cloud platform"]),
    "Docker": ("Cloud & DevOps", ["containers"]),
    "Kubernetes": ("Cloud & DevOps", ["k8s", "container orchestration"]),
    "Helm": ("Cloud & DevOps", []),
    "Terraform": ("Cloud & DevOps", ["infrastructure as code", "iac"]),
    "Ansible": ("Cloud & DevOps", []),
    "CI/CD": ("Cloud & DevOps", ["cicd", "continuous integration", "continuous delivery"]),
    "Linux": ("Cloud & DevOps", []),
    "Prometheus": ("Cloud & DevOps", []),
    "DevOps": ("Cloud & DevOps", []),
    "Site Reliability Engineering": ("Cloud & DevOps", ["sre"]),
    # AI / ML
    "Machine Learning": ("AI/ML", ["ml"]),
    "Deep Learning": ("AI/ML", ["dl"]),
    "PyTorch": ("AI/ML", ["torch"]),
    "TensorFlow": ("AI/ML", ["tf"]),
    "NLP": ("AI/ML", ["natural language processing"]),
    "Computer Vision": ("AI/ML", []),
    "LLMs": ("AI/ML", ["llm", "large language models", "generative ai", "genai"]),
    "RAG": ("AI/ML", ["retrieval augmented generation", "retrieval-augmented generation"]),
    "scikit-learn": ("AI/ML", ["sklearn"]),
    "MLOps": ("AI/ML", []),
    # Design & product
    "Figma": ("Design", []),
    "UI Design": ("Design", ["user interface design"]),
    "UX Research": ("Design", ["user research"]),
    "Product Management": ("Product", ["product manager"]),
    # Business
    "Salesforce": ("Sales", ["sfdc"]),
    "Sales": ("Sales", ["b2b sales"]),
    "Financial Modeling": ("Finance", ["financial modelling"]),
    "Excel": ("Finance", ["microsoft excel"]),
    "Accounting": ("Finance", []),
}

# (has, wanted, weight when the candidate HAS the first and the job WANTS the second, reverse weight, kind)
RELATIONS: List[Tuple[str, str, float, float, str]] = [
    ("TypeScript", "JavaScript", 0.9, 0.5, "parent"),
    ("React", "JavaScript", 0.6, 0.2, "parent"),
    ("Next.js", "React", 0.9, 0.4, "parent"),
    ("Vue.js", "JavaScript", 0.6, 0.2, "parent"),
    ("Angular", "TypeScript", 0.6, 0.2, "parent"),
    ("Vue.js", "React", 0.5, 0.5, "transferable"),
    ("Angular", "React", 0.4, 0.4, "transferable"),
    ("Node.js", "JavaScript", 0.7, 0.3, "parent"),
    ("Express", "Node.js", 0.8, 0.5, "parent"),
    ("Tailwind CSS", "CSS", 0.8, 0.3, "parent"),
    ("HTML", "CSS", 0.5, 0.5, "related"),
    ("Django", "Python", 0.8, 0.3, "parent"),
    ("FastAPI", "Python", 0.8, 0.3, "parent"),
    ("Flask", "Python", 0.8, 0.3, "parent"),
    ("FastAPI", "Flask", 0.6, 0.6, "transferable"),
    ("Django", "Flask", 0.5, 0.5, "transferable"),
    ("Pandas", "Python", 0.7, 0.2, "parent"),
    ("Spring Boot", "Java", 0.8, 0.3, "parent"),
    (".NET", "C#", 0.8, 0.4, "parent"),
    ("Ruby on Rails", "Ruby", 0.8, 0.4, "parent"),
    ("Java", "C#", 0.6, 0.6, "transferable"),
    ("Java", "Kotlin", 0.6, 0.7, "transferable"),
    ("C++", "Rust", 0.4, 0.5, "transferable"),
    ("Go", "Rust", 0.3, 0.3, "transferable"),
    ("PostgreSQL", "SQL", 0.9, 0.5, "parent"),
    ("MySQL", "SQL", 0.9, 0.5, "parent"),
    ("PostgreSQL", "MySQL", 0.7, 0.7, "transferable"),
    ("pgvector", "PostgreSQL", 0.6, 0.2, "parent"),
    ("pgvector", "Vector Databases", 0.8, 0.4, "parent"),
    ("Elasticsearch", "Vector Databases", 0.3, 0.3, "related"),
    ("Kafka", "Distributed Systems", 0.4, 0.3, "related"),
    ("Microservices", "Distributed Systems", 0.6, 0.6, "related"),
    ("Distributed Systems", "System Design", 0.6, 0.6, "related"),
    ("Spark", "Data Engineering", 0.6, 0.4, "related"),
    ("Airflow", "Data Engineering", 0.6, 0.4, "related"),
    ("dbt", "Data Engineering", 0.6, 0.3, "related"),
    ("Snowflake", "SQL", 0.6, 0.2, "related"),
    ("Docker", "Kubernetes", 0.5, 0.7, "related"),
    ("Helm", "Kubernetes", 0.8, 0.4, "parent"),
    ("AWS", "Azure", 0.5, 0.5, "transferable"),
    ("AWS", "GCP", 0.5, 0.5, "transferable"),
    ("Azure", "GCP", 0.5, 0.5, "transferable"),
    ("Terraform", "Ansible", 0.4, 0.4, "related"),
    ("Kubernetes", "DevOps", 0.5, 0.4, "related"),
    ("CI/CD", "DevOps", 0.6, 0.5, "related"),
    ("Site Reliability Engineering", "DevOps", 0.7, 0.6, "related"),
    ("Prometheus", "Site Reliability Engineering", 0.4, 0.3, "related"),
    ("Linux", "DevOps", 0.4, 0.3, "related"),
    ("Deep Learning", "Machine Learning", 0.8, 0.5, "parent"),
    ("PyTorch", "Deep Learning", 0.7, 0.4, "parent"),
    ("TensorFlow", "Deep Learning", 0.7, 0.4, "parent"),
    ("PyTorch", "TensorFlow", 0.7, 0.7, "transferable"),
    ("scikit-learn", "Machine Learning", 0.7, 0.4, "parent"),
    ("LLMs", "NLP", 0.7, 0.5, "related"),
    ("RAG", "LLMs", 0.8, 0.5, "parent"),
    ("RAG", "Vector Databases", 0.5, 0.4, "related"),
    ("MLOps", "Machine Learning", 0.5, 0.3, "related"),
    ("Figma", "UI Design", 0.6, 0.6, "related"),
    ("UX Research", "UI Design", 0.4, 0.4, "related"),
    ("Salesforce", "Sales", 0.5, 0.3, "related"),
    ("Excel", "Financial Modeling", 0.4, 0.3, "related"),
]


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def ensure_skill_ontology(db: Session) -> None:
    by_name = {s.name.lower(): s for s in db.query(SkillTaxonomy).all()}
    for name, (category, _) in SKILLS.items():
        if name.lower() not in by_name:
            skill = SkillTaxonomy(id=_new_id("tax"), name=name, category=category, demand_level="", avg_salary_boost="")
            db.add(skill)
            by_name[name.lower()] = skill
    db.flush()

    taken = {a for (a,) in db.query(SkillAlias.alias)}
    for name, (_, aliases) in SKILLS.items():
        for alias in aliases:
            alias = alias.lower()
            if alias not in taken and alias not in by_name:
                db.add(SkillAlias(id=_new_id("alias"), skill_id=by_name[name.lower()].id, alias=alias))
                taken.add(alias)

    existing = {(r.skill_id, r.related_skill_id) for r in db.query(SkillRelation).all()}
    for has, wanted, forward, reverse, kind in RELATIONS:
        a, b = by_name[has.lower()].id, by_name[wanted.lower()].id
        for src, dst, weight in ((a, b, forward), (b, a, reverse)):
            if (src, dst) not in existing and weight > 0:
                db.add(SkillRelation(id=_new_id("rel"), skill_id=src, related_skill_id=dst, kind=kind, weight=weight))
                existing.add((src, dst))
    db.commit()


def ensure_reference_data(db: Session) -> None:
    from app.ai.prompts import ensure_default_prompts

    ensure_skill_ontology(db)
    ensure_default_prompts(db)
