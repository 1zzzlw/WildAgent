"""Spec 模块 —— 规范文档加载

公共兼容入口当前导出 SpecLoader 与 FileSpecLoader。
RAGSpecLoader、分片器及 embedding 工厂由业务层从 agent.rag.loader 显式导入，
避免只需要文件兜底加载器的调用方被迫感知 Chroma 相关实现。
"""
from agent.rag.loader import SpecLoader
from agent.rag.loader import FileSpecLoader

__all__ = ["SpecLoader", "FileSpecLoader"]
