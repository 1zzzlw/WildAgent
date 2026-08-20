"""Agent Turn 服务端持久化与中断恢复测试。"""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.api import sessions


class _Request:
    def __init__(self, body):
        self._body = body

    async def json(self):
        return self._body


def _content(response):
    return json.loads(response.body)


class SessionTurnPersistenceTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.sessions_dir_patch = patch.object(
            sessions,
            "SESSIONS_DIR",
            Path(self.temp_dir.name),
        )
        self.sessions_dir_patch.start()
        self.addCleanup(self.sessions_dir_patch.stop)

    def test_blueprint_description_is_compacted_but_manual_session_name_wins(self):
        blueprint_info = {
            "filename": "2026-08-12/session_title.wild",
            "name": "退台新中式别墅：一层矩形基座，二层U形退台，两翼端部设置阳台",
            "elements_count": 10,
            "components_count": 4,
            "updated_at": 1,
        }
        with patch.object(sessions, "_find_blueprint_for_session", return_value=blueprint_info):
            automatic = sessions._build_session_info("session_title", {"name": "新建筑"})
            manual = sessions._build_session_info("session_title", {"name": "我的方案"})

        assert automatic["name"] == "退台新中式别墅"
        assert manual["name"] == "我的方案"

    async def test_replace_deduplicates_and_round_trips_turns(self):
        response = await sessions.replace_turns(
            "session_turns",
            _Request({
                "turns": [
                    {"request_id": "req_1", "status": "running", "started_at": 1},
                    {"request_id": "req_1", "status": "completed", "started_at": 2},
                    {"request_id": "req_2", "status": "completed", "started_at": 3},
                ],
            }),
        )

        assert _content(response)["turn_count"] == 2
        turns = _content(await sessions.get_turns("session_turns"))
        assert [turn["request_id"] for turn in turns] == ["req_1", "req_2"]
        assert turns[0]["status"] == "completed"

    async def test_running_turn_from_before_server_start_is_marked_interrupted(self):
        sessions._write_session_meta("session_interrupted", {
            "turns": [{
                "request_id": "req_old",
                "status": "running",
                "server_instance_id": "previous-server-instance",
                "thinking_status": "thinking",
                "steps": [{"node": "skeleton", "status": "running"}],
            }],
        })

        turns = _content(await sessions.get_turns("session_interrupted"))
        assert turns[0]["status"] == "error"
        assert turns[0]["thinking_status"] == "error"
        assert turns[0]["steps"][0]["status"] == "error"
        assert "中断" in turns[0]["interruption_reason"]

    async def test_current_server_running_turn_is_not_interrupted(self):
        await sessions.replace_turns(
            "session_active",
            _Request({
                "turns": [{
                    "request_id": "req_active",
                    "status": "running",
                    "started_at": 1,
                }],
            }),
        )

        turns = _content(await sessions.get_turns("session_active"))
        assert turns[0]["status"] == "running"
        assert turns[0]["server_instance_id"] == sessions.SERVER_INSTANCE_ID
        assert "interruption_reason" not in turns[0]
