"""进程临时目录回退、启动顺序与真实 Chroma 持久化回归。"""

import asyncio
from concurrent.futures import ThreadPoolExecutor
import os
import sys
from types import SimpleNamespace

import pytest

from app.infrastructure import temporary


@pytest.fixture
def windows_temp(monkeypatch, tmp_path):
    monkeypatch.setattr(temporary, "sys", SimpleNamespace(platform="win32"))
    monkeypatch.setattr(temporary, "STORAGE_ROOT", tmp_path / "storage")
    monkeypatch.setattr(temporary.tempfile, "tempdir", temporary.tempfile.tempdir)
    monkeypatch.setenv("TEMP", str(tmp_path / "missing-temp"))
    monkeypatch.setenv("TMP", str(tmp_path / "missing-temp"))
    return tmp_path / "storage" / "tmp"


def test_writable_system_temp_is_preserved(monkeypatch, tmp_path, windows_temp):
    system_temp = tmp_path / "system-temp"
    system_temp.mkdir()
    monkeypatch.setenv("TMP", str(system_temp))
    original_temp = os.environ["TEMP"]
    original_cache = temporary.tempfile.tempdir
    assert temporary.ensure_writable_temp_directory() == system_temp
    assert os.environ["TEMP"] == original_temp
    assert temporary.tempfile.tempdir == original_cache
    assert not windows_temp.exists()
    assert list(system_temp.iterdir()) == []


def test_unusable_temp_falls_back_and_repeated_calls_keep_the_same_directory(windows_temp):
    for _ in range(2):
        assert temporary.ensure_writable_temp_directory() == windows_temp
        assert os.environ["TEMP"] == str(windows_temp)
        assert os.environ["TMP"] == str(windows_temp)
        assert temporary.tempfile.gettempdir() == str(windows_temp)
    assert list(windows_temp.iterdir()) == []


def test_temp_is_checked_when_tmp_is_unset(monkeypatch, windows_temp):
    monkeypatch.delenv("TMP")
    assert temporary.ensure_writable_temp_directory() == windows_temp


def test_unwritable_fallback_reports_failure_without_changing_process_settings(monkeypatch, windows_temp):
    original = (os.environ["TEMP"], os.environ["TMP"], temporary.tempfile.tempdir)
    monkeypatch.setattr(temporary, "_can_write", lambda _path: False)
    with pytest.raises(RuntimeError, match="均不可写"):
        temporary.ensure_writable_temp_directory()
    assert (os.environ["TEMP"], os.environ["TMP"], temporary.tempfile.tempdir) == original


def test_non_windows_does_not_override_environment(monkeypatch, windows_temp):
    monkeypatch.setattr(temporary, "sys", SimpleNamespace(platform="linux"))
    original = dict(os.environ)
    assert temporary.ensure_writable_temp_directory() is None
    assert dict(os.environ) == original
    assert not windows_temp.exists()


def test_concurrent_initialization_uses_one_valid_fallback(windows_temp):
    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(lambda _: temporary.ensure_writable_temp_directory(), range(4)))
    assert results == [windows_temp] * 4
    assert list(windows_temp.iterdir()) == []


def test_service_prepares_temp_before_starting_connections_and_workers(monkeypatch):
    from app.bootstrap import lifespan as service

    calls = []

    async def record():
        calls.append("connection_or_worker")

    monkeypatch.setattr(service, "ensure_writable_temp_directory", lambda: calls.append("temp"))
    monkeypatch.setattr(service, "init_connect", record)
    monkeypatch.setattr(service, "initialize_agent_resources", lambda: calls.append("agent"))
    monkeypatch.setattr(service, "realtime_bus", SimpleNamespace(start=record, close=record))
    monkeypatch.setattr(service, "presence_service", SimpleNamespace(startup=record, shutdown=record))
    monkeypatch.setattr(service, "startup_generation_jobs", record)
    monkeypatch.setattr(service, "shutdown_generation_jobs", record)
    monkeypatch.setattr(service, "close_connect", lambda: None)

    async def run():
        async with service.lifespan(None):
            calls.append("serving")

    asyncio.run(run())
    assert calls[:3] == ["temp", "connection_or_worker", "agent"]
    assert "serving" in calls


@pytest.mark.skipif(sys.platform != "win32", reason="回放 Windows 原生 SQLite 临时目录错误")
def test_real_chroma_can_create_write_and_query_with_broken_original_temp(tmp_path, windows_temp):
    from app.infrastructure.retrieval.loader import HashEmbeddingFunction, RAGSpecLoader

    loader = RAGSpecLoader(
        base_paths=[], rag_paths=[], persist_dir=str(tmp_path / "index"),
        collection_name="temporary_directory_test",
        embedding_function=HashEmbeddingFunction(dimension=8), auto_sync=False,
    )
    try:
        collection = loader._get_collection()
        vector = [1.0] + [0.0] * 7
        collection.add(ids=["probe"], embeddings=[vector], documents=["local storage verification"])
        assert collection.count() == 1
        assert collection.query(query_embeddings=[vector], n_results=1)["ids"] == [["probe"]]
        assert os.environ["TMP"] == str(windows_temp)
        assert (tmp_path / "index" / "chroma.sqlite3").is_file()
    finally:
        if loader._client is not None:
            loader._client.close()
