"""知识文档的确定性分片与元数据解析，不包含向量库或模型调用。"""
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any
from loguru import logger
from app.domain.knowledge.policy import KNOWLEDGE_REVISION
from config import config


def _normalize_path(path: Path) -> str:
    """生成用于路径比较的绝对、大小写不敏感字符串。"""
    try:
        # resolve() 同时消解 ``..`` 和符号链接，避免同一路径有多种写法。
        return str(path.resolve()).casefold()
    except OSError:
        # 文件暂时无法解析时仍返回可比较的绝对路径，不中断知识库扫描。
        return str(path.absolute()).casefold()


@dataclass(frozen=True)
class SpecChunk:
    """写入 Chroma 的规范片段"""

    id: str
    document: str
    metadata: dict[str, str | int | float | bool]


class MarkdownChunker:
    """按标题和业务实体分块，并只对普通长文本执行长度兜底。"""

    _DOCUMENT_METADATA_FIELDS = (
        "doc_type",
        "doc_scope",
        "knowledge_layer",
        "entity_type",
        "entity_name",
        "topic",
        "wild_version",
        "status",
        "authority",
        "knowledge_revision",
        "knowledge_role",
        "applies_to",
        "primary_terms",
        "synonyms",
        # 兼容尚未迁移的外部文档；正式知识库不再写 legacy keywords。
        "keywords",
    )
    _HEADING_PATTERN = re.compile(r"^(#{1,5})\s+(.+?)\s*#*\s*$")
    _FENCE_PATTERN = re.compile(r"^\s*(```+|~~~+)")
    _TABLE_ROW_PATTERN = re.compile(r"^\s*\|.*\|\s*$")
    _TABLE_SEPARATOR_PATTERN = re.compile(
        r"^\s*\|(?:\s*:?-{3,}:?\s*\|)+\s*$"
    )

    def __init__(
        self,
        chunk_size: int = 900,
        chunk_overlap: int = 150,
        metadata_config_path: str | Path | None = None,
    ):
        self.chunk_size = max(200, chunk_size)
        # overlap 最多为分片长度的一半，避免相邻分片几乎完全重复。
        self.chunk_overlap = max(0, min(chunk_overlap, self.chunk_size // 2))
        self._metadata_config_path = (
            Path(metadata_config_path) if metadata_config_path is not None else None
        )
        self._metadata_config: dict[str, Any] | None = None
        try:
            from langchain_text_splitters import (
                MarkdownHeaderTextSplitter,
                RecursiveCharacterTextSplitter,
            )
        except ImportError as exc:
            raise RuntimeError(
                "缺少 langchain-text-splitters 依赖，请先安装 wild-server 依赖"
            ) from exc

        self._markdown_splitter = MarkdownHeaderTextSplitter(
            # 标题内容会保留在 page_content 中，同时标题值写入 metadata。
            headers_to_split_on=[
                ("#", "h1"),
                ("##", "h2"),
                ("###", "h3"),
                ("####", "h4"),
                ("#####", "h5"),
            ],
            strip_headers=False,
        )
        self._text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            length_function=len,
            is_separator_regex=False,
        )

    def split_file(
        self,
        path: Path,
        namespace: str,
        doc_scope: str = "generation",
    ) -> list[SpecChunk]:
        if not path.exists():
            return []

        text = path.read_text(encoding="utf-8")
        frontmatter, body = self._extract_frontmatter(text)
        body, entity_metadata = self._extract_entity_metadata(body)
        # 第一阶段只按标题边界切分，不在不同标题或业务实体之间合并。
        documents = self._markdown_splitter.split_text(body)
        inferred_metadata = self._infer_document_metadata(path, doc_scope)
        # 配置只提供路径级默认值；文档 frontmatter 始终拥有最高优先级。
        inferred_metadata.update(self._path_rule_metadata(path))
        declared_source = frontmatter.get("source")
        for field in self._DOCUMENT_METADATA_FIELDS:
            if field in frontmatter:
                inferred_metadata[field] = frontmatter[field]
        self._normalize_term_metadata(inferred_metadata)

        chunks: list[SpecChunk] = []
        # mtime 仅供追踪来源状态，不参与分片 ID 或判重。
        # Chroma 会把浮点 metadata 归一化到约 6 位小数；预先对齐可避免每次启动
        # 都把仅有亚微秒差异的 mtime 误判为 metadata 变化。
        mtime = round(path.stat().st_mtime, 6)
        source_path = path.resolve().as_posix()
        # source_hash 区分不同文件；相同内容位于不同文件时仍会拥有不同 ID。
        source_hash = hashlib.sha256(f"{namespace}:{source_path}".encode("utf-8")).hexdigest()[:12]

        chunk_index = 0
        for section_index, document in enumerate(documents):
            heading_path = self._heading_path(document.metadata)
            heading = " > ".join(heading_path) if heading_path else path.stem
            section_metadata = dict(inferred_metadata)
            # 实体 metadata 按标题层级继承；更深层标题上的声明覆盖祖先声明。
            for depth in range(1, len(heading_path) + 1):
                section_metadata.update(entity_metadata.get(heading_path[:depth], {}))
            self._normalize_term_metadata(section_metadata)

            context_line = f"> 知识路径：{heading}"
            section_parts = [
                part
                for part in self._split_section(document.page_content, context_line)
                if self._has_meaningful_payload(part)
            ]
            parent_digest = hashlib.sha256(
                f"{namespace}:{source_path}:{section_index}:{heading}".encode("utf-8")
            ).hexdigest()[:16]
            parent_chunk_id = f"{namespace}:{source_hash}:section:{parent_digest}"

            for part_index, part in enumerate(section_parts):
                # 每个长度子片都重复标题路径，让脱离相邻片段后仍有完整语义上下文。
                content = f"{context_line}\n\n{part.strip()}".strip()
                if not content:
                    continue
                content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
                # body_hash 忽略祖先标题路径，但保留当前标题，识别跨文件重复业务正文。
                body_hash_source = self._body_hash_source(part, heading_path)
                body_hash = hashlib.sha256(body_hash_source.encode("utf-8")).hexdigest()[:16]
                chunk_id = f"{parent_chunk_id}:{part_index}:{content_hash}"
                metadata: dict[str, str | int | float | bool] = {
                    "namespace": namespace,
                    "source": path.name,
                    "source_file": path.name,
                    "path": source_path,
                    "_source": source_path,
                    "_extension": path.suffix.lower(),
                    "_file_name": path.name,
                    "heading": heading,
                    "heading_path": " > ".join(heading_path),
                    "parent_chunk_id": parent_chunk_id,
                    "part_index": part_index,
                    "chunk_index": chunk_index,
                    "content_hash": content_hash,
                    "body_hash": body_hash,
                    "mtime": mtime,
                }
                if declared_source:
                    metadata["declared_source"] = self._metadata_scalar(declared_source)
                for key, value in section_metadata.items():
                    metadata[key] = self._metadata_scalar(value)
                chunks.append(SpecChunk(id=chunk_id, document=content, metadata=metadata))
                chunk_index += 1

        return chunks

    def _extract_frontmatter(self, text: str) -> tuple[dict[str, Any], str]:
        """提取文件级 YAML 子集；不引入额外 YAML 运行时依赖。"""
        match = re.match(r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|$)", text, re.DOTALL)
        if not match:
            return {}, text
        return self._parse_metadata_lines(match.group(1).splitlines()), text[match.end():]

    def _extract_entity_metadata(
        self,
        text: str,
    ) -> tuple[str, dict[tuple[str, ...], dict[str, Any]]]:
        """移除 ``rag-meta`` 注释，并把它绑定到出现位置的标题路径。"""
        output: list[str] = []
        metadata_by_heading: dict[tuple[str, ...], dict[str, Any]] = {}
        heading_stack: list[str] = []
        lines = text.splitlines()
        index = 0
        active_fence: str | None = None

        while index < len(lines):
            line = lines[index]
            fence_match = self._FENCE_PATTERN.match(line)
            if fence_match:
                fence_char = fence_match.group(1)[0]
                if active_fence is None:
                    active_fence = fence_char
                elif fence_char == active_fence:
                    active_fence = None
                output.append(line)
                index += 1
                continue
            if active_fence is not None:
                output.append(line)
                index += 1
                continue

            heading_match = self._HEADING_PATTERN.match(line)
            if heading_match:
                level = len(heading_match.group(1))
                heading_stack = heading_stack[:level - 1]
                heading_stack.append(heading_match.group(2).strip())
                output.append(line)
                index += 1
                continue

            if line.strip().startswith("<!-- rag-meta"):
                metadata_lines: list[str] = []
                # 允许起始标记同行存在字段，也兼容规范模板中的独占一行写法。
                first_line = line.split("<!-- rag-meta", 1)[1]
                if "-->" in first_line:
                    metadata_lines.append(first_line.split("-->", 1)[0])
                    index += 1
                else:
                    if first_line.strip():
                        metadata_lines.append(first_line)
                    index += 1
                    while index < len(lines) and "-->" not in lines[index]:
                        metadata_lines.append(lines[index])
                        index += 1
                    if index < len(lines):
                        metadata_lines.append(lines[index].split("-->", 1)[0])
                        index += 1
                key = tuple(heading_stack)
                metadata_by_heading.setdefault(key, {}).update(
                    self._parse_metadata_lines(metadata_lines)
                )
                continue

            output.append(line)
            index += 1

        return "\n".join(output), metadata_by_heading

    def _parse_metadata_lines(self, lines: list[str]) -> dict[str, Any]:
        """解析 Skill 约定的扁平 ``key: value`` 和列表语法。"""
        result: dict[str, Any] = {}
        active_list_key: str | None = None
        for raw_line in lines:
            stripped = raw_line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if stripped.startswith("- ") and active_list_key:
                result.setdefault(active_list_key, []).append(
                    self._parse_metadata_scalar(stripped[2:])
                )
                continue
            if ":" not in stripped:
                active_list_key = None
                continue
            key, raw_value = stripped.split(":", 1)
            key = key.strip()
            raw_value = raw_value.strip()
            if not key:
                continue
            if not raw_value:
                result[key] = []
                active_list_key = key
            else:
                result[key] = self._parse_metadata_scalar(raw_value)
                active_list_key = None
        return result

    def _parse_metadata_scalar(self, value: str) -> Any:
        value = value.strip()
        if value == "[]":
            return []
        if value.startswith("[") and value.endswith("]"):
            return [
                item.strip().strip("'\"")
                for item in value[1:-1].split(",")
                if item.strip()
            ]
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        lowered = value.casefold()
        if lowered in {"true", "false"}:
            return lowered == "true"
        if "," in value:
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    def _normalize_term_metadata(self, metadata: dict[str, Any]) -> None:
        """把 legacy keywords 暴露为新字段，供旧的外部文档平滑迁移。"""
        if "keywords" not in metadata:
            return
        if "primary_terms" not in metadata and "synonyms" not in metadata:
            metadata["primary_terms"] = metadata["keywords"]
            metadata["synonyms"] = []

    def _path_rule_metadata(self, path: Path) -> dict[str, Any]:
        """按 config.yaml 合并 defaults 和命中的 mapping_rules。"""
        config_path = self._resolve_metadata_config_path(path)
        if config_path is None:
            return {}
        if self._metadata_config is None:
            try:
                import yaml

                loaded = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
                self._metadata_config = loaded if isinstance(loaded, dict) else {}
            except Exception as exc:
                logger.warning(f"[RAG] 无法读取知识库 metadata 配置 {config_path}: {exc}")
                self._metadata_config = {}

        config = self._metadata_config
        defaults = config.get("defaults", {})
        resolved = dict(defaults) if isinstance(defaults, dict) else {}
        try:
            relative_path = path.resolve().relative_to(config_path.parent.resolve()).as_posix()
        except ValueError:
            return resolved

        rules = config.get("mapping_rules", [])
        if not isinstance(rules, list):
            logger.warning(f"[RAG] {config_path} 的 mapping_rules 必须是列表")
            return resolved
        for rule in rules:
            if not isinstance(rule, dict):
                continue
            pattern = str(rule.get("path_pattern") or "").strip()
            rule_metadata = rule.get("metadata", {})
            if (
                pattern
                and isinstance(rule_metadata, dict)
                and PurePosixPath(relative_path).match(pattern)
            ):
                resolved.update(rule_metadata)
        return resolved

    def _resolve_metadata_config_path(self, path: Path) -> Path | None:
        if self._metadata_config_path is not None:
            return self._metadata_config_path if self._metadata_config_path.is_file() else None
        # 直接使用 MarkdownChunker 的脚本也能自动发现最近的知识库配置。
        for parent in path.resolve().parents:
            candidate = parent / "config.yaml"
            if candidate.is_file():
                self._metadata_config_path = candidate
                return candidate
        return None

    def _infer_document_metadata(self, path: Path, doc_scope: str) -> dict[str, Any]:
        """为旧文档提供可过滤的最小 metadata，新文档可用 frontmatter 覆盖。"""
        path_text = path.as_posix().casefold()
        stem = path.stem.casefold().replace("_", "-")
        metadata: dict[str, Any] = {
            "doc_type": "knowledge",
            "doc_scope": doc_scope,
            "knowledge_revision": KNOWLEDGE_REVISION,
            "knowledge_role": "capability",
            "knowledge_layer": "generation",
            "entity_type": "general",
            "entity_name": path.stem,
            "topic": "general",
        }
        if path.name.casefold() == "readme.md":
            metadata.update({
                "doc_type": "index",
                "doc_scope": "index",
                "knowledge_layer": "navigation",
                "entity_type": "index",
                "topic": "navigation",
            })
            return metadata
        if "recipes" in path_text:
            metadata.update({"doc_type": "recipe", "entity_type": "assembly"})
        elif "components" in path_text:
            metadata["doc_type"] = "component"
        elif "spec" in stem:
            metadata.update({
                "doc_type": "blueprint_spec",
                "knowledge_layer": "wild_schema",
                "entity_type": "schema",
            })

        entity_aliases = {
            "window": ("window", "windows", "窗"),
            "door": ("door", "doors", "门"),
            "wall": ("wall", "walls", "墙"),
            "roof": ("roof", "roofs", "屋顶"),
            "stair": ("stair", "stairs", "楼梯"),
            "railing": ("railing", "railings", "栏杆"),
            "opening": ("opening", "openings", "洞口"),
            "material": ("material", "materials", "材质"),
        }
        filename = path.name.casefold()
        for entity_type, aliases in entity_aliases.items():
            if any(alias in filename for alias in aliases):
                metadata["entity_type"] = entity_type
                break
        return metadata

    def _heading_path(self, metadata: dict[str, Any]) -> tuple[str, ...]:
        return tuple(
            str(metadata[key])
            for key in ("h1", "h2", "h3", "h4", "h5")
            if metadata.get(key)
        )

    def _split_section(self, text: str, context_line: str) -> list[str]:
        """把标题 section 拆成 Markdown 逻辑块，再进行受限的长度兜底。"""
        budget = max(80, self.chunk_size - len(context_line) - 2)
        logical_blocks = self._markdown_blocks(text.strip())
        parts: list[str] = []
        current: list[str] = []

        def flush() -> None:
            if current:
                parts.append("\n\n".join(current).strip())
                current.clear()

        for block_type, block in logical_blocks:
            if block_type == "table":
                candidates = self._split_table(block, budget)
            elif block_type == "code":
                candidates = [block]
            else:
                candidates = self._split_normal_block(block, budget)
            for candidate in candidates:
                # 超长代码块作为原子知识单元保留；由文档 linter 提示作者重构。
                if len(candidate) > budget:
                    flush()
                    parts.append(candidate.strip())
                    continue
                combined = "\n\n".join([*current, candidate]).strip()
                if current and len(combined) > budget:
                    flush()
                current.append(candidate.strip())
        flush()
        return [part for part in parts if part]

    def _has_meaningful_payload(self, text: str) -> bool:
        """过滤只有标题、空行或 Markdown 分隔线的目录壳 section。"""
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped or self._HEADING_PATTERN.match(stripped):
                continue
            if re.fullmatch(r"(?:-{3,}|\*{3,}|_{3,})", stripped):
                continue
            return True
        return False

    def _body_hash_source(self, text: str, heading_path: tuple[str, ...]) -> str:
        payload_lines = [
            line.strip()
            for line in text.splitlines()
            if line.strip() and not self._HEADING_PATTERN.match(line.strip())
        ]
        current_heading = heading_path[-1] if heading_path else ""
        return f"{current_heading}\n{'\n'.join(payload_lines)}".strip()

    def _markdown_blocks(self, text: str) -> list[tuple[str, str]]:
        """识别 fenced code、表格和普通段落，保护结构化内容不被字符切断。"""
        if not text:
            return []
        lines = text.splitlines()
        blocks: list[tuple[str, str]] = []
        normal_lines: list[str] = []
        index = 0

        def flush_normal() -> None:
            if normal_lines:
                value = "\n".join(normal_lines).strip()
                if value:
                    blocks.append(("normal", value))
                normal_lines.clear()

        while index < len(lines):
            fence_match = self._FENCE_PATTERN.match(lines[index])
            if fence_match:
                flush_normal()
                fence = fence_match.group(1)
                code_lines = [lines[index]]
                index += 1
                while index < len(lines):
                    code_lines.append(lines[index])
                    if re.match(rf"^\s*{re.escape(fence[0])}{{{len(fence)},}}\s*$", lines[index]):
                        index += 1
                        break
                    index += 1
                blocks.append(("code", "\n".join(code_lines).strip()))
                continue

            if (
                index + 1 < len(lines)
                and self._TABLE_ROW_PATTERN.match(lines[index])
                and self._TABLE_SEPARATOR_PATTERN.match(lines[index + 1])
            ):
                flush_normal()
                table_lines = [lines[index], lines[index + 1]]
                index += 2
                while index < len(lines) and self._TABLE_ROW_PATTERN.match(lines[index]):
                    table_lines.append(lines[index])
                    index += 1
                blocks.append(("table", "\n".join(table_lines).strip()))
                continue

            if not lines[index].strip():
                flush_normal()
            else:
                normal_lines.append(lines[index])
            index += 1
        flush_normal()
        return blocks

    def _split_normal_block(self, block: str, budget: int) -> list[str]:
        if len(block) <= budget:
            return [block]
        splitter = self._text_splitter
        if budget != self.chunk_size:
            from langchain_text_splitters import RecursiveCharacterTextSplitter

            splitter = RecursiveCharacterTextSplitter(
                chunk_size=budget,
                chunk_overlap=min(self.chunk_overlap, budget // 2),
                length_function=len,
                is_separator_regex=False,
            )
        return [part for part in splitter.split_text(block) if part.strip()]

    def _split_table(self, table: str, budget: int) -> list[str]:
        lines = table.splitlines()
        if len(lines) < 3 or len(table) <= budget:
            return [table]
        header = lines[:2]
        parts: list[str] = []
        current = list(header)
        for row in lines[2:]:
            candidate = "\n".join([*current, row])
            if len(candidate) > budget and len(current) > 2:
                parts.append("\n".join(current))
                current = [*header, row]
            else:
                current.append(row)
        if len(current) > 2:
            parts.append("\n".join(current))
        return parts or [table]

    def _metadata_scalar(self, value: Any) -> str | int | float | bool:
        """Chroma metadata 只接受标量，列表统一存为逗号分隔字符串。"""
        if isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, list):
            return ", ".join(str(item) for item in value)
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
