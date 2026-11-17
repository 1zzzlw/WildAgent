"""会话占用信息复用在线连接；仅使用隔离 SQL/Redis 存储。"""

import asyncio
import json
import time

import pytest

from app.api.websocket.connections import WebSocketConnectionRegistry
from app.application.errors import ApplicationError
from app.application.presence import PresenceService, public_presence_snapshot
from app.infrastructure.persistence.repositories.accounts import accounts
from app.infrastructure.persistence.repositories.conversations import conversations
from app.infrastructure.redis.connection import cache
from app.infrastructure.redis.events import RealtimeBus


class Socket:
    def __init__(self):
        self.events = []

    async def send_json(self, payload):
        self.events.append(payload)


async def eventually(predicate):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if predicate():
            return
        await asyncio.sleep(0.02)
    raise AssertionError("会话使用状态未同步")


def editor(name):
    account = accounts.create(name, name + "@example.com", "unused-test-password-hash")
    return {"id": account["id"], "username": name, "identity": 1, "role": "editor"}


def test_shared_activity_identity_idle_expiry_and_disconnect_across_workers(storage):
    owner, other = editor("owner"), editor("other")
    conversations.ensure("session_shared")
    before = conversations.read("session_shared")

    async def run():
        bus_a, bus_b = RealtimeBus(client=cache.async_client), RealtimeBus(client=cache.async_client)
        first, second = WebSocketConnectionRegistry(bus=bus_a), WebSocketConnectionRegistry(bus=bus_b)
        ws_a, ws_b = Socket(), Socket()
        try:
            await first.connect(ws_a, client_ip="127.0.0.1", region="测试", display_name="自定义昵称", user=owner)
            await second.connect(ws_b, client_ip="127.0.0.1", region="测试", user=other)
            identity = first._connections[ws_a]

            def participant():
                return next(row for row in ws_b.events[-1]["clients"] if row["id"] == identity)

            for activity in ("active", "generating", "idle"):
                await first.update_activity(ws_a, session_id="session_shared", activity=activity, user=owner)
                await eventually(lambda: participant().get("activity") == activity)
                assert participant()["username"] == "owner"
                assert participant()["session_id"] == "session_shared"
                assert not any(key.startswith("_") for key in participant())
            await first.update_display_name(ws_a, "冒充其他账号")
            await eventually(lambda: participant()["display_name"] == "冒充其他账号")
            assert participant()["username"] == "owner"

            await first.update_activity(ws_a, session_id="session_shared", activity="active", user=owner)
            await eventually(lambda: participant()["activity"] == "active")
            unchanged = len(ws_b.events)
            await first.update_activity(ws_a, session_id="session_shared", activity="active", user=owner)
            await asyncio.sleep(0.05)
            assert len(ws_b.events) == unchanged
            key = cache.key("presence:client:" + identity)
            value = json.loads(await cache.async_client.get(key))
            value["_activity_at"] = int(time.time() * 1000) - 61_000
            await cache.async_client.set(key, json.dumps(value), xx=True, keepttl=True)
            await second._broadcast()
            assert participant()["activity"] == "idle"
            # 连接心跳续期不会把空闲用户改回操作中。
            first._last_touch[ws_a] -= 30
            await first.touch(ws_a)
            await second._broadcast()
            assert participant()["activity"] == "idle"
            await first.disconnect(ws_a)
            await eventually(lambda: all(row["id"] != identity for row in ws_b.events[-1]["clients"]))
            assert ws_a not in first._users and ws_a not in first._last_sent
        finally:
            await first.shutdown()
            await second.shutdown()
            await bus_a.close()
            await bus_b.close()
            await cache.aclose()

    asyncio.run(run())
    assert conversations.read("session_shared") == before


def test_private_and_unsaved_session_visibility_and_read_only_user(storage):
    owner, other, admin = editor("owner"), editor("other"), editor("admin")
    admin["identity"] = 2
    guest = {"role": "guest", "username": "访客"}
    conversations.ensure("session_private", owner["id"])

    async def run():
        service = PresenceService()
        client = await service.register(display_name="假名称", masked_ip="127.0.*.*", region="测试", user=owner)
        for session_id in ("session_private", "session_unsaved"):
            await service.set_activity(client["id"], session_id=session_id, activity="active", user=owner)
            raw = await service.snapshot()
            for viewer in (owner, admin):
                public = public_presence_snapshot(raw, viewer)
                assert public["clients"][0]["session_id"] == session_id
                assert public["clients"][0]["username"] == "owner"
            for viewer in (other, guest, None):
                public = public_presence_snapshot(raw, viewer)
                assert public["clients"][0]["session_id"] is None
                assert public["clients"][0]["activity"] == "idle"
                assert not any(key.startswith("_") for key in public["clients"][0])
        for user, session_id in ((other, "session_private"), (guest, "session_private")):
            with pytest.raises(ApplicationError):
                await service.set_activity(client["id"], session_id=session_id, activity="active", user=user)
        await service.set_activity(client["id"], session_id=None, activity="idle", user=owner)
        assert (await service.snapshot())["clients"][0]["session_id"] is None
        await service.remove(client["id"])
        assert not await service.set_activity(client["id"], session_id="session_private", activity="active", user=owner)
        assert (await service.snapshot())["online_count"] == 0
        await cache.aclose()

    asyncio.run(run())
    assert conversations.owner("session_unsaved") == (False, None)


def test_disconnect_during_snapshot_send_does_not_restore_socket_state(storage):
    owner = editor("owner")
    conversations.ensure("session_shared")

    async def run():
        bus = RealtimeBus(client=cache.async_client)
        registry = WebSocketConnectionRegistry(bus=bus)
        entered, release = asyncio.Event(), asyncio.Event()

        class SlowSocket(Socket):
            slow = False

            async def send_json(self, payload):
                if self.slow:
                    entered.set()
                    await release.wait()
                await super().send_json(payload)

        ws = SlowSocket()
        try:
            await registry.connect(ws, client_ip="127.0.0.1", region="测试", user=owner)
            ws.slow = True
            sending = asyncio.create_task(registry.update_activity(ws, session_id="session_shared", activity="active", user=owner))
            await asyncio.wait_for(entered.wait(), 2)
            disconnecting = asyncio.create_task(registry.disconnect(ws))
            await asyncio.sleep(0)
            assert ws not in registry._connections
            release.set()
            await asyncio.gather(sending, disconnecting)
            assert ws not in registry._users and ws not in registry._last_sent
            assert (await registry._snapshot())["online_count"] == 0
        finally:
            release.set()
            await registry.shutdown()
            await bus.close()
            await cache.aclose()

    asyncio.run(run())


@pytest.mark.parametrize("session_id, activity", [("../private", "active"), ("x" * 129, "idle"), ([], "active"), (None, "invalid"), (None, {})])
def test_presence_rejects_invalid_activity_without_creating_state(storage, session_id, activity):
    async def run():
        service = PresenceService()
        with pytest.raises(ApplicationError) as error:
            await service.set_activity("unknown", session_id=session_id, activity=activity, user={"id": "editor", "role": "editor"})
        assert error.value.code == "invalid_input"
        assert (await service.snapshot())["online_count"] == 0
        await cache.aclose()
    asyncio.run(run())
