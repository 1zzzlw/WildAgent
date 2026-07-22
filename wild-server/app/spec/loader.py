"""
Spec Document Loader —— 规范文档加载器

职责：加载 WILD 语言规范文档，注入到 LLM System Prompt 中。

设计原则：
  - 接口不变，实现可替换
  - 现在：FileSpecLoader（os.read 直接读文件）
  - 以后：RAGSpecLoader（向量检索，不改调用方一行代码）

升级路径：
  class RAGSpecLoader(SpecLoader):
      def __init__(self, retriever):
          self.retriever = retriever
      def load(self, query: str = "") -> str:
          docs = self.retriever.retrieve(query)
          return "\\n\\n---\\n\\n".join(docs)
"""
import time
from pathlib import Path


class SpecLoader:
    """规范文档加载器抽象基类

    所有加载器都必须实现 load() 和 list_sources()。
    调用方只依赖这两个方法，不需要知道底层实现。
    """

    def load(self) -> str:
        """加载所有规范文档，返回拼接后的文本"""
        raise NotImplementedError

    def list_sources(self) -> list[str]:
        """返回已加载的文档路径或来源标识"""
        raise NotImplementedError


class FileSpecLoader(SpecLoader):
    """从文件系统直接读取规范文档（当前阶段使用）

    用法:
        loader = FileSpecLoader([
            "/path/to/SPEC.md",
            "/path/to/PRIMITIVES.md",
        ])
        spec_text = loader.load()
    """

    def __init__(self, paths: list[str]):
        self._paths = [Path(p) for p in paths]
        self._loaded_at: float | None = None

    def load(self) -> str:
        """读取所有文件并拼接

        每个文件以 "## {文件名}" 为标题，用分隔线连接。
        不存在的文件会插入警告注释，不中断加载。
        """
        texts: list[str] = []
        for p in self._paths:
            if p.exists():
                text = p.read_text(encoding="utf-8")
                # 用文件名（不含扩展名）作为章节标题
                texts.append(f"## {p.stem}\n\n{text}")
            else:
                texts.append(
                    f"<!-- 警告：规范文档不存在: {p} -->\n"
                    f"## {p.stem}\n\n（文件缺失，请检查路径配置）"
                )
        self._loaded_at = time.time()
        return "\n\n---\n\n".join(texts)

    def list_sources(self) -> list[str]:
        """返回所有配置的文档路径"""
        return [str(p) for p in self._paths]

    @property
    def loaded_at(self) -> float | None:
        """最近一次加载的时间戳（用于监控/调试）"""
        return self._loaded_at
