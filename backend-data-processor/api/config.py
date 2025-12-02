"""
Configuration management for the API service.
Supports both local development and cloud deployment.
"""
from pydantic_settings import BaseSettings
from typing import Literal


class Settings(BaseSettings):
    """Application settings with environment variable support."""
    
    # Application
    app_name: str = "Data Processor API"
    app_version: str = "1.0.0"
    environment: Literal["local", "development", "production"] = "local"
    
    # API Configuration
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_workers: int = 4
    max_request_size: int = 10 * 1024 * 1024  # 10MB
    
    # Message Queue (Local: Redis, Cloud: Pub/Sub)
    queue_type: Literal["redis", "pubsub"] = "redis"
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    redis_queue_name: str = "log-ingestion"
    
    # GCP Pub/Sub (for cloud deployment)
    gcp_project_id: str = ""
    pubsub_topic: str = "log-ingestion"
    
    # Database (Local: SQLite/Emulator, Cloud: Firestore)
    database_type: Literal["emulator", "firestore", "sqlite"] = "sqlite"
    firestore_emulator_host: str = "localhost:8080"
    sqlite_db_path: str = "/app/data/logs.db"
    
    # Processing
    enable_pii_redaction: bool = True
    processing_time_per_char: float = 0.05  # seconds
    
    # Logging
    log_level: str = "INFO"
    log_format: str = "json"
    
    class Config:
        env_file = ".env"
        case_sensitive = False


# Global settings instance
settings = Settings()