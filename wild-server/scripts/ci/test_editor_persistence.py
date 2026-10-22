"""保护导入场景持久化和删除会话的可观察 API 行为。"""
import asyncio
import importlib
import json
import sys
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app.api import scenes, sessions
from app.design.repository import DesignRepository
from app.services.generation_job_service import GenerationJobService


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    scenes_dir = tmp_path/'scenes'
    scenes_dir.mkdir()
    monkeypatch.setattr(scenes, 'SCENES_DIR', scenes_dir)
    monkeypatch.setattr(sessions, 'SCENES_DIR', scenes_dir)
    monkeypatch.setattr(sessions, 'SESSIONS_DIR', tmp_path/'sessions')
    repository = importlib.import_module('app.design.repository')
    monkeypatch.setattr(repository, 'design_repository', DesignRepository(tmp_path/'designs'))
    jobs = GenerationJobService(tmp_path/'jobs.sqlite3')
    monkeypatch.setattr(importlib.import_module('app.services.generation_job_service'), 'generation_job_service', jobs)
    app = FastAPI()
    app.include_router(scenes.router)
    app.include_router(sessions.router)
    return app, scenes_dir, jobs


def blueprint(name='导入建筑'):
    return {'meta': {'version': '1.1', 'type': 'building', 'name': name},
            'geometry': {'elements': [], 'components': []}, 'materials': {}}


def test_save_replace_list_reload(workspace):
    async def run():
        app, directory, jobs = workspace
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
            path = '/api/scenes/2026-10-22/session_101_import.wild'
            assert (await client.put(path, json=blueprint())).status_code == 200
            changed = blueprint('重命名后仍是同一文件')
            changed['editor'] = {'revision': 4}
            assert (await client.put(path, json=changed)).status_code == 200
            assert (await client.get(path)).json() == changed
            rows = (await client.get('/api/sessions')).json()
            assert rows[0]['filename'] == '2026-10-22/session_101_import.wild'
            assert len(list(directory.rglob('*.wild'))) == 1
        await jobs.shutdown()
    asyncio.run(run())


@pytest.mark.parametrize('status', ['running', 'waiting_review'])
def test_real_active_job_blocks_deletion_without_data_loss(workspace, status):
    async def run():
        app, directory, jobs = workspace
        await jobs.initialize()
        await jobs._insert_job('req_active', 'session_101', {})
        if status == 'waiting_review':
            async with __import__('aiosqlite').connect(jobs.database_path) as db:
                await db.execute("UPDATE generation_jobs SET status = 'waiting_review'")
                await db.commit()
        saved = directory/'session_101_villa.wild'
        saved.write_text(json.dumps(blueprint()), encoding='utf-8')
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
            response = await client.delete('/api/sessions/session_101')
            assert response.status_code == 409
            assert saved.exists()
            assert (await jobs.get_job('req_active')).status == status
        await jobs.shutdown()
    asyncio.run(run())


def test_stale_history_does_not_block_delete_or_touch_similar_session(workspace):
    async def run():
        app, directory, jobs = workspace
        await jobs.initialize()
        await jobs._insert_job('req_done', 'session_101', {})
        await jobs.publish_event('req_done', {'type': 'agent_reply', 'content': '完成'})
        sessions._write_session_meta('session_101', {'turns': [{'request_id': 'stale', 'status': 'waiting_review'}]})
        target = directory/'session_101_villa.wild'
        other = directory/'session_1010_villa.wild'
        target.write_text(json.dumps(blueprint()), encoding='utf-8')
        other.write_text(json.dumps(blueprint('其他建筑')), encoding='utf-8')
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
            assert (await client.delete('/api/sessions/session_101')).status_code == 200
            assert not target.exists() and other.exists()
            assert not sessions._session_path('session_101').exists()
            assert await jobs.get_job('req_done') is None
            assert await jobs.events_after('req_done', 0) == []
            assert (await client.delete('/api/sessions/session_101')).status_code == 200
        await jobs.shutdown()
    asyncio.run(run())
