import redis
from typing import Optional, Any
from core.config import settings

class RedisAdapter:
    """Redis adapter for short-lived session context, working states, and caches."""

    def __init__(self, host: Optional[str] = None, port: Optional[int] = None,
                 password: Optional[str] = None, default_ttl: Optional[int] = None):
        self.host = host or settings.REDIS_HOST
        self.port = port or settings.REDIS_PORT
        self.password = password if password is not None else settings.REDIS_PASSWORD
        self.default_ttl = default_ttl or settings.REDIS_DEFAULT_TTL_SECONDS
        self._client: Optional[redis.Redis] = None

    @property
    def client(self) -> redis.Redis:
        if self._client is None:
            self._client = redis.Redis(
                host=self.host,
                port=self.port,
                password=self.password if self.password else None,
                decode_responses=True
            )
        return self._client

    def ping(self) -> bool:
        try:
            return self.client.ping() is True
        except Exception:
            return False

    def set_with_ttl(self, key: str, value: str, ttl_seconds: Optional[int] = None) -> bool:
        ttl = ttl_seconds if ttl_seconds is not None else self.default_ttl
        return bool(self.client.set(key, value, ex=ttl))

    def get(self, key: str) -> Optional[str]:
        return self.client.get(key)

    def delete(self, key: str) -> bool:
        return bool(self.client.delete(key))

    def get_ttl(self, key: str) -> int:
        return self.client.ttl(key)

    def close(self):
        if self._client is not None:
            self._client.close()
            self._client = None

