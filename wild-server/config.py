from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import AliasChoices

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    model_name: str = Field(
        default="qwen3.5-plus",
        validation_alias=AliasChoices("model_name", "DASHSCOPE_MODEL_NAME"),
    )
    model_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("model_api_key", "DASHSCOPE_API_KEY"),
    )
    model_base_url: str = Field(
        default="",
        validation_alias=AliasChoices("model_base_url", "DASHSCOPE_BASE_URL"),
    )

config = Settings()