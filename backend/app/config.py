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
    llm_max_attempts: int = 3  # generation attempts before an agent gives up
    llm_log_path: str = "logs/llm_interactions.jsonl"

    # OpenAI Configuration (structured outputs need gpt-4o or newer)
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"
    openai_base_url: str = ""  # optional: any OpenAI-compatible endpoint

    # Anthropic Configuration
    anthropic_api_key: str = ""  # optional: the SDK also reads ANTHROPIC_API_KEY itself
    anthropic_model: str = "claude-opus-5"
    anthropic_effort: str = "high"  # low | medium | high | xhigh | max
    anthropic_refusal_fallback: bool = True  # server-side fallback on refusals

    # Local model Configuration (OpenAI-compatible server, e.g. Ollama)
    local_model: str = "llama3.1"
    local_base_url: str = "http://localhost:11434/v1"
    local_json_mode: bool = True  # many local servers lack strict json_schema support

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
        # .env may live in backend/ or in the repository root (per the README)
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
    )


# Global settings instance
settings = Settings()
