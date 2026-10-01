import os
from pydantic import BaseModel

class MatchingWeights(BaseModel):
    skills_weight: float = 0.45
    experience_weight: float = 0.25
    location_weight: float = 0.15
    salary_weight: float = 0.10
    education_weight: float = 0.05

class Settings(BaseModel):
    app_name: str = "TalentMatch AI Enterprise"
    app_version: str = "2.0.0"
    api_prefix: str = "/api/v1"
    host: str = "0.0.0.0"
    port: int = int(os.getenv("PORT", "8000"))
    weights: MatchingWeights = MatchingWeights()

settings = Settings()
