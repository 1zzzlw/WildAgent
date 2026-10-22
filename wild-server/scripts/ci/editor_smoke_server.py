"""仅供本地浏览器回归：使用真实应用路由，所有会话/设计/任务写入独立临时目录。"""
import importlib
import os
os.environ.setdefault('SystemRoot', r'C:\Windows')
os.environ.setdefault('WINDIR', r'C:\Windows')
os.environ['RAG__ENABLED'] = 'false'
os.environ['LANGSMITH_TRACING'] = 'false'
import sys
import tempfile
from pathlib import Path
import uvicorn

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
temporary = tempfile.TemporaryDirectory(prefix='wild-editor-smoke-')
storage = Path(temporary.name)
parser = importlib.import_module('app.utils.blueprint_parser')
parser.SCENES_DIR = storage/'scenes'
scenes = importlib.import_module('app.api.scenes')
sessions = importlib.import_module('app.api.sessions')
scenes.SCENES_DIR = sessions.SCENES_DIR = storage/'scenes'
sessions.SESSIONS_DIR = storage/'sessions'
repository = importlib.import_module('app.design.repository')
repository.design_repository = repository.DesignRepository(storage/'designs')
jobs = importlib.import_module('app.services.generation_job_service')
jobs.generation_job_service = jobs.GenerationJobService(storage/'jobs.sqlite3')
from main import app


@app.get('/api/editor-smoke-storage')
async def storage_snapshot():
    import json
    return {p.relative_to(storage).as_posix(): json.loads(p.read_text(encoding='utf-8'))
            for p in storage.rglob('*.wild')}


if __name__ == '__main__':
    try:
        uvicorn.run(app, host='127.0.0.1', port=18080, log_level='warning')
    finally:
        temporary.cleanup()
