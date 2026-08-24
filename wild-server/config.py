"""从环境变量和 ``.env`` 文件加载后端配置。

嵌套配置使用双下划线分隔，例如 ``CHAT__API_KEY`` 会写入
``Settings.chat.api_key``。模块末尾创建一次全局 ``config``，其他模块只读取它，
从而保证一次进程中的配置视图一致。
"""

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ModelConfig(BaseModel):
    """一项 OpenAI-compatible 模型服务的连接参数。"""

    # 模型名会原样传给兼容服务，例如 qwen-plus 或某个 embedding 模型名。
    name: str = "qwen-plus"
    # 密钥默认留空，实际值应通过环境变量提供，避免写入代码仓库。
    api_key: str = ""
    # 自建或第三方兼容服务填写 base_url；空值表示使用客户端默认地址。
    base_url: str = ""


class RetrievalGateConfig(BaseModel):
    """向量召回门控；observe 只记结论，enforce 才影响运行时行为。"""

    mode: str = "observe"
    # Chroma distance 越小越相关；必须用当前 embedding 的正负样本校准后配置。
    max_distance: float | None = None
    min_hits: int = 1
    refusal_message: str = "知识库中暂无足够可靠的相关信息。"


class RAGTraceConfig(BaseModel):
    """RAG 请求追踪文件设置。"""

    enabled: bool = True
    root_dir: str = "storage/sessions/rag_traces"
    query_preview_chars: int = 300
    answer_preview_chars: int = 10000


class RAGSecurityConfig(BaseModel):
    """服务端身份头、PII 与基础内容安全设置。"""

    # 只有反向代理同时提供正确共享密钥时，身份头才会被视为可信。
    trusted_header_secret: str = ""
    pii_redaction_enabled: bool = True
    content_safety_enabled: bool = True


class RAGConfig(BaseModel):
    """Chroma 知识库的分片、召回和持久化参数。"""

    # 关闭后不创建向量索引，AgentService 会退回基础规范文件加载器。
    enabled: bool = True
    # 相对路径会由 AgentService 解析到 wild-server 根目录下。
    persist_dir: str = "storage/chroma"
    collection_name: str = "wild_knowledge_base"
    # chunk_overlap 必须小于 chunk_size；Loader 内还会对异常值做边界收敛。
    chunk_size: int = 900
    chunk_overlap: int = 150
    # 单查询最终保留的唯一分片数；Loader 会多召回一些再按内容哈希去重。
    top_k: int = 6
    # 基础规范与 RAG 片段拼接后的最大字符数，防止 System Prompt 无限增长。
    max_context_chars: int = 18000
    # 没配置远程 embedding 时允许使用本地 hash 向量，仅适合开发 smoke test。
    allow_hash_fallback: bool = True
    retrieval_gate: RetrievalGateConfig = Field(default_factory=RetrievalGateConfig)
    trace: RAGTraceConfig = Field(default_factory=RAGTraceConfig)
    security: RAGSecurityConfig = Field(default_factory=RAGSecurityConfig)


class AssetConfig(BaseModel):
    """PBR 资产本地入库与公开地址配置。"""

    backend: str = "local"
    root_dir: str = "storage/assets"
    public_base_url: str = "/api/assets"
    max_file_bytes: int = 20 * 1024 * 1024
    max_total_bytes: int = 80 * 1024 * 1024


class Settings(BaseSettings):
    """整个后端进程使用的顶层配置对象。"""

    # Pydantic Settings 会先读环境变量，再按配置读取当前工作目录中的 .env。
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        # 例如 RAG__TOP_K=8 会映射到 rag.top_k。
        env_nested_delimiter="__",
        # 忽略暂未被代码消费的环境变量，便于前后端共用同一份环境文件。
        extra="ignore",
    )

    # default_factory 确保每个 Settings 实例拥有独立的嵌套配置对象。
    chat: ModelConfig = Field(default_factory=ModelConfig)
    embedding: ModelConfig = Field(default_factory=ModelConfig)
    rerank: ModelConfig = Field(default_factory=ModelConfig)
    rag: RAGConfig = Field(default_factory=RAGConfig)
    assets: AssetConfig = Field(default_factory=AssetConfig)


# 导入 config.py 时完成一次解析；业务模块不应在运行中修改这个对象。
config = Settings()
