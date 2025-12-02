"""
Data models and schemas for API requests and internal processing.
"""
from pydantic import BaseModel, Field, validator
from typing import Optional, Literal
from datetime import datetime
import uuid


class JSONLogPayload(BaseModel):
    """Schema for JSON log ingestion."""
    tenant_id: str = Field(..., min_length=1, max_length=100)
    log_id: str = Field(..., min_length=1, max_length=100)
    text: str = Field(..., min_length=1)
    
    @validator('tenant_id', 'log_id')
    def validate_alphanumeric(cls, v):
        """Ensure tenant_id and log_id are safe for use in paths."""
        if not v.replace('_', '').replace('-', '').isalnum():
            raise ValueError('Must contain only alphanumeric characters, hyphens, and underscores')
        return v


class IngestResponse(BaseModel):
    """Response model for successful ingestion."""
    status: str = "accepted"
    message: str = "Log queued for processing"
    log_id: str
    tenant_id: str
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))


class ErrorResponse(BaseModel):
    """Error response model."""
    status: str = "error"
    message: str
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))


class NormalizedMessage(BaseModel):
    """Internal normalized message format for queue."""
    tenant_id: str
    log_id: str
    text: str
    source: Literal["json", "text"]
    ingested_at: datetime = Field(default_factory=datetime.utcnow)
    request_id: str
    
    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "tenant_id": self.tenant_id,
            "log_id": self.log_id,
            "text": self.text,
            "source": self.source,
            "ingested_at": self.ingested_at.isoformat(),
            "request_id": self.request_id
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "NormalizedMessage":
        """Create from dictionary (deserialization)."""
        data["ingested_at"] = datetime.fromisoformat(data["ingested_at"])
        return cls(**data)


class ProcessedLog(BaseModel):
    """Schema for processed log stored in database."""
    log_id: str
    tenant_id: str
    source: Literal["json_upload", "text_upload"]
    original_text: str
    modified_data: str
    ingested_at: datetime
    processed_at: datetime
    processing_time_seconds: float
    character_count: int
    request_id: str
    
    def to_firestore_dict(self) -> dict:
        """Convert to Firestore-compatible dictionary."""
        return {
            "log_id": self.log_id,
            "source": self.source,
            "original_text": self.original_text,
            "modified_data": self.modified_data,
            "ingested_at": self.ingested_at.isoformat(),
            "processed_at": self.processed_at.isoformat(),
            "processing_time_seconds": self.processing_time_seconds,
            "character_count": self.character_count,
            "request_id": self.request_id
        }