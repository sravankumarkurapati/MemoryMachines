"""
Configuration for the worker service.
Inherits from API config but can have worker-specific overrides.
"""
from pydantic_settings import BaseSettings
from typing import Literal


class Settings(BaseSettings):
    """Worker-specific settings."""
    
    # Application
    app_name: str = "Log Processor Worker"
    environment: Literal["local", "development", "production"] = "local"
    
    # Message Queue
    queue_type: Literal["redis", "pubsub"] = "redis"
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    redis_queue_name: str = "log-ingestion"
    
    # GCP Pub/Sub
    gcp_project_id: str = ""
    pubsub_topic: str = "log-ingestion"
    pubsub_subscription: str = "log-processing-worker"
    
    # Database
    database_type: Literal["emulator", "firestore", "sqlite"] = "sqlite"
    firestore_emulator_host: str = "localhost:8080"
    sqlite_db_path: str = "/app/data/logs.db"
    
    # Processing
    enable_pii_redaction: bool = True
    processing_time_per_char: float = 0.05
    max_concurrent_messages: int = 10
    
    # Retry configuration
    max_retries: int = 3
    retry_delay_seconds: int = 5
    
    # Logging
    log_level: str = "INFO"
    
    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()