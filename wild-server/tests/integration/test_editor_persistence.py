"""保护导入场景持久化和删除会话的可观察 API 行为。"""
import asyncio
import importlib
import sys
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app.api.http import blueprints as scenes
from app.api.http import sessions
from app.infrastructure.persistence.repositories.designs import DesignRepository
from app.application.generation.jobs import GenerationJobService
from app.infrastructure.persistence.repositories.blueprints import blueprint_repository
from app.infrastructure.persistence.repositories.conversations import conversations


@pytest.fixture
def workspace(tmp_path, monkeypatch, storage):
    scenes_dir = tmp_path/'scenes'
    repository = importlib.import_module('app.infrastructure.persistence.repositories.designs')
    monkeypatch.setattr(repository, 'design_repository', DesignRepository())
    jobs = GenerationJobService(tmp_path/'jobs.sqlite3')
    monkeypatch.setattr(importlib.import_module('app.application.generation.jobs'), 'generation_job_service', jobs)
    app = FastAPI()
    from app.api.exception_handlers import install_exception_handlers
    install_exception_handlers(app)
    app.include_router(scenes.router)
    app.include_router(sessions.router)
    from app.application.accounts import hash_password
    from app.infrastructure.persistence.repositories.accounts import accounts
    from app.infrastructure.persistence.schema import users
    administrator = accounts.create('editor-test-admin', 'editor-test-admin@example.com', hash_password('editor-test-password'))
    with storage.begin() as conn:
        conn.execute(users.update().where(users.c.id == administrator['id']).values(identity=2))
    @app.middleware("http")
    async def administrator_context(request, call_next):
        request.state.user = {"id": administrator['id'], "role": "editor", "identity": 2}
        return await call_next(request)
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
            owner_id = blueprint_repository.get('2026-10-22/session_101_import.wild')['owner_id']
            assert len(blueprint_repository.list(owner_id)) == 1
            assert not list(directory.rglob('*.wild'))
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
        saved = 'session_101_villa.wild'
        blueprint_repository.save(saved, blueprint())
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
            response = await client.delete('/api/sessions/session_101')
            assert response.status_code == 409
            assert blueprint_repository.get(saved) is not None
            assert (await jobs.get_job('req_active')).status == status
        await jobs.shutdown()
    asyncio.run(run())


def test_stale_history_does_not_block_delete_or_touch_similar_session(workspace):
    async def run():
        app, directory, jobs = workspace
        await jobs.initialize()
        await jobs._insert_job('req_done', 'session_101', {})
        await jobs.publish_event('req_done', {'type': 'agent_reply', 'content': '完成'})
        conversations.write('session_101', {'turns': [{'request_id': 'stale', 'status': 'waiting_review'}]})
        target = 'session_101_villa.wild'
        other = 'session_1010_villa.wild'
        blueprint_repository.save(target, blueprint())
        blueprint_repository.save(other, blueprint('其他建筑'))
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
            assert (await client.delete('/api/sessions/session_101')).status_code == 200
            assert blueprint_repository.get(target) is None and blueprint_repository.get(other) is not None
            assert conversations.read('session_101') is None
            assert await jobs.get_job('req_done') is None
            assert await jobs.events_after('req_done', 0) == []
            assert (await client.delete('/api/sessions/session_101')).status_code == 200
        await jobs.shutdown()
    asyncio.run(run())
