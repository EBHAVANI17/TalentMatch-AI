"""Shapes the copilot's model calls must return (validated before use)."""
from typing import Any, Dict, List

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ToolCall(BaseModel):
    model_config = ConfigDict(extra="ignore")
    tool: str
    args: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("args", mode="before")
    @classmethod
    def _args(cls, value):
        return value if isinstance(value, dict) else {}


class CopilotPlan(BaseModel):
    model_config = ConfigDict(extra="ignore")
    calls: List[ToolCall] = Field(default_factory=list)


class CopilotAnswer(BaseModel):
    model_config = ConfigDict(extra="ignore")
    answer: str
    cited_refs: List[str] = Field(default_factory=list)
    follow_ups: List[str] = Field(default_factory=list)

    @field_validator("cited_refs", "follow_ups", mode="before")
    @classmethod
    def _strings(cls, value):
        if not isinstance(value, list):
            return []
        return [str(v).strip() for v in value if str(v).strip()]
