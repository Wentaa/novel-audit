from pydantic_settings import BaseSettings
from typing import Optional
import os
from pathlib import Path


class Settings(BaseSettings):
    """Application configuration settings"""

    # API Configuration
    api_title: str = "Novel Content Audit System"
    api_description: str = "Intelligent content auditing system for novel chapters"
    api_version: str = "1.0.0"
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # OpenAI Configuration
    openai_api_key: str
    openai_model: str = "gpt-4o-mini"
    openai_embedding_model: str = "text-embedding-ada-002"
    openai_max_tokens: int = 4000
    openai_temperature: float = 0.1

    # Claude Configuration
    claude_api_key: str
    claude_model: str = "claude-3-5-sonnet-20241022"
    claude_max_tokens: int = 4000
    claude_temperature: float = 0.1

    # Doubao Configuration  
    doubao_api_key: str
    doubao_model: str = "doubao-pro-4k"
    doubao_max_tokens: int = 4000
    doubao_temperature: float = 0.1

    # ChromaDB Configuration
    chromadb_host: str = "localhost"
    chromadb_port: int = 8001
    chromadb_collection_name: str = "audit_cases"

    # Database Configuration
    database_url: str = "sqlite:///./data/audit_system.db"

    # File Paths
    data_path: Path = Path("./data")
    rules_path: Path = Path("./data/rules")
    cases_path: Path = Path("./data/cases")
    logs_path: Path = Path("./logs")

    # System Configuration
    environment: str = "development"
    log_level: str = "INFO"
    debug: bool = True

    # Audit Configuration
    confidence_threshold_high: float = 0.8
    confidence_threshold_low: float = 0.3
    max_retry_attempts: int = 3

    class Config:
        env_file = ".env"
        case_sensitive = False

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Ensure directories exist
        self.data_path.mkdir(exist_ok=True)
        self.rules_path.mkdir(exist_ok=True)
        self.cases_path.mkdir(exist_ok=True)
        self.logs_path.mkdir(exist_ok=True)


# Global settings instance
settings = Settings()