from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str

    storage_dir: str = "storage"
    max_file_size_mb: int = 25

    redis_url: str = "redis://127.0.0.1:6379/0"

    ollama_url: str = "http://127.0.0.1:11434"
    llm_model: str = "qwen3:8b"
    llm_timeout_seconds: int = 180
    llm_max_chars: int = 60_000

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )


settings = Settings()