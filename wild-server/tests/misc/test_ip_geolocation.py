import unittest
from types import SimpleNamespace

from app.extensions.presence.geoip import GeoIPResolver, extract_client_ip, mask_ip


class IPGeolocationTest(unittest.TestCase):
    def test_mask_ip_hides_host_part(self):
        self.assertEqual(mask_ip("113.96.1.8"), "113.96.*.*")
        self.assertEqual(mask_ip("2001:db8::1"), "2001:0db8:0000:0000::*")
        self.assertEqual(mask_ip("not-an-ip"), "未知IP")

    def test_trusted_proxy_uses_nginx_real_ip(self):
        ws = SimpleNamespace(
            client=SimpleNamespace(host="172.18.0.3"),
            headers={
                "x-real-ip": "113.96.1.8",
                "x-forwarded-for": "198.51.100.7, 113.96.1.8",
            },
        )
        self.assertEqual(extract_client_ip(ws), "113.96.1.8")

    def test_untrusted_peer_cannot_spoof_proxy_headers(self):
        ws = SimpleNamespace(
            client=SimpleNamespace(host="8.8.8.8"),
            headers={"x-real-ip": "113.96.1.8"},
        )
        self.assertEqual(extract_client_ip(ws), "8.8.8.8")

    def test_private_and_missing_database_fallbacks(self):
        resolver = GeoIPResolver("missing-city.mmdb")
        self.assertEqual(resolver.resolve_region("127.0.0.1"), "本机")
        self.assertEqual(resolver.resolve_region("192.168.1.10"), "内网")
        self.assertEqual(resolver.resolve_region("8.8.8.8"), "地区库未配置")
