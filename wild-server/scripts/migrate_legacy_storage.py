"""可重复的共享历史迁移。仅插入缺失记录，不覆盖数据库数据、不改动源文件。"""
import argparse
import sys
from collections import defaultdict
from contextlib import closing
import json
from pathlib import Path
import re
import sqlite3
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pymysql
from langgraph.checkpoint.mysql.pymysql import PyMySQLSaver
from langgraph.checkpoint.sqlite import SqliteSaver
from sqlalchemy import insert, select

from app.design.contracts import DesignDocument
from app.infrastructure.database import database
from app.infrastructure.schema import designs, events, jobs
from app.repositories.blueprints import blueprint_repository, session_for_filename, validate_filename
from app.repositories.conversations import conversations, ensure_session, now_ms
from config import config


def _shared(session_id: str):
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", session_id):
        raise ValueError("历史会话标识格式无效")
    exists, owner = conversations.owner(session_id)
    if exists and owner is not None:
        raise ValueError("历史标识与私人会话冲突，迁移已停止")


def migrate_legacy(source: Path, *, apply: bool = False) -> dict:
    source = source.resolve(strict=True)
    counts = {"sessions": 0, "blueprints": 0, "design_versions": 0, "jobs": 0, "events": 0, "checkpoints": 0}
    # 先完整解析文件，格式错误在任何数据库写入前暴露。
    session_values, blueprint_values, design_values = [], [], {}
    for path in sorted((source / "sessions").glob("*.json")):
        value = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(value, dict):
            raise ValueError(f"历史会话不是对象: {path.name}")
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", path.stem):
            raise ValueError("历史会话标识格式无效")
        session_values.append((path.stem, value))
    for path in sorted((source / "scenes").rglob("*.wild")):
        filename = validate_filename(path.relative_to(source / "scenes").as_posix())
        value = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(value, dict) or not isinstance(value.get("meta"), dict) or not isinstance(value.get("geometry"), dict):
            raise ValueError(f"历史蓝图结构无效: {filename}")
        blueprint_values.append((filename, value, int(path.stat().st_mtime * 1000)))
    paths = [*sorted((source / "designs" / "history").rglob("revision_*.json")),
             *sorted((source / "designs").glob("*.design.json"))]
    for path in paths:
        document = DesignDocument.model_validate_json(path.read_text(encoding="utf-8-sig"))
        design_values[(document.session_id, document.revision)] = document.model_dump(mode="json")
    counts.update(sessions=len(session_values), blueprints=len(blueprint_values), design_versions=len(design_values))
    if apply:
        for sid, value in session_values:
            _shared(sid)
            if conversations.read(sid) is None:
                conversations.write(sid, value)
        for filename, value, timestamp in blueprint_values:
            sid = session_for_filename(filename)
            if sid:
                _shared(sid)
            if blueprint_repository.get(filename) is None:
                blueprint_repository.save(filename, value, timestamp=timestamp)
        for (sid, revision), value in sorted(design_values.items()):
            _shared(sid)
            with database.engine.begin() as conn:
                ensure_session(conn, sid)
                exists = conn.execute(select(designs.c.revision).where(designs.c.session_id == sid,
                    designs.c.revision == revision)).first()
                if not exists:
                    conn.execute(insert(designs).values(session_id=sid, revision=revision,
                        document_json=value, resolved_json={}, updated_at=now_ms()))
    sqlite_path = source / "sessions" / "langgraph_checkpoints.sqlite3"
    if sqlite_path.is_file():
        _copy_runtime(sqlite_path, apply, counts)
    return {"mode": "applied" if apply else "dry_run", "source_unchanged": True, "records_found": counts}


def _copy_runtime(path: Path, apply: bool, counts: dict):
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as source:
        source.row_factory = sqlite3.Row
        tables = {row[0] for row in source.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for name in ("generation_jobs", "generation_events"):
            if name not in tables:
                continue
            target = jobs if name == "generation_jobs" else events
            column_types = {row[1]: row[2].upper() for row in source.execute(f"PRAGMA table_info({name})")}
            for row in source.execute(f"SELECT * FROM {name}"):
                counts["jobs" if target is jobs else "events"] += 1
                if not apply:
                    continue
                value = dict(row)
                if target is jobs:
                    _shared(value["session_id"])
                    # 迁移历史不触发旧任务再次调用模型。
                    if value["status"] in {"running", "waiting_review"}:
                        value.update(status="stopped", error="数据库迁移时保留为已停止任务")
                for key in ("created_at", "updated_at"):
                    if key in value:
                        multiplier = 1000 if column_types.get(key) in {"REAL", "FLOAT", "DOUBLE"} else 1
                        value[key] = int(value[key] * multiplier)
                with database.engine.begin() as conn:
                    if target is jobs:
                        ensure_session(conn, value["session_id"])
                    condition = target.c.request_id == value["request_id"]
                    if target is events:
                        condition &= target.c.seq == value["seq"]
                    if conn.execute(select(target.c.request_id).where(condition)).first() is None:
                        conn.execute(insert(target).values(**value))
        if "checkpoints" not in tables:
            return
        counts["checkpoints"] = source.execute("SELECT count(*) FROM checkpoints").fetchone()[0]
        if not apply:
            return
        # 通过 SQLite backup 获得含 WAL 的一致快照，读取器不接触原库。
        with tempfile.TemporaryDirectory(prefix="wild-checkpoint-migration-") as directory:
            snapshot = Path(directory) / "checkpoints.sqlite3"
            with closing(sqlite3.connect(snapshot)) as copied:
                source.backup(copied)
            cfg = config.mysql
            with pymysql.connect(host=cfg.host, port=cfg.port, user=cfg.username,
                password=cfg.password.get_secret_value(), database=cfg.database,
                charset="utf8mb4", autocommit=True) as connection:
                target = PyMySQLSaver(connection)
                with SqliteSaver.from_conn_string(str(snapshot)) as old:
                    for entry in old.list(None):
                        if target.get_tuple(entry.config) is not None:
                            continue
                        base = entry.parent_config or {"configurable": {
                            "thread_id": entry.config["configurable"]["thread_id"],
                            "checkpoint_ns": entry.config["configurable"].get("checkpoint_ns", "")}}
                        saved = target.put(base, entry.checkpoint, entry.metadata, entry.checkpoint["channel_versions"])
                        pending = defaultdict(list)
                        for task_id, channel, value in entry.pending_writes or []:
                            pending[task_id].append((channel, value))
                        for task_id, values in pending.items():
                            target.put_writes(saved, values, task_id)


def main():
    parser = argparse.ArgumentParser(description="将旧磁盘资料迁入已建表的 MySQL；不执行建表 SQL")
    parser.add_argument("--source", type=Path, default=Path("storage"))
    parser.add_argument("--apply", action="store_true", help="默认仅检查；指定后才写入业务数据")
    args = parser.parse_args()
    try:
        print(migrate_legacy(args.source, apply=args.apply))
    finally:
        database.close()


if __name__ == "__main__":
    main()
