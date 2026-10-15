"""原子写入与幂等提交单元的回归测试。"""

import json
import tempfile
import unittest
import sqlite3
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

from app.services.agent_delivery import commit_generation_result
from app.utils.blueprint_parser import save_blueprint_file_as


class AtomicSaveTest(unittest.TestCase):
    def test_saved_file_event_is_broadcast_even_if_history_database_is_locked(self):
        from app.services.generation_job_service import DurableEventSink
        service = Mock()
        service.publish_event = AsyncMock(side_effect=sqlite3.OperationalError("database is locked"))
        service._broadcast = AsyncMock()
        sink = DurableEventSink(service, "req_locked")
        event = {"type": "blueprint_generated", "request_id": "req_locked", "filename": "draft.wild"}
        coroutine = sink.send_json(event)
        with self.assertRaises(StopIteration):
            coroutine.send(None)
        service._broadcast.assert_awaited_once()
        assert service._broadcast.call_args.args[1]["filename"] == "draft.wild"
        assert sink.failed and "database is locked" in sink.error

    def test_save_is_atomic_and_leaves_no_temp_file(self):
        blueprint = {"meta": {"name": "x"}, "geometry": {"elements": [], "components": []}}
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            saved = save_blueprint_file_as(blueprint, directory, "2026-08-14/sess_x.wild")
            target = Path(saved)
            self.assertTrue(target.exists())
            self.assertEqual(json.loads(target.read_text(encoding="utf-8")), blueprint)
            self.assertEqual(list(directory.rglob("*.tmp-*")), [])

    def test_commit_generation_result_uses_single_delivery_entry(self):
        blueprint = {"meta": {"name": "提交"}, "geometry": {"elements": [], "components": []}}
        from app.agent.validation.diagnostics import VALIDATOR_VERSION, blueprint_fingerprint
        snapshot = {"blueprint_fingerprint": blueprint_fingerprint(blueprint), "validator_version": VALIDATOR_VERSION,
                    "status": "complete", "results": [], "error_count": 0}
        with patch("app.services.agent_delivery.prepare_blueprint_delivery") as prepare:
            commit_generation_result("sess_1", "req_1", blueprint, [], status="complete", validation_snapshot=snapshot)
            # 同一会话再次提交仍走同一 prepare（文件名确定性），不产生副本。
            commit_generation_result("sess_1", "req_2", blueprint, [], status="complete", validation_snapshot=snapshot)
        self.assertEqual(prepare.call_count, 2)


if __name__ == "__main__":
    unittest.main()
