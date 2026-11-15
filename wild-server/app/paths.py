"""后端资源根目录；模块迁移不改变配置、知识库和存储的定位。"""
from pathlib import Path

SERVER_ROOT = Path(__file__).resolve().parent.parent
PROJECT_ROOT = SERVER_ROOT.parent
STORAGE_ROOT = SERVER_ROOT / "storage"
