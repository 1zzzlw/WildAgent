"""供应商地址与连接解析；显式选择优先，auto 保留旧配置兼容。"""
from urllib.parse import urlparse

BASE_URL = {
    "openai": "https://api.openai.com/v1",
    "dashscope": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "deepseek": "https://api.deepseek.com/v1",
    "moonshot": "https://api.moonshot.cn/v1",
    "mimo": "https://api.xiaomimimo.com/v1",
}


def resolve_connection(model_cfg):
    provider = model_cfg.provider
    base_url = model_cfg.base_url.strip()
    if provider == "auto":
        host = (urlparse(base_url).hostname or "").casefold()
        if host == "xiaomimimo.com" or host.endswith(".xiaomimimo.com"):
            provider = "mimo"
        elif host.endswith(".aliyuncs.com") and (host.startswith("dashscope") or ".maas.aliyuncs.com" in host):
            provider = "dashscope"
        elif host == "api.deepseek.com" or host.endswith(".deepseek.com"):
            provider = "deepseek"
        elif host in {"api.moonshot.ai", "api.moonshot.cn", "api.kimi.com", "api.kimi.ai"} or host.endswith((".moonshot.ai", ".moonshot.cn")):
            provider = "moonshot"
        else:
            provider = "custom" if base_url and host != "api.openai.com" else "openai"
    if provider == "custom" and not base_url:
        raise ValueError("自定义供应商必须填写 Base URL")
    return provider, base_url or BASE_URL[provider]
