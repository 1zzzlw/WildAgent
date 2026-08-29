import asyncio
import tempfile
import unittest
from pathlib import Path

from app.agent.protocol import versioned_event
from app.services.generation_job_service import GenerationJobService, GenerationPaused


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

    async def test_public_progress_is_persisted_but_model_reasoning_is_not(self):
        service = self.make_service()

        async def runner(sink, payload, _resume):
            for channel, delta in (
                ("progress", "正在比较平面候选"),
                ("reasoning", "模型原始思考"),
            ):
                await sink.send_json(versioned_event({
                    "type": "thinking_delta",
                    "request_id": payload["request_id"],
                    "session_id": payload["session_id"],
                    "node": "architecture",
                    "channel": channel,
                    "delta": delta,
                }))

        await service.startup(runner)
        subscriber = RecordingSubscriber()
        await service.start_job({
            "request_id": "req_progress",
            "session_id": "session_progress",
        }, subscriber)
        await self.wait_for_status(service, "req_progress", "completed")

        events = await service.events_after("req_progress", 0)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["channel"], "progress")
        self.assertEqual(events[0]["delta"], "正在比较平面候选")
        self.assertEqual(
            [message["channel"] for message in subscriber.messages],
            ["progress", "reasoning"],
        )

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

    async def test_generation_pause_does_not_rewrite_persisted_review_status(self):
        service = self.make_service()
        waiting_persisted = asyncio.Event()
        allow_pause = asyncio.Event()
        status_writes: list[str] = []
        original_mark_status = service._mark_status

        async def tracking_mark_status(request_id, status, error):
            status_writes.append(status)
            await original_mark_status(request_id, status, error)

        service._mark_status = tracking_mark_status

        async def runner(_sink, payload, _resume):
            await service.mark_waiting_for_review(
                payload["request_id"],
                "execution_plan",
            )
            waiting_persisted.set()
            await allow_pause.wait()
            raise GenerationPaused()

        await service.startup(runner)
        await service.start_job({
            "request_id": "req_persisted_pause",
            "session_id": "session_persisted_pause",
        }, RecordingSubscriber())
        await waiting_persisted.wait()
        active = service._active_tasks["req_persisted_pause"]

        allow_pause.set()
        await active

        job = await service.get_job("req_persisted_pause")
        self.assertIsNotNone(job)
        self.assertEqual(job.status, "waiting_review")
        self.assertNotIn("waiting_review", status_writes)

    async def test_floor_plan_review_pauses_and_resumes_same_job(self):
        service = self.make_service()
        resume_payloads: list[dict] = []

        async def runner(sink, payload, resume):
            if not resume:
                await service.mark_waiting_for_review(payload["request_id"])
                await sink.send_json(versioned_event({
                    "type": "floor_plan_review_required",
                    "request_id": payload["request_id"],
                    "session_id": payload["session_id"],
                    "revision": 0,
                    "can_confirm": True,
                }))
                raise GenerationPaused()
            resume_payloads.append(payload["_floor_plan_review"])

        await service.startup(runner)
        subscriber = RecordingSubscriber()
        await service.start_job({
            "request_id": "req_review",
            "session_id": "session_review",
            "precision_mode": True,
        }, subscriber)
        await self.wait_for_status(service, "req_review", "waiting_review")

        await service.submit_floor_plan_review(
            subscriber,
            request_id="req_review",
            session_id="session_review",
            action="revise",
            feedback="主卧增加一扇朝南窗",
        )
        await self.wait_for_status(service, "req_review", "completed")

        self.assertEqual(resume_payloads, [{
            "action": "revise",
            "feedback": "主卧增加一扇朝南窗",
        }])
        events = await service.events_after("req_review", 0)
        self.assertEqual(events[0]["type"], "floor_plan_review_required")

    async def test_style_review_pauses_and_resumes_same_job(self):
        service = self.make_service()
        resume_payloads: list[dict] = []

        async def runner(sink, payload, resume):
            if not resume:
                await service.mark_waiting_for_review(payload["request_id"], "style")
                await sink.send_json(versioned_event({
                    "type": "style_review_required",
                    "request_id": payload["request_id"],
                    "session_id": payload["session_id"],
                    "revision": 0,
                    "selected_style_id": "modern",
                    "options": [],
                }))
                raise GenerationPaused()
            resume_payloads.append(payload["_style_review"])

        await service.startup(runner)
        subscriber = RecordingSubscriber()
        await service.start_job({
            "request_id": "req_style_review",
            "session_id": "session_style_review",
            "precision_mode": True,
        }, subscriber)
        await self.wait_for_status(service, "req_style_review", "waiting_review")

        await service.submit_style_review(
            subscriber,
            request_id="req_style_review",
            session_id="session_style_review",
            action="confirm",
            style_package_id="chinese",
        )
        await self.wait_for_status(service, "req_style_review", "completed")

        self.assertEqual(resume_payloads, [{
            "action": "confirm",
            "style_package_id": "chinese",
            "feedback": "",
        }])
        events = await service.events_after("req_style_review", 0)
        self.assertEqual(events[0]["type"], "style_review_required")

    async def test_execution_plan_review_pauses_and_resumes_same_job(self):
        service = self.make_service()
        resume_payloads: list[dict] = []
        allow_pause_to_finish = asyncio.Event()
        handoff_started = asyncio.Event()
        original_resume_review_job = service._resume_review_job

        async def tracking_resume_review_job(resumed):
            handoff_started.set()
            await original_resume_review_job(resumed)

        service._resume_review_job = tracking_resume_review_job

        async def runner(sink, payload, resume):
            if not resume:
                await service.mark_waiting_for_review(
                    payload["request_id"],
                    "execution_plan",
                )
                await sink.send_json(versioned_event({
                    "type": "execution_plan_review_required",
                    "request_id": payload["request_id"],
                    "session_id": payload["session_id"],
                    "plan": {"version": 1, "steps": []},
                }))
                await allow_pause_to_finish.wait()
                raise GenerationPaused()
            resume_payloads.append(payload["_execution_plan_review"])

        await service.startup(runner)
        subscriber = RecordingSubscriber()
        await service.start_job({
            "request_id": "req_plan_review",
            "session_id": "session_plan_review",
            "plan_mode": True,
        }, subscriber)
        await self.wait_for_status(service, "req_plan_review", "waiting_review")

        submit_task = asyncio.create_task(service.submit_execution_plan_review(
            subscriber,
            request_id="req_plan_review",
            session_id="session_plan_review",
            action="confirm",
        ))
        await handoff_started.wait()
        self.assertFalse(submit_task.done())

        allow_pause_to_finish.set()
        await submit_task
        await self.wait_for_status(service, "req_plan_review", "completed")

        self.assertEqual(resume_payloads, [{"action": "confirm", "feedback": ""}])

    async def test_running_execution_feedback_is_persisted_and_drained_once(self):
        service = self.make_service()
        started = asyncio.Event()
        release = asyncio.Event()

        async def runner(_sink, _payload, _resume):
            started.set()
            await release.wait()

        await service.startup(runner)
        subscriber = RecordingSubscriber()
        await service.start_job({
            "request_id": "req_feedback",
            "session_id": "session_feedback",
            "plan_mode": True,
        }, subscriber)
        await started.wait()

        queued_count = await service.queue_execution_feedback(
            request_id="req_feedback",
            session_id="session_feedback",
            feedback="塔楼改为更细长的比例",
        )

        self.assertEqual(queued_count, 1)
        self.assertEqual(
            await service.drain_execution_feedback("req_feedback"),
            ["塔楼改为更细长的比例"],
        )
        self.assertEqual(await service.drain_execution_feedback("req_feedback"), [])
        events = await service.events_after("req_feedback", 0)
        self.assertEqual(events[-1]["type"], "execution_feedback_queued")
        release.set()
        await self.wait_for_status(service, "req_feedback", "completed")


if __name__ == "__main__":
    unittest.main()
