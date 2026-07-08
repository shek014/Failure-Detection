"""Application configuration loaded from environment variables."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # LLM (Groq - free tier, get a key at console.groq.com)
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"

    # LangSmith
    langchain_tracing_v2: bool = False
    langchain_api_key: str = ""
    langchain_project: str = "incident-resolution-agent"

    # Database
    database_url: str = "sqlite:///./data/incidents.db"

    # Vector store
    vector_store_dir: str = "./data/vectors"
    chroma_persist_dir: str = "./data/vectors"  # alias for backward compatibility
    embedding_model: str = "all-MiniLM-L6-v2"

    # Monitoring
    prometheus_url: str = "http://localhost:9090"
    metrics_poll_interval_seconds: int = 30
    simulate_metrics: bool = True
    active_scenario: str = "random"

    # Detection thresholds
    cpu_threshold: float = 95.0
    memory_threshold: float = 90.0
    error_rate_threshold: float = 5.0
    latency_threshold_ms: float = 2000.0

    # Human-in-the-loop
    auto_resolve_low_risk: bool = True
    require_approval_high_risk: bool = True

    # App
    log_level: str = "INFO"
    streamlit_port: int = 8501

    @property
    def project_root(self) -> Path:
        return Path(__file__).resolve().parent.parent

    @property
    def data_dir(self) -> Path:
        path = self.project_root / "data"
        path.mkdir(parents=True, exist_ok=True)
        return path


@lru_cache
def get_settings() -> Settings:
    return Settings()
