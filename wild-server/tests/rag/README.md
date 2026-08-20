---
AIGC:
    Label: "1"
    ContentProducer: 001191440300708461136T1XGW3
    ProduceID: 120c9aab85e3ed979ff6cbda3bbcb633_9ef737039c4911f19046525400287e28
    ReservedCode1: ozHNaaW6m/pGwDB4qrqymMWVaqxY2qnGjy34hQGWTMe3wTC3AB6R266giim9RnJiClTOQKl6wG7LHDO3qKEHE/7QMZIJqXAGSEBFFby1f3yVhxISg/phI0E4VVbx0bQ/zHhNDnRNhhdfK1SFZrRJ24fWwGMo4foDb7B73OcPX5suK3YHyy8rbGTJ4Ps=
    ContentPropagator: 001191440300708461136T1XGW3
    PropagateID: 120c9aab85e3ed979ff6cbda3bbcb633_9ef737039c4911f19046525400287e28
    ReservedCode2: ozHNaaW6m/pGwDB4qrqymMWVaqxY2qnGjy34hQGWTMe3wTC3AB6R266giim9RnJiClTOQKl6wG7LHDO3qKEHE/7QMZIJqXAGSEBFFby1f3yVhxISg/phI0E4VVbx0bQ/zHhNDnRNhhdfK1SFZrRJ24fWwGMo4foDb7B73OcPX5suK3YHyy8rbGTJ4Ps=
---



# rag 包测试

## 用途

验证知识库 RAG 检索链路：语义分片、Chroma 索引增量同步、检索缓存与查询规划。保证 `.wild` 知识被正确切分、入库并可被高效检索。

## 覆盖范围

| 测试文件 | 作用 |
|---|---|
| `test_rag_semantic_chunking.py` | 语义分片：Markdown 标题分片、实体 metadata 继承、长度回退策略、JSON/表格结构完整性、content_hash/body_hash 跨文件去重、检索上下文截断边界 |
| `test_rag_index_sync.py` | 索引同步：Chroma 增量同步（upsert/update/delete）、检索排序与过滤组合 |
| `test_rag_retrieval_cache.py` | 检索缓存：缓存命中/失效逻辑 |
| `test_query_planner.py` | 查询规划：查询改写、namespace/scope 与业务过滤组合 |

## 单独运行

在 `wild-server` 目录下（已激活 `.\.venv\Scripts\activate`）：

```bash
python -m pytest tests/rag -v
```

运行单个文件：

```bash
python -m pytest tests/rag/test_rag_semantic_chunking.py -v
```
## 测试文件详解与结果解读

| 文件 | 用例 | 覆盖点 | 运行命令 |
|---|---|---|---|
| `test_rag_semantic_chunking.py` | 7 | 语义分片：知识路径+实体 metadata 覆盖每个长度分片；长度兜底保持 JSON/表格结构完整；README 推断为 index scope；空容器标题不入索引；body_hash 忽略重复知识路径前缀；检索合并 namespace/scope/业务过滤；上下文上限保持分片原子 | `python -m pytest tests/rag/test_rag_semantic_chunking.py -v` |
| `test_rag_index_sync.py` | 7 | 索引同步：supported 维护者分片可压过 nearby experimental；retrieve_many 每查询保留一条；parent 相邻分片扩展；未变分片跳过 embedding upsert；metadata 变更不重嵌入；变更分片删旧 id 插新 id；删除文档清理陈旧分片 | `python -m pytest tests/rag/test_rag_index_sync.py -v` |
| `test_rag_retrieval_cache.py` | 4 | 检索缓存：相同输入缓存键稳定；filter / per-query / 知识库版本变化时键变化 | `python -m pytest tests/rag/test_rag_retrieval_cache.py -v` |
| `test_query_planner.py` | 5 | 查询规划：商业别名解析不虚构事实；显式过滤优先于推断组件类型；LLM 改写保留 raw query 且只用白名单 metadata；loader retrieve_many 带 metadata filter；重构后索引富化已移除 | `python -m pytest tests/rag/test_query_planner.py -v` |

**预期结果与结果怎么看**：
- 四个文件合计 23 个用例，标准环境下应全部 `PASSED`（末尾 `23 passed`）。
- 失败定位：`FAILED tests/rag/<文件>.py::<类名>::<函数>`。若 `test_rag_semantic_chunking.py` 失败，多为分片策略/知识路径前缀变化；`test_rag_index_sync.py` 失败多为增量 upsert 逻辑回归。重跑单条：
  ```bash
  python -m pytest tests/rag/test_rag_index_sync.py::RAGIndexSyncTest::test_unchanged_chunks_skip_embedding_upsert -v
  ```
- 提示：本子包测试使用临时索引/临时 Chroma，不污染 `storage/chroma` 线上索引，可放心反复运行。
*（内容由AI生成，仅供参考）*
*（内容由AI生成，仅供参考）*
