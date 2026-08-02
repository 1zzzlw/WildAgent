"""Presence 扩展专用的客户端 IP 提取、脱敏与本地 GeoIP 查询。"""

from __future__ import annotations

import ipaddress
import os
from pathlib import Path

import geoip2.database
from geoip2.errors import AddressNotFoundError
from loguru import logger


DEFAULT_TRUSTED_PROXY_CIDRS = "127.0.0.0/8,::1/128,172.16.0.0/12"
DEFAULT_GEOIP_DB = (
    Path(__file__).resolve().parents[3]
    / "storage"
    / "geoip"
    / "GeoLite2-City.mmdb"
)


def _parse_ip(value: str | None) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    if not value:
        return None
    candidate = value.strip().strip("[]")
    try:
        return ipaddress.ip_address(candidate)
    except ValueError:
        return None


def _trusted_proxy_networks() -> tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...]:
    configured = os.getenv(
        "PRESENCE__TRUSTED_PROXY_CIDRS",
        DEFAULT_TRUSTED_PROXY_CIDRS,
    )
    networks = []
    for value in configured.split(","):
        value = value.strip()
        if not value:
            continue
        try:
            networks.append(ipaddress.ip_network(value, strict=False))
        except ValueError:
            logger.warning(f"忽略无效的 PRESENCE__TRUSTED_PROXY_CIDRS 项: {value}")
    return tuple(networks)


def _is_trusted_proxy(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return any(
        address.version == network.version and address in network
        for network in _trusted_proxy_networks()
    )


def extract_client_ip(ws) -> str:
    """读取真实客户端 IP；仅在直连节点属于可信代理网段时接受代理头。"""
    peer = _parse_ip(getattr(getattr(ws, "client", None), "host", None))
    if peer is None:
        return "unknown"

    if _is_trusted_proxy(peer):
        headers = getattr(ws, "headers", {})
        real_ip = _parse_ip(headers.get("x-real-ip"))
        if real_ip is not None:
            return str(real_ip)

        forwarded_for = headers.get("x-forwarded-for", "")
        forwarded_ip = _parse_ip(forwarded_for.split(",")[-1])
        if forwarded_ip is not None:
            return str(forwarded_ip)

    return str(peer)


def mask_ip(address: str) -> str:
    """生成只用于前端展示的脱敏 IP，不返回完整地址。"""
    parsed = _parse_ip(address)
    if parsed is None:
        return "未知IP"
    if isinstance(parsed, ipaddress.IPv4Address):
        first, second, _, _ = str(parsed).split(".")
        return f"{first}.{second}.*.*"
    groups = parsed.exploded.split(":")
    return f"{groups[0]}:{groups[1]}:{groups[2]}:{groups[3]}::*"


class GeoIPResolver:
    """使用本地 GeoLite2 City MMDB 查询地区；缺失时不影响在线列表。"""

    def __init__(self, database_path: str | Path | None = None):
        configured = (
            database_path
            or os.getenv("PRESENCE__GEOIP_DB")
            or DEFAULT_GEOIP_DB
        )
        configured_path = Path(configured)
        self.database_path = (
            configured_path
            if configured_path.is_absolute()
            else Path(__file__).resolve().parents[3] / configured_path
        )
        self._reader: geoip2.database.Reader | None = None
        self._load_attempted = False

    def _get_reader(self) -> geoip2.database.Reader | None:
        if self._load_attempted:
            return self._reader
        self._load_attempted = True
        if not self.database_path.is_file():
            logger.info(f"Presence 地区库未配置: {self.database_path}")
            return None
        try:
            self._reader = geoip2.database.Reader(str(self.database_path))
        except Exception as exc:
            logger.warning(f"Presence GeoIP 数据库加载失败: {exc}")
        return self._reader

    def resolve_region(self, address: str) -> str:
        parsed = _parse_ip(address)
        if parsed is None:
            return "未知地区"
        if parsed.is_loopback:
            return "本机"
        if parsed.is_private or parsed.is_link_local:
            return "内网"

        reader = self._get_reader()
        if reader is None:
            return "地区库未配置"
        try:
            response = reader.city(str(parsed))
        except (AddressNotFoundError, ValueError):
            return "未知地区"
        except Exception as exc:
            logger.warning(f"Presence GeoIP 查询失败: {exc}")
            return "未知地区"

        subdivision = response.subdivisions.most_specific
        region = subdivision.names.get("zh-CN") or subdivision.name
        if region:
            return region
        country = response.country.names.get("zh-CN") or response.country.name
        return country or "未知地区"


geoip_resolver = GeoIPResolver()
