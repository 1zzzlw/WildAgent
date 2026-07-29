from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ModelConfig(BaseModel):
    """单个模型的配置"""
    name: str = "qwen-plus"
    api_key: str = ""
    base_url: str = ""


class RAGConfig(BaseModel):
    """RAG 检索配置"""
    enabled: bool = True
    persist_dir: str = "storage/chroma"
    collection_name: str = "wild_knowledge_base"
    chunk_size: int = 900
    chunk_overlap: int = 150
    top_k: int = 6
    max_context_chars: int = 18000
    allow_hash_fallback: bool = True


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
    )

    chat: ModelConfig = Field(default_factory=ModelConfig)
    embedding: ModelConfig = Field(default_factory=ModelConfig)
    rerank: ModelConfig = Field(default_factory=ModelConfig)
    rag: RAGConfig = Field(default_factory=RAGConfig)


config = Settings()
