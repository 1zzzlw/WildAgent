"""RAG chunk_id 引用提取和确定性校验。"""

from __future__ import annotations

import re
from dataclasses import dataclass


_CITATION_PATTERN = re.compile(r"\[引用:([^\]\s]+)\]")


@dataclass(frozen=True)
class CitationValidation:
    answer: str
    cited_chunk_ids: tuple[str, ...]
    invalid_chunk_ids: tuple[str, ...]
    appended_fallback: bool


def validate_answer_citations(
    answer: str,
    allowed_chunk_ids: list[str] | tuple[str, ...],
    *,
    append_fallback: bool = True,
    fallback_limit: int = 3,
) -> CitationValidation:
    """只保留本次真正注入 Context 的 ID，并在模型漏引时补确定性来源。"""

    allowed = list(dict.fromkeys(item for item in allowed_chunk_ids if item))
    allowed_set = set(allowed)
    raw_ids = list(dict.fromkeys(_CITATION_PATTERN.findall(str(answer or ""))))
    valid = [item for item in raw_ids if item in allowed_set]
    invalid = [item for item in raw_ids if item not in allowed_set]
    normalized_answer = _CITATION_PATTERN.sub(
        lambda match: match.group(0) if match.group(1) in allowed_set else "",
        str(answer or ""),
    ).rstrip()

    appended = False
    if append_fallback and not valid and allowed:
        valid = allowed[:max(1, fallback_limit)]
        citation_line = " ".join(f"[引用:{chunk_id}]" for chunk_id in valid)
        normalized_answer = f"{normalized_answer}\n\n参考分片：{citation_line}".strip()
        appended = True

    return CitationValidation(
        answer=normalized_answer,
        cited_chunk_ids=tuple(valid),
        invalid_chunk_ids=tuple(invalid),
        appended_fallback=appended,
    )
