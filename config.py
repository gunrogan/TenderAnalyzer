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

    # API и документация (Swagger/ReDoc)
    api_prefix: str = "/api/v1"
    swagger_enabled: bool = True
    docs_url: str = "/docs"
    redoc_url: str = "/redoc"
    openapi_url: str = "/openapi.json"

    # Celery worker
    # threads-пул безопасен на Windows (prefork использует spawn и ломает
    # fast_trace optimization). tasks используют asyncio.run внутри потока.
    worker_pool: str = "threads"
    worker_concurrency: int = 4

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )


settings = Settings()