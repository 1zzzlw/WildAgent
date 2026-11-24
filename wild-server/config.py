"""编辑器的存储、缓存、邮件与资产配置。"""

from typing import Literal

from pydantic import BaseModel, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from common.configuration import runtime_env_path


class AssetConfig(BaseModel):
    """PBR 资产本地入库与公开地址配置。"""

    backend: str = "local"
    root_dir: str = "storage/assets"
    public_base_url: str = "/api/assets"
    max_file_bytes: int = 20 * 1024 * 1024
    max_total_bytes: int = 80 * 1024 * 1024


class MySQLConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = Field(default=3306, ge=1, le=65535)
    database: str = "wild_agent"
    username: str = "wild_agent"
    password: SecretStr = SecretStr("")
    pool_size: int = Field(default=10, ge=1, le=100)
    connect_timeout: int = Field(default=5, ge=1, le=60)


class RedisConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = Field(default=6379, ge=1, le=65535)
    database: int = Field(default=0, ge=0)
    username: str = ""
    password: SecretStr = SecretStr("")
    ssl: bool = False
    key_prefix: str = "wild:"
    session_seconds: int = Field(default=43200, ge=60)


class SMTPConfig(BaseModel):
    host: str = ""
    port: int = Field(default=465, ge=1, le=65535)
    username: str = ""
    password: SecretStr = SecretStr("")
    from_address: str = ""
    security: Literal["ssl", "starttls", "plain"] = "ssl"
    code_seconds: int = Field(default=600, ge=60, le=1800)
    resend_seconds: int = Field(default=60, ge=30, le=600)


class Settings(BaseSettings):
    """编辑器配置对象。"""

    # Pydantic Settings 会先读环境变量，再读取固定的运行时配置文件；默认位于
    # wild-server/.env，容器可用 WILD_RUNTIME_ENV_FILE 指向宿主机挂载文件。
    model_config = SettingsConfigDict(
        env_file=str(runtime_env_path()),
        env_file_encoding="utf-8",
        # 例如 MYSQL__PORT=3306 会映射到 mysql.port。
        env_nested_delimiter="__",
        # 忽略暂未被代码消费的环境变量，便于前后端共用同一份环境文件。
        extra="ignore",
    )

    # default_factory 确保每个 Settings 实例拥有独立的嵌套配置对象。
    assets: AssetConfig = Field(default_factory=AssetConfig)
    mysql: MySQLConfig = Field(default_factory=MySQLConfig)
    redis: RedisConfig = Field(default_factory=RedisConfig)
    smtp: SMTPConfig = Field(default_factory=SMTPConfig)


# 导入 config.py 时完成一次解析；业务模块不应在运行中修改这个对象。
config = Settings()
