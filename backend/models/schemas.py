from enum import StrEnum

from pydantic import BaseModel, Field


class JobStatus(StrEnum):
    CREATED = "CREATED"
    ANALYZING = "ANALYZING"
    EXTRACTING_AUDIO = "EXTRACTING_AUDIO"
    CHUNKING = "CHUNKING"
    TRANSCRIBING = "TRANSCRIBING"
    MERGING = "MERGING"
    EXPORTING = "EXPORTING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class StartJobRequest(BaseModel):
    language: str = Field(default="auto", pattern="^(auto|en|hi|hi-en)$")
    quality: str = Field(default="auto", pattern="^(auto|accurate|fast)$")


class RetryRequest(BaseModel):
    chunk_id: int | None = None
