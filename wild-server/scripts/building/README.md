---
AIGC:
    Label: "1"
    ContentProducer: 001191440300708461136T1XGW3
    ProduceID: 120c9aab85e3ed979ff6cbda3bbcb633_97cdcb139c4911f1b930525400e6dd8f
    ReservedCode1: Leq17EJQ85yVG4ikP7kFXhvh7Hldswau4Q3DCMV10x9yUWL96eYu8EeyZVOI1neGKZQYvuv49Ceaz3vHzznfzKQss+s4NiqIfU72nctsUU5g4D1C3YYCyrc75pFhmh9jHc8Jb1MgUKDg+RQUDVM+aRV1q550PdDiMylz6arDqY7RBA4cdVcJrYWDcIY=
    ContentPropagator: 001191440300708461136T1XGW3
    PropagateID: 120c9aab85e3ed979ff6cbda3bbcb633_97cdcb139c4911f1b930525400e6dd8f
    ReservedCode2: Leq17EJQ85yVG4ikP7kFXhvh7Hldswau4Q3DCMV10x9yUWL96eYu8EeyZVOI1neGKZQYvuv49Ceaz3vHzznfzKQss+s4NiqIfU72nctsUU5g4D1C3YYCyrc75pFhmh9jHc8Jb1MgUKDg+RQUDVM+aRV1q550PdDiMylz6arDqY7RBA4cdVcJrYWDcIY=
---



# building/ — 建筑类型分类工具

建筑类型（`building_category`）元数据相关的批量更新与验证脚本，服务于知识库中建筑类型文档的分类检索。

## 文件清单

| 文件 | 作用 |
|---|---|
| `update_building_category.py` | 批量遍历知识库建筑类型文档，根据文件路径与内容特征为 frontmatter 添加 `building_category` 元数据（residential / commercial / industrial / mixed_use 等）。 |
| `test_building_category.py` | 验证带 `building_category` 过滤的 RAG 检索：同步知识库索引后，用多组查询 + 过滤条件检查检索结果分类是否命中预期。 |

## 运行方式

需在 **wild-server 根目录** 下运行，并设置 `PYTHONPATH="."`：

```powershell
cd E:\AgentProject\WildAgent\wild-server
$env:PYTHONPATH="."
.\.venv\Scripts\python.exe scripts\building\update_building_category.py --help
.\.venv\Scripts\python.exe scripts\building\test_building_category.py
```

或使用 uv（免手动激活）：

```powershell
$env:PYTHONPATH="."; uv run --no-project python scripts/building/test_building_category.py
```

## 使用流程

1. 编辑 `storage/knowledge_base/...` 中的建筑类型文档；
2. 如需补充分类元数据，运行 `update_building_category.py`；
3. 运行 `test_building_category.py` 验证分类检索命中。

## 各脚本详解

### `update_building_category.py`

- **用途**：批量遍历 `storage/knowledge_base/building_types/` 下 Markdown，按文件路径与内容特征为 frontmatter 添加 `building_category` 元数据（residential / commercial / industrial / mixed_use 等），供 RAG 检索做业务过滤。
- **参数**：无 CLI 参数（默认处理固定知识库目录）。
- **运行**：
  ```powershell
  cd E:\AgentProject\WildAgent\wild-server
  $env:PYTHONPATH="."
  .\.venv\Scripts\python.exe scripts\building\update_building_category.py
  ```
- **输出怎么看**：
  ```
  ✅ 已更新: building_types\catalog\villas.md   ← 该文件已补上/更新 building_category
  ⏭️  跳过: building_types\catalog\README.md    ← 文件无对应建筑类型（如目录 README），无需更新
  ❌ 失败: xxx.md - <错误>                        ← 写入失败，需按错误排查
  总结: 更新 N 个文件, 跳过 M 个文件              ← N+M 应与目标文件数一致
  ```
- **注意**：脚本只改 frontmatter，不重分片；改完需触发索引同步（重启服务或跑 `rag/check_sync_status.py` 确认入库）。

### `test_building_category.py`

- **用途**：验证"带 `building_category` 过滤的 RAG 检索"是否生效：同步知识库索引后，用多组查询 + 过滤条件检查检索结果分类是否命中预期。
- **注意**：这是 **异步验证脚本**（非 pytest 用例文件），直接 `python` 运行，不要用 `pytest` 运行。
- **运行**：
  ```powershell
  cd E:\AgentProject\WildAgent\wild-server
  $env:PYTHONPATH="."
  .\.venv\Scripts\python.exe scripts\building\test_building_category.py
  ```
- **输出怎么看**：控制台逐组打印查询与命中文件的分类；**预期结果**：每个查询在对应 `building_category` 过滤下命中预期的建筑类型文档（如住宅类查询命中 villas / cabins / courtyards 等 residential 文档），无过滤时也能召回但排序体现分类。若某组 0 命中或命中错误分类，说明 metadata 未落库或过滤条件与知识库 `building_category` 取值不一致。
- **运行前**：需先确保索引已同步（`check_sync_status.py` 的总片段数正常）。
*（内容由AI生成，仅供参考）*
*（内容由AI生成，仅供参考）*
