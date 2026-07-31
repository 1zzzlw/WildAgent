"""
WebSocket 心跳监控器

独立于 WebSocket 端点的心跳检测工具，负责：
- 定期检查 last_message_time，超时则回调通知
- 支持 is_processing 标记（AI 查询期间豁免超时）
- touch() 刷新最后消息时间

使用方式:
    heartbeat = WebSocketHeartbeat(timeout=90, check_interval=10)

    async def on_timeout(elapsed: float):
        await ws.close()

    await heartbeat.start(on_timeout)

    # 在消息接收循环中每次收到消息后调用:
    heartbeat.touch()

    # AI 处理期间豁免超时:
    heartbeat.is_processing = True
    try:
        await long_running_task()
    finally:
        heartbeat.is_processing = False
        heartbeat.touch()
"""

import asyncio
import time
from collections.abc import Awaitable, Callable
from loguru import logger


class WebSocketHeartbeat:
    """WebSocket 心跳监控器

    后台异步任务定期检查 last_message_time，超时则调用 on_timeout 回调。
    回调负责具体的断开逻辑（发送 network_error、关闭连接等），监控器本身
    只负责检测和通知，与具体 WebSocket 实现解耦。

    Attributes:
        timeout: 超时阈值（秒），超过此时间未收到消息则触发回调
        check_interval: 检查间隔（秒）
        is_processing: AI 处理标记，为 True 时跳过超时检查
    """

    def __init__(self, timeout: float = 90, check_interval: float = 10):
        """保存检查参数并初始化尚未启动的监控状态。"""
        self.timeout = timeout
        self.check_interval = check_interval
        # 这是由调用方维护的协作标记，不代表后台任务自身正在执行。
        self.is_processing: bool = False

        # 使用墙上时钟记录最近活动；elapsed 属性和检查循环采用同一时间源。
        self._last_message_time: float = time.time()
        self._alive: bool = False
        # 每个 Heartbeat 实例至多持有一个监控 Task。
        self._task: asyncio.Task | None = None

    @property
    def last_message_time(self) -> float:
        """最近一次收到消息的时间戳"""
        return self._last_message_time

    @property
    def elapsed(self) -> float:
        """距离上次收到消息经过的秒数（方便调试/日志）"""
        return time.time() - self._last_message_time

    def touch(self):
        """刷新最后消息时间（收到任何消息时调用）"""
        self._last_message_time = time.time()

    async def start(self, on_timeout: Callable[[float], Awaitable[None]]):
        """启动心跳监控（后台异步任务）

        Args:
            on_timeout: 超时回调，接收 elapsed 秒数作为参数。
                        回调内部负责具体的断开逻辑，如果回调抛出异常，
                        监控器会记录日志并停止。
        """
        # 每次 start 都从当前时刻重新计时，构造对象到启动之间的耗时不算空闲。
        self._last_message_time = time.time()
        self._alive = True
        self._task = asyncio.create_task(self._monitor(on_timeout))

    async def stop(self):
        """停止心跳监控，取消后台任务"""
        self._alive = False
        if self._task is not None:
            # sleep 中的任务只有通过 cancel 才能立即结束，不必等待 check_interval。
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                # stop 主动取消属于正常控制流，不向上游暴露异常。
                pass
            self._task = None

    async def _monitor(self, on_timeout: Callable[[float], Awaitable[None]]):
        """循环检查空闲时长；首次超时回调完成后终止监控。"""
        try:
            while self._alive:
                await asyncio.sleep(self.check_interval)

                if not self._alive:
                    break

                # AI 处理期间跳过检查（额外安全保护，实际 ping 仍可正常响应）
                if self.is_processing:
                    continue

                elapsed = time.time() - self._last_message_time
                if elapsed > self.timeout:
                    logger.warning(
                        f"WebSocket 心跳超时: {elapsed:.0f}s 未收到消息，触发断开回调"
                    )
                    try:
                        await on_timeout(elapsed)
                    except Exception as exc:
                        logger.error(f"心跳超时回调执行异常: {exc}")
                    finally:
                        # 无论回调成功与否都只触发一次，防止重复关闭同一连接。
                        self._alive = False
                    break
        except asyncio.CancelledError:
            # stop() 或连接清理触发的取消是预期退出路径。
            pass
        except Exception as exc:
            # 监控器自身失败不应击穿 WebSocket 端点，只记录诊断日志。
            logger.error(f"心跳监控异常: {exc}")
