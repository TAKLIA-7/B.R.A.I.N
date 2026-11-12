from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

class Settings(BaseSettings):
    # PostgreSQL + pgvector
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "knowledge_brain"
    POSTGRES_USER: str = "brain_user"
    POSTGRES_PASSWORD: str = "brain_password"

    # Redis
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: Optional[str] = None
    REDIS_DEFAULT_TTL_SECONDS: int = 3600

    # Neo4j
    NEO4J_HOST: str = "localhost"
    NEO4J_BOLT_PORT: int = 7687
    NEO4J_HTTP_PORT: int = 7474
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = "brain_graph_password"

    # Extraction LLM Provider
    EXTRACTION_LLM_PROVIDER: str = "gemini"  # "gemini" | "mock"
    GEMINI_API_KEY: Optional[str] = None
    GEMINI_MODEL: str = "gemini-2.5-flash"

    # Vector Embeddings
    EMBEDDING_PROVIDER: str = "openai"  # "openai" | "local" | "mock"
    OPENAI_API_KEY: Optional[str] = None
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    EMBEDDING_DIMENSION: int = 1536  # 1536 for text-embedding-3-small, 384 for all-MiniLM-L6-v2

    # Application Environment
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"

    # Obsidian Vault (Optional human-facing Markdown projection)
    OBSIDIAN_VAULT_PATH: Optional[str] = "obsidian_vault"

    @property
    def postgres_uri(self) -> str:
        return f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    @property
    def postgres_async_uri(self) -> str:
        return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    @property
    def neo4j_bolt_uri(self) -> str:
        return f"bolt://{self.NEO4J_HOST}:{self.NEO4J_BOLT_PORT}"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()
