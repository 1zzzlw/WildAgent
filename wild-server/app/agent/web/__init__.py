"""受控网络研究客户端：搜索 + 网页抓取的安全封装。"""

from app.agent.web.search_client import (
    MockSearchClient,
    SearchClient,
    SearchQuery,
    TavilySearchClient,
    WebResult,
    _validate_public_url,
)


def create_search_client(
    *,
    enabled: bool = False,
    provider: str = "tavily",
    api_key: str = "",
    base_url: str = "https://api.tavily.com/search",
    max_content_chars: int = 4000,
    timeout_ms: int = 15000,
) -> SearchClient | None:
    """按配置创建搜索客户端；未启用或缺 key 时返回 None（调用方回退纯本地）。

    用户只需在 .env 配置 WEB_RESEARCH__API_KEY 即可启用。
    """
    if not enabled or not api_key:
        return None
    try:
        if provider == "tavily":
            return TavilySearchClient(
                api_key,
                base_url=base_url,
                max_content_chars=max_content_chars,
                timeout_ms=timeout_ms,
            )
        return None
    except ValueError as exc:
        return None


__all__ = [
    "MockSearchClient",
    "SearchClient",
    "SearchQuery",
    "TavilySearchClient",
    "WebResult",
    "create_search_client",
    "_validate_public_url",
]
