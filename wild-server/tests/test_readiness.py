import json
import unittest
from unittest.mock import patch

import main


class _ReadyRAGSpecLoader:
    def list_sources(self):
        return [f"source-{index}" for index in range(37)]

    @property
    def last_sync_stats(self):
        return {"total": 362, "updated": 362, "deleted": 0}


class _FallbackFileSpecLoader:
    def list_sources(self):
        return ["BLUEPRINT-SPEC-MINIMAL.md"]


# readiness 使用真实类名区分生产 RAG 和静默文件降级；测试替身保持同名。
_ReadyRAGSpecLoader.__name__ = "RAGSpecLoader"
_FallbackFileSpecLoader.__name__ = "FileSpecLoader"


class ReadinessTest(unittest.IsolatedAsyncioTestCase):
    async def test_rag_loader_with_index_is_ready(self):
        with (
            patch.object(main.config.rag, "enabled", True),
            patch.object(main.agent_service, "spec_loader", _ReadyRAGSpecLoader()),
        ):
            response = await main.readiness()

        payload = json.loads(response.body)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["status"], "ready")
        self.assertEqual(payload["rag"]["source_count"], 37)
        self.assertEqual(payload["rag"]["sync"]["total"], 362)

    async def test_rag_fallback_is_not_ready_when_rag_is_enabled(self):
        with (
            patch.object(main.config.rag, "enabled", True),
            patch.object(main.agent_service, "spec_loader", _FallbackFileSpecLoader()),
        ):
            response = await main.readiness()

        payload = json.loads(response.body)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(payload["status"], "not_ready")
        self.assertEqual(payload["rag"]["loader"], "FileSpecLoader")

    async def test_file_loader_is_ready_when_rag_is_intentionally_disabled(self):
        with (
            patch.object(main.config.rag, "enabled", False),
            patch.object(main.agent_service, "spec_loader", _FallbackFileSpecLoader()),
        ):
            response = await main.readiness()

        self.assertEqual(response.status_code, 200)
