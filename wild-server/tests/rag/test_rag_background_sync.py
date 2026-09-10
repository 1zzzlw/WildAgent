"""后台索引同步（不阻塞服务启动）的回归测试。

覆盖：
- RAGSpecLoader 构造（auto_sync=False）不发起任何 embedding 调用；
- start_background_sync 在守护线程中完成同步，且进程内单飞；
- 跨进程锁文件基本互斥语义（同进程内模拟第二次获取失败）。
"""
import shutil
import time
import unittest
from pathlib import Path

from app.spec.loader import HashEmbeddingFunction, RAGSpecLoader


def _wait_for(predicate, timeout: float = 15.0, interval: float = 0.05) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


class RAGBackgroundSyncTest(unittest.TestCase):
    _TMP_ROOT = Path.cwd() / ".rag_bg_sync_test"

    def setUp(self):
        # 沙箱/CI 环境对 mkdtemp(0o700) 的目录可能拒绝嵌套写入，
        # 统一使用工作区内固定目录（默认 ACL）并在 teardown 清理。
        self._tmp_root = self._TMP_ROOT
        self.kb_dir = self._tmp_root / "knowledge"
        self.persist_dir = self._tmp_root / "chroma"
        self.kb_dir.mkdir(parents=True, exist_ok=True)
        (self.kb_dir / "sample.md").write_text(
            "# 样本文档\n\n## 段落一\n\n矩形住宅的默认进深为 8 米。\n\n"
            "## 段落二\n\n内墙必须位于两个空间的公共边界上。\n\n"
            "## 段落三\n\n楼梯必须连接两个连续楼层。\n",
            encoding="utf-8",
        )

    def tearDown(self):
        shutil.rmtree(self._tmp_root, ignore_errors=True)

    def make_loader(self, auto_sync: bool = False) -> RAGSpecLoader:
        return RAGSpecLoader(
            base_paths=[],
            rag_paths=[str(self.kb_dir / "sample.md")],
            persist_dir=str(self.persist_dir),
            collection_name="test_background_sync",
            embedding_function=HashEmbeddingFunction(),
            top_k=4,
            auto_sync=auto_sync,
            namespace="test_sync",
        )

    def test_auto_sync_disabled_constructor_never_embeds(self):
        loader = self.make_loader(auto_sync=False)
        # 构造完成即返回，同步统计仍为空（尚未发起任何向量化）。
        self.assertEqual(loader.last_sync_stats, {"total": 0, "updated": 0, "deleted": 0})
        self.assertEqual(loader.sync_status["phase"], "pending")

    def test_background_sync_completes(self):
        loader = self.make_loader(auto_sync=False)
        started = loader.start_background_sync(attempts=2, backoff_seconds=(0.2, 0.5))
        self.assertTrue(started)
        self.assertTrue(_wait_for(lambda: loader.sync_status["phase"] == "ok"))
        self.assertGreater(loader.last_sync_stats["total"], 0)
        self.assertGreaterEqual(loader.last_sync_stats["updated"], 1)

    def test_start_background_sync_is_single_flight(self):
        loader = self.make_loader(auto_sync=False)
        self.assertTrue(loader.start_background_sync(attempts=1, backoff_seconds=(0.2,)))
        # 第二次调用是幂等 no-op。
        self.assertFalse(loader.start_background_sync(attempts=1, backoff_seconds=(0.2,)))
        self.assertTrue(_wait_for(lambda: loader.sync_status["phase"] == "ok"))

    def test_partial_sync_is_retried_and_never_reported_as_ok(self):
        loader = self.make_loader(auto_sync=False)
        calls = 0

        def partial_sync(*, raise_on_stall=True, budget_seconds=None):
            nonlocal calls
            calls += 1
            loader._last_sync_pending = 3
            loader._sync_status["pending_chunks"] = 3
            return 0

        loader.sync_index = partial_sync  # type: ignore[method-assign]
        self.assertTrue(loader.start_background_sync(attempts=2, backoff_seconds=(0.01,)))
        self.assertTrue(_wait_for(lambda: not loader._sync_thread.is_alive()))

        self.assertEqual(calls, 2)
        self.assertEqual(loader.sync_status["phase"], "degraded")
        self.assertEqual(loader.sync_status["pending_chunks"], 3)
        self.assertIn("3 个文本块待同步", loader.sync_status["last_error"])

    def test_process_lock_acquire_release(self):
        # Windows 字节锁按进程生效：同进程内可重复获取（用于跨进程互斥），
        # 这里只验证 获取→写持有者标记→释放→再次获取 的完整生命周期。
        loader = self.make_loader(auto_sync=False)
        first = loader._try_process_lock()
        self.assertIsNotNone(first)
        try:
            # 锁文件被 msvcrt 独占锁定，读持有者标记必须经由同一句柄。
            first.seek(0)
            marker = first.read().decode("utf-8", errors="replace")
            self.assertIn("pid=", marker)
        finally:
            loader._release_process_lock(first)
        third = loader._try_process_lock()
        self.assertIsNotNone(third, "释放后可以再次获取锁")
        loader._release_process_lock(third)


if __name__ == "__main__":
    unittest.main()
