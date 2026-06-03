from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, Dict

class ItemCreate(BaseModel):
    name: str
    description: Optional[str] = None

class ItemResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}

class HealthResponse(BaseModel):
    status: str
    checks: Dict[str, str]
    timestamp: str
    version: str

class SummarizeRequest(BaseModel):
    text: str = Field(..., min_length=10, max_length=5000, description="The input text to summarize.")

class SummarizeResponse(BaseModel):
    summary: str
    execution_time_ms: float
    cached: bool
    created_at: datetime

    model_config = {"from_attributes": True}