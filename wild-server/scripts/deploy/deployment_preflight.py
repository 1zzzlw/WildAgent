"""生产部署前检查；默认离线，可显式启用真实供应商连通性冒烟。"""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import yaml

MODEL_SMOKE_MAX_TOKENS = 128


def _get_config():
    from config import config

    return config


def validate_knowledge_documents(kb_root: Path) -> tuple[list[Path], list[str]]:
    """按知识库清单验证镜像内容，返回实际 Markdown 和必需相对路径。"""
    config_path = kb_root / "config.yaml"
    assert config_path.is_file(), "knowledge base config missing from image"
    loaded: Any = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    required = loaded.get("required_documents") if isinstance(loaded, dict) else None
    assert isinstance(required, list) and required, (
        "knowledge base required_documents manifest is empty"
    )
    required_paths = [str(item).strip() for item in required]
    assert all(path and path.endswith(".md") for path in required_paths), (
        "knowledge base manifest contains an invalid document path"
    )
    assert all(
        not Path(path).is_absolute() and ".." not in Path(path).parts
        for path in required_paths
    ), "knowledge base manifest paths must stay inside the knowledge root"
    assert len(required_paths) == len(set(required_paths)), (
        "knowledge base manifest contains duplicate document paths"
    )
    missing = [path for path in required_paths if not (kb_root / path).is_file()]
    assert not missing, "required knowledge documents missing: " + ", ".join(missing)
    return sorted(kb_root.rglob("*.md")), required_paths


def select_smoke_response_text(response: object) -> tuple[str, str]:
    """选择可证明模型已响应的文本，并返回来源标签。"""
    from app.agent.model_client import message_texts

    content, reasoning = message_texts(response)
    if content.strip():
        return content, "content"
    if reasoning.strip():
        return reasoning, "reasoning_content"

    metadata = getattr(response, "response_metadata", {})
    finish_reason = metadata.get("finish_reason") if isinstance(metadata, dict) else None
    raise AssertionError(
        "model returned no text in content or reasoning_content"
        + (f" (finish_reason={finish_reason})" if finish_reason else "")
    )


def validate_image_and_config(*, require_provider_credentials: bool) -> None:
    """检查镜像内置资源；仅在真实冒烟模式下要求供应商凭据。"""
    config = _get_config()
    kb_root = Path("storage/knowledge_base")
    kb_files, required_paths = validate_knowledge_documents(kb_root)
    if require_provider_credentials:
        assert config.chat.name.strip(), "CHAT__NAME missing"
        assert config.chat.api_key.strip(), "CHAT__API_KEY missing"
        embedding_required = config.rag.enabled
        assert (not embedding_required) or (
            config.embedding.name.strip() and config.embedding.api_key.strip()
        ), "EMBEDDING config missing for live provider preflight"

    print(
        f"knowledge_base_files={len(kb_files)} "
        f"required_documents={len(required_paths)}"
    )
    print(f"preflight_model={config.chat.name}")
    print(f"preflight_base_url={config.chat.base_url or '(default)'}")
    print(f"preflight_rag_enabled={str(config.rag.enabled).lower()}")
    print(f"preflight_embedding={config.embedding.name}")


def run_model_smoke() -> None:
    from app.agent.model_client import create_llm

    response = create_llm().bind(max_tokens=MODEL_SMOKE_MAX_TOKENS).invoke(
        "Reply with WILD_OK only."
    )
    text, source = select_smoke_response_text(response)
    metadata = getattr(response, "response_metadata", {})
    finish_reason = metadata.get("finish_reason") if isinstance(metadata, dict) else None
    print(
        f"model_smoke=ok source={source} response_chars={len(text)}"
        + (f" finish_reason={finish_reason}" if finish_reason else "")
    )


def run_embedding_smoke() -> None:
    from app.spec.loader import create_embedding_function

    config = _get_config()
    if not config.rag.enabled:
        print("embedding_smoke=skipped")
        return
    embedding = create_embedding_function(
        config.embedding.api_key,
        config.embedding.base_url,
        config.embedding.name,
        config.rag.allow_hash_fallback,
    )
    vector = embedding.embed_query("WildAgent deployment smoke")
    assert vector and isinstance(vector[0], (int, float)), (
        "embedding returned invalid vector"
    )
    print(f"embedding_smoke=ok dimensions={len(vector)}")


def run_preflight(*, live_providers: bool = False) -> None:
    """执行部署预检；默认不向 Chat/Embedding 供应商发出网络请求。"""
    validate_image_and_config(require_provider_credentials=live_providers)
    print(f"preflight_mode={'live_providers' if live_providers else 'offline'}")
    if not live_providers:
        print("model_smoke=skipped reason=live_provider_preflight_disabled")
        print("embedding_smoke=skipped reason=live_provider_preflight_disabled")
        return

    run_model_smoke()
    run_embedding_smoke()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--live-providers",
        action="store_true",
        help="向真实 Chat 和 Embedding 服务发送最小请求；可能消耗额度",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_preflight(live_providers=args.live_providers)


if __name__ == "__main__":
    main()
