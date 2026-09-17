"""Application configuration

Manages environment variables and application settings.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""

    # Database Configuration
    database_url: str = "postgresql://court_user:court_password@localhost:5432/court_simulation"

    # LLM Provider Configuration
    llm_provider: str = "openai"  # openai, anthropic, or local

    # OpenAI Configuration
    openai_api_key: str = ""
    openai_model: str = "gpt-4-turbo-preview"

    # Anthropic Configuration
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-3-5-sonnet-20241022"

    # Application Configuration
    environment: str = "development"
    log_level: str = "INFO"
    debug: bool = True

    # API Configuration
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # Frontend Configuration
    frontend_url: str = "http://localhost:3000"
    cors_origins: List[str] = ["http://localhost:3000"]

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )


# Global settings instance
settings = Settings()
