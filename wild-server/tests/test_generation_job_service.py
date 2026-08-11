import asyncio
import tempfile
import unittest
from pathlib import Path

from app.agent.protocol import versioned_event
from app.services.generation_job_service import GenerationJobService


class RecordingSubscriber:
    def __init__(self):
        self.messages: list[dict] = []

    async def send_json(self, payload: dict) -> None:
        self.messages.append(payload)


class BlockingResumeSubscriber(RecordingSubscriber):
    def __init__(self):
        super().__init__()
        self.ack_started = asyncio.Event()
        self.allow_ack = asyncio.Event()

    async def send_json(self, payload: dict) -> None:
        if payload.get("type") == "generation_resumed":
            self.ack_started.set()
            await self.allow_ack.wait()
        await super().send_json(payload)


class GenerationJobServiceTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "checkpoints.sqlite3"
        self.services: list[GenerationJobService] = []

    async def asyncTearDown(self):
        for service in reversed(self.services):
            if service._initialized:
                await service.shutdown()
        self.temp_dir.cleanup()

    def make_service(self) -> GenerationJobService:
        service = GenerationJobService(self.database_path)
        self.services.append(service)
        return service

    async def wait_for_status(
        self,
        service: GenerationJobService,
        request_id: str,
        expected: str,
    ):
        for _ in range(100):
            job = await service.get_job(request_id)
            if job is not None and job.status == expected:
                return job
            await asyncio.sleep(0.01)
        self.fail(f"任务 {request_id} 未进入 {expected} 状态")

    async def test_job_continues_and_persists_event_without_subscriber(self):
        service = self.make_service()
        started = asyncio.Event()
        release = asyncio.Event()

        async def runner(sink, _payload, _resume):
            started.set()
            await release.wait()
            await sink.send_json(versioned_event({
                "type": "agent_reply",
                "request_id": "req_disconnect",
                "session_id": "session_disconnect",
                "content": "后台完成",
            }))

        await service.startup(runner)
        subscriber = RecordingSubscriber()
        await service.start_job({
            "request_id": "req_disconnect",
            "session_id": "session_disconnect",
            "precision_mode": True,
        }, subscriber)
        await started.wait()
        await service.detach(subscriber)
        release.set()

        job = await self.wait_for_status(service, "req_disconnect", "completed")
        events = await service.events_after(job.request_id, 0)
        self.assertEqual(subscriber.messages, [])
        self.assertEqual(events[0]["type"], "agent_reply")
        self.assertEqual(events[0]["event_seq"], 1)

    async def test_restart_recovers_running_job_and_replays_events(self):
        first = self.make_service()
        started = asyncio.Event()

        async def blocking_runner(_sink, _payload, _resume):
            started.set()
            await asyncio.Event().wait()

        await first.startup(blocking_runner)
        await first.start_job({
            "request_id": "req_restart",
            "session_id": "session_restart",
            "precision_mode": True,
        }, RecordingSubscriber())
        await started.wait()
        await first.shutdown()

        paused = await first.get_job("req_restart")
        self.assertIsNotNone(paused)
        self.assertEqual(paused.status, "running")

        second = self.make_service()
        resume_flags: list[bool] = []

        async def resumed_runner(sink, _payload, resume):
            resume_flags.append(resume)
            await sink.send_json(versioned_event({
                "type": "agent_reply",
                "request_id": "req_restart",
                "session_id": "session_restart",
                "content": "重启后完成",
            }))

        await second.startup(resumed_runner)
        await self.wait_for_status(second, "req_restart", "completed")
        self.assertEqual(resume_flags, [True])

        subscriber = RecordingSubscriber()
        job = await second.resume_or_replay(
            subscriber,
            request_id="req_restart",
            session_id="session_restart",
            after_seq=0,
        )
        self.assertIsNotNone(job)
        self.assertEqual(
            [message["type"] for message in subscriber.messages],
            ["generation_resumed", "agent_reply"],
        )
        self.assertEqual(subscriber.messages[1]["event_seq"], 1)

    async def test_replay_finishes_before_new_live_persisted_event(self):
        service = self.make_service()
        first_published = asyncio.Event()
        publish_second = asyncio.Event()

        async def runner(sink, _payload, _resume):
            await sink.send_json(versioned_event({
                "type": "agent_step",
                "request_id": "req_order",
                "session_id": "session_order",
                "stage": "generating",
                "content": "第一条",
            }))
            first_published.set()
            await publish_second.wait()
            await sink.send_json(versioned_event({
                "type": "agent_reply",
                "request_id": "req_order",
                "session_id": "session_order",
                "content": "第二条",
            }))

        await service.startup(runner)
        original = RecordingSubscriber()
        await service.start_job({
            "request_id": "req_order",
            "session_id": "session_order",
            "precision_mode": True,
        }, original)
        await first_published.wait()
        await service.detach(original)

        resumed = BlockingResumeSubscriber()
        replay_task = asyncio.create_task(service.resume_or_replay(
            resumed,
            request_id="req_order",
            session_id="session_order",
            after_seq=0,
        ))
        await resumed.ack_started.wait()
        publish_second.set()
        await asyncio.sleep(0.02)
        self.assertEqual(resumed.messages, [])

        resumed.allow_ack.set()
        await replay_task
        await self.wait_for_status(service, "req_order", "completed")
        self.assertEqual(
            [
                (message["type"], message.get("event_seq"))
                for message in resumed.messages
            ],
            [
                ("generation_resumed", None),
                ("agent_step", 1),
                ("agent_reply", 2),
            ],
        )

    async def test_terminal_event_closes_restart_crash_window(self):
        first = self.make_service()
        terminal_persisted = asyncio.Event()

        async def terminal_then_block(sink, _payload, _resume):
            await sink.send_json(versioned_event({
                "type": "agent_reply",
                "request_id": "req_terminal",
                "session_id": "session_terminal",
                "content": "结果已持久化",
            }))
            terminal_persisted.set()
            await asyncio.Event().wait()

        await first.startup(terminal_then_block)
        await first.start_job({
            "request_id": "req_terminal",
            "session_id": "session_terminal",
            "precision_mode": True,
        }, RecordingSubscriber())
        await terminal_persisted.wait()
        await self.wait_for_status(first, "req_terminal", "completed")
        await first.shutdown()

        second = self.make_service()
        resumed: list[str] = []

        async def should_not_resume(_sink, payload, _resume):
            resumed.append(payload["request_id"])

        await second.startup(should_not_resume)
        await asyncio.sleep(0.02)
        self.assertEqual(resumed, [])


if __name__ == "__main__":
    unittest.main()
