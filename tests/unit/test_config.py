import pytest
from core.config import Settings

def test_settings_load_defaults():
    settings = Settings()
    assert settings.POSTGRES_DB == "knowledge_brain"
    assert settings.POSTGRES_USER == "brain_user"
    assert settings.REDIS_PORT == 6379
    assert settings.NEO4J_BOLT_PORT == 7687
    assert settings.EMBEDDING_DIMENSION == 1536
    assert settings.REDIS_DEFAULT_TTL_SECONDS == 3600

