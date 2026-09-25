"""外部知识的**离线**入库通道。

代码里不再有"运行期联网检索"这一步：在线研究节点随旧计划层一起删除（它唯一的
消费者是计划研究）。保留下来的是离线补课链路——把外部资料整理成声明、写进 staging，
再由 `scripts/kb/promote_staged.py` 人工审核后并入知识库。下一次生成就能检索到，
不需要在请求链路上联网，也就不会有"结果不可复现"的问题。
"""

from app.agent.knowledge.web.knowledge_claims import KnowledgeClaim, map_claim_to_capability
from app.agent.knowledge.web.staging import (
    STAGING_ROOT,
    claim_to_markdown,
    list_staged_files,
    write_claim_to_staging,
)

__all__ = [
    "KnowledgeClaim",
    "STAGING_ROOT",
    "claim_to_markdown",
    "list_staged_files",
    "map_claim_to_capability",
    "write_claim_to_staging",
]
