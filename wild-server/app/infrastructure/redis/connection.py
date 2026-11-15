"""Redis 仅保存有过期时间的认证会话、验证码和限流状态。"""
from redis import Redis
from redis.asyncio import Redis as AsyncRedis

from config import config


class Cache:
    def __init__(self):
        self._client: Redis | None = None
        self._async_client: AsyncRedis | None = None

    @property
    def client(self) -> Redis:
        if self._client is None:
            cfg = config.redis
            self._client = Redis(host=cfg.host, port=cfg.port, db=cfg.database,
                                 username=cfg.username or None,
                                 password=cfg.password.get_secret_value() or None,
                                 ssl=cfg.ssl, decode_responses=True,
                                 socket_connect_timeout=5, socket_timeout=5,
                                 max_connections=50)
        return self._client

    def key(self, name: str) -> str:
        return config.redis.key_prefix + name

    @property
    def async_client(self) -> AsyncRedis:
        if self._async_client is None:
            self._async_client = self.create_async_client()
        return self._async_client

    def create_async_client(self, *, socket_timeout: float | None = 5) -> AsyncRedis:
        cfg = config.redis
        return AsyncRedis(host=cfg.host, port=cfg.port, db=cfg.database,
            username=cfg.username or None, password=cfg.password.get_secret_value() or None,
            ssl=cfg.ssl, decode_responses=True, socket_connect_timeout=5,
            socket_timeout=socket_timeout, max_connections=50, health_check_interval=15)

    async def aclose(self) -> None:
        if self._async_client is not None:
            await self._async_client.aclose()
            self._async_client = None

    def check(self) -> None:
        self.client.ping()

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None


cache = Cache()
