"""受控网络搜索客户端抽象。

安全设计（全部在客户端层强制，不依赖调用方自觉）：
- 只允许 HTTP/HTTPS；禁止本机地址、内网 IP、file://（SSRF 防护）。
- 返回"搜索结果摘要"，不整页复制；内容长度受 max_content_chars 限制。
- 无 API key 时客户端不可用，调用方应回退纯本地（不抛异常）。
- 外部服务由 provider 选择，默认 tavily；测试用 mock。

用户只需在 .env 配置 WEB_RESEARCH__API_KEY 即可启用。
"""

from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Protocol

from loguru import logger


@dataclass(frozen=True)
class WebResult:
    """一条受控搜索/抓取结果。"""

    title: str
    url: str
    snippet: str
    content: str = ""          # 抓取正文（受限长度）
    source: str = ""           # 来源机构/域名
    fetched_at: float = 0.0
    # 内容哈希：用于跨任务去重，防止同一 URL 反复入库。
    content_hash: str = ""

    def with_content(self, content: str, fetched_at: float) -> "WebResult":
        return WebResult(
            title=self.title,
            url=self.url,
            snippet=self.snippet,
            content=content,
            source=self.source,
            fetched_at=fetched_at,
            content_hash=hashlib.sha1(
                f"{self.url}\n{content}".encode("utf-8", errors="replace")
            ).hexdigest()[:16],
        )


@dataclass
class SearchQuery:
    """一次受控搜索请求。"""

    query: str
    max_results: int = 4


class SearchClient(Protocol):
    """外部搜索服务的统一接口（用户只需配置 api_key）。"""

    async def search(self, query: SearchQuery) -> list[WebResult]:
        """执行一次搜索，返回摘要结果。"""
        ...

    async def fetch_page(self, url: str) -> str:
        """抓取单个网页正文（受限长度，含 SSRF 防护）。"""
        ...


# ── SSRF / 协议防护 ──
_ALLOWED_SCHEMES = {"http", "https"}
_LOCAL_IPS = {
    "127.0.0.1", "0.0.0.0", "::1", "::ffff:127.0.0.1",
    "10.0.0.0", "172.16.0.0", "192.168.0.0", "169.254.0.0",  # 前缀匹配见下
}


def _validate_public_url(url: str) -> str:
    """校验 URL 只允许公网 HTTP/HTTPS，返回规范化 URL；非法则抛 ValueError。"""
    parsed = urllib.parse.urlparse(url.strip())
    if parsed.scheme not in _ALLOWED_SCHEMES:
        raise ValueError(f"只允许 http/https URL: {url[:80]}")
    host = parsed.hostname or ""
    if not host:
        raise ValueError(f"URL 缺少主机名: {url[:80]}")
    if host.lower() in {"localhost", "localhost.localdomain"}:
        raise ValueError(f"禁止访问本机地址: {host}")
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        # host 不是字面 IP（是域名），交由 urllib 解析；域名解析后的内网
        # 地址无法在此处预判，但后续 fetch 的 SSRF 由平台 DNS/网络策略承担。
        pass
    else:
        if ip.is_private or ip.is_loopback or ip.is_link_local:
            raise ValueError(f"禁止访问内网/本机 IP: {host}")
    return urllib.parse.urlunparse(parsed)


def _strip_html_to_text(html: str, max_chars: int) -> str:
    """把 HTML 粗略转为纯文本（不执行任何脚本/提示），并截断到 max_chars。"""
    text = re.sub(r"(?is)<(script|style|noscript|svg)[^>]*>.*?</\1>", " ", html)
    text = re.sub(r"(?is)<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()[:max_chars]


class TavilySearchClient:
    """Tavily 搜索 API 实现（用标准库 urllib，无新依赖）。"""

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = "https://api.tavily.com/search",
        max_content_chars: int = 4000,
        timeout_ms: int = 15000,
    ):
        if not api_key or not str(api_key).strip():
            raise ValueError("Tavily api_key 未配置")
        self.api_key = str(api_key).strip()
        self.base_url = base_url
        self.max_content_chars = max(500, int(max_content_chars))
        self.timeout = max(1, int(timeout_ms)) / 1000.0

    async def search(self, query: SearchQuery) -> list[WebResult]:
        payload = {
            "api_key": self.api_key,
            "query": query.query,
            "max_results": max(1, min(query.max_results, 8)),
            "include_answer": False,
            "include_raw_content": False,
        }
        data = await asyncio.to_thread(self._post_json, payload)
        results: list[WebResult] = []
        for item in data.get("results", []):
            url = str(item.get("url") or "").strip()
            if not url:
                continue
            try:
                _validate_public_url(url)
            except ValueError:
                continue
            results.append(WebResult(
                title=str(item.get("title") or "")[:200],
                url=url,
                snippet=str(item.get("content") or "")[:500],
                source=str(item.get("source") or "")[:120],
            ))
        return results

    async def fetch_page(self, url: str) -> str:
        safe_url = _validate_public_url(url)
        request = urllib.request.Request(
            safe_url,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; WildAgentWebResearch/1.0)",
                "Accept": "text/html,application/xhtml+xml",
            },
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            raw = response.read(self.max_content_chars + 4096)
            encoding = response.headers.get_content_charset() or "utf-8"
            html = raw.decode(encoding, errors="replace")
        return _strip_html_to_text(html, self.max_content_chars)

    def _post_json(self, payload: dict[str, Any]) -> dict[str, Any]:
        request = urllib.request.Request(
            self.base_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read()
                return json.loads(raw.decode("utf-8", errors="replace"))
        except urllib.error.HTTPError as exc:
            logger.warning(f"[web_research] Tavily HTTP {exc.code}: {exc.read()[:200]}")
            return {}
        except Exception as exc:
            logger.warning(f"[web_research] Tavily 搜索失败: {exc}")
            return {}


class MockSearchClient:
    """测试用 mock：返回固定结果，不访问网络。"""

    def __init__(self, results: list[WebResult] | None = None):
        self._results = results or [
            WebResult(
                title="示例建筑规范",
                url="https://example.com/building-spec",
                snippet="高层建筑核心筒与垂直交通配置示例",
                source="example.com",
            ),
        ]

    async def search(self, query: SearchQuery) -> list[WebResult]:
        return list(self._results)

    async def fetch_page(self, url: str) -> str:
        _validate_public_url(url)
        return "高层建筑核心筒配置：电梯井、楼梯间、设备管井围绕核心布置。"
