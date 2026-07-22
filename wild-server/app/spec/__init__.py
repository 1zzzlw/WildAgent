"""Spec 模块 —— 规范文档加载

现在：FileSpecLoader (os.read)
以后：RAGSpecLoader (向量检索)
"""
from app.spec.loader import SpecLoader, FileSpecLoader

__all__ = ["SpecLoader", "FileSpecLoader"]
