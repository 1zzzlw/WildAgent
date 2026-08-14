"""原子写入与幂等提交单元的回归测试。"""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.services.agent_delivery import commit_generation_result
from app.utils.blueprint_parser import save_blueprint_file_as


class AtomicSaveTest(unittest.TestCase):
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
        with patch("app.services.agent_delivery.prepare_blueprint_delivery") as prepare:
            commit_generation_result("sess_1", "req_1", blueprint, [], status="complete")
            # 同一会话再次提交仍走同一 prepare（文件名确定性），不产生副本。
            commit_generation_result("sess_1", "req_2", blueprint, [], status="complete")
        self.assertEqual(prepare.call_count, 2)


if __name__ == "__main__":
    unittest.main()
