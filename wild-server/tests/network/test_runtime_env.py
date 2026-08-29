"""运行时模型配置文件的路径和持久化回归。"""

from __future__ import annotations

import errno
from pathlib import Path

import pytest

from app.utils import runtime_env


def test_default_runtime_env_path_does_not_depend_on_cwd(monkeypatch) -> None:
    monkeypatch.delenv(runtime_env.RUNTIME_ENV_PATH_KEY, raising=False)

    assert runtime_env.runtime_env_path() == runtime_env.SERVER_ROOT / ".env"


def test_relative_runtime_env_path_is_resolved_from_server_root(monkeypatch) -> None:
    monkeypatch.setenv(runtime_env.RUNTIME_ENV_PATH_KEY, "runtime/config.env")

    assert runtime_env.runtime_env_path() == (
        runtime_env.SERVER_ROOT / "runtime" / "config.env"
    )


def test_update_runtime_env_preserves_other_content_and_updates_once(tmp_path) -> None:
    target = tmp_path / ".env"
    target.write_text(
        "# keep this comment\nCHAT__NAME=old\nRAG__ENABLED=true\nCHAT__NAME=duplicate\n",
        encoding="utf-8",
    )

    saved = runtime_env.update_runtime_env(
        {
            "CHAT__NAME": "new-model",
            "CHAT__API_KEY": "key with spaces",
            "CHAT__BASE_URL": "https://example.com/v1",
        },
        target,
    )

    content = target.read_text(encoding="utf-8")
    assert saved == target.resolve()
    assert "# keep this comment" in content
    assert "RAG__ENABLED=true" in content
    assert content.count("CHAT__NAME=") == 1
    assert "CHAT__NAME=new-model" in content
    assert 'CHAT__API_KEY="key with spaces"' in content
    assert "CHAT__BASE_URL=https://example.com/v1" in content


def test_update_runtime_env_rejects_multiline_values(tmp_path) -> None:
    with pytest.raises(ValueError, match="不能包含换行"):
        runtime_env.update_runtime_env(
            {"CHAT__API_KEY": "first\nINJECTED=value"},
            tmp_path / ".env",
        )


def test_single_file_bind_mount_falls_back_to_in_place_write(
    tmp_path,
    monkeypatch,
) -> None:
    target = tmp_path / ".env"
    target.write_text("CHAT__NAME=old\n", encoding="utf-8")
    original_inode = target.stat().st_ino

    def mounted_file_replace(_source: Path, _target: Path) -> None:
        raise OSError(errno.EBUSY, "mount point is busy")

    monkeypatch.setattr(runtime_env.os, "replace", mounted_file_replace)

    runtime_env.update_runtime_env({"CHAT__NAME": "new"}, target)

    assert target.read_text(encoding="utf-8") == "CHAT__NAME=new\n"
    assert target.stat().st_ino == original_inode


def test_persistence_flag_is_explicit_inside_container(monkeypatch) -> None:
    monkeypatch.setenv(runtime_env.RUNTIME_ENV_PERSISTENT_KEY, "true")
    monkeypatch.setenv(
        runtime_env.RUNTIME_ENV_HOST_PATH_KEY,
        "/opt/wild-agent/.env",
    )

    assert runtime_env.runtime_env_is_persistent() is True
    assert runtime_env.runtime_env_host_path() == "/opt/wild-agent/.env"
