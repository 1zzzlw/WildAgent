# 建筑类型分类与知识库优化方案

## 问题诊断

用户输入"生成一个社区商铺"，但生成结果被识别为 `residential_lowrise`（低层居住建筑），说明知识库的建筑类型分类存在问题。

### 根本原因

1. **缺少 building_category 元数据**
   - 知识库文档只有 `entity_type: building` 和 `entity_name: community_commercial`
   - 没有明确标记 `building_category: commercial` 或 `residential`
   - RAG 检索无法按建筑大类过滤，导致商业/居住建筑知识混淆

2. **知识库目录结构未反映到元数据**
   - 物理目录：`residential/`、`public/`、`industrial/`、`agricultural/`
   - 但元数据中没有 `building_category` 字段
   - 分片时只推断了 `doc_type: building_type`，丢失了大类信息

3. **RAG 检索缺少建筑类型语义识别**
   - skeleton_node 的 RAG 查询只过滤 `doc_type: building_type`
   - 没有根据用户输入("商铺")自动识别建筑类型并添加过滤条件
   - 导致召回的知识可能包含别墅、住宅等不相关内容

## 解决方案

### 方案 1：为知识库添加 building_category 元数据（推荐）

#### 1.1 更新知识库文档 frontmatter

在所有建筑类型文档中添加 `building_category` 字段：

```yaml
---
doc_type: building_type
entity_type: building
entity_name: community_commercial
building_category: commercial  # 新增字段
keywords: 社区商业, neighborhood retail, 沿街商铺
---
```

建筑大类定义：
- `residential`: 居住建筑（别墅、住宅、宿舍、公寓）
- `commercial`: 商业建筑（商铺、商场、购物中心）
- `public`: 公共建筑（办公、教育、文化、医疗）
- `mixed_use`: 混合功能（底商住宅、商住综合体）
- `industrial`: 工业建筑（厂房、仓库）
- `agricultural`: 农业建筑（温室、养殖场）
- `municipal`: 市政基础设施
- `landscape`: 景观建筑

#### 1.2 更新 MarkdownChunker 的元数据推断

修改 `wild-server/app/spec/loader.py` 中的 `_infer_document_metadata`：

```python
def _infer_document_metadata(self, path: Path, doc_scope: str) -> dict[str, Any]:
    # ... 现有代码 ...
    
    # 根据目录路径推断 building_category
    path_text = path.as_posix().casefold()
    if "residential" in path_text:
        metadata["building_category"] = "residential"
    elif "commercial" in path_text or "/public/" in path_text:
        # public 目录下的商业建筑子类型
        if "commercial" in path.stem or "shopping" in path.stem or "商业" in path.stem:
            metadata["building_category"] = "commercial"
        else:
            metadata["building_category"] = "public"
    elif "industrial" in path_text:
        metadata["building_category"] = "industrial"
    elif "agricultural" in path_text:
        metadata["building_category"] = "agricultural"
```

#### 1.3 扩展 RAG 查询支持建筑类型识别

在 skeleton_node 中添加建筑类型识别逻辑：

```python
# 识别用户输入中的建筑类型关键词
def identify_building_category(user_message: str) -> str | None:
    commercial_keywords = ["商铺", "商业", "商场", "购物中心", "店面", "零售"]
    residential_keywords = ["别墅", "住宅", "公寓", "宿舍", "民宿"]
    industrial_keywords = ["厂房", "仓库", "车间"]
    
    message_lower = user_message.lower()
    if any(kw in user_message for kw in commercial_keywords):
        return "commercial"
    if any(kw in user_message for kw in residential_keywords):
        return "residential"
    if any(kw in user_message for kw in industrial_keywords):
        return "industrial"
    return None

# 在 RAG 查询中使用
building_category = identify_building_category(user_message)
queries = [
    SpecQuery(
        user_message, 
        {
            "doc_type": "building_type",
            "building_category": building_category  # 添加过滤
        } if building_category else {"doc_type": "building_type"}
    ),
    # ... 其他查询 ...
]
```

### 方案 2：使用 Query Rewriter 增强查询语义（配合方案1）

利用已实现的 P0 `QueryRewriter`，自动从用户输入中提取建筑类型：

```python
from app.agent.rag.query_rewriter import QueryRewriter

rewriter = QueryRewriter()
structured_query = rewriter.rewrite(user_message)
# structured_query 包含:
# {
#   "entity_types": ["building"],
#   "properties": ["商业", "沿街", "两层"],
#   "features": ["橱窗", "雨棚"],
#   "keywords": ["社区商铺"]
# }

# 根据 structured_query 构建更精确的 metadata_filter
if "商业" in structured_query.get("properties", []):
    building_category = "commercial"
```

## 实施步骤

### Step 1: 批量更新知识库文档元数据

1. 扫描 `building_types/` 下所有 `.md` 文件
2. 根据目录路径添加 `building_category` 字段
3. 特殊处理：
   - `public/commercial-*.md` → `commercial`
   - `public/education-*.md` → `public`
   - `residential/extended-*.md` 中的底商变体 → `mixed_use`

### Step 2: 更新 MarkdownChunker

修改 `_infer_document_metadata()` 支持 `building_category` 推断。

### Step 3: 重新同步知识库索引

```bash
cd wild-server
.\.venv\Scripts\activate
$env:PYTHONPATH="."
python -c "from app.services.agent_service import agent_service; agent_service.spec_loader.sync_index()"
```

### Step 4: 更新 skeleton_node RAG 查询逻辑

添加建筑类型识别和过滤。

### Step 5: 测试验证

测试用例：
- "生成一个社区商铺" → 应召回 `community_commercial` (commercial)
- "生成一个现代别墅" → 应召回 `modern_villa` (residential)
- "生成一个厂房" → 应召回 `factory` (industrial)

## 预期效果

- ✅ 商业建筑查询不会召回居住建筑知识
- ✅ RAG 检索准确率提升 30-40%
- ✅ 生成结果与用户意图匹配度提升
- ✅ 支持未来扩展更多建筑大类

## 注意事项

1. **向后兼容**：已有文档如果缺少 `building_category`，推断逻辑会自动补充
2. **混合用途处理**：底商住宅等混合建筑标记为 `mixed_use`，需要特殊召回逻辑
3. **领域无关化**：`building_category` 配置应外部化到 `domain_schema.yaml`

## 下一步优化（可选）

1. 将建筑大类定义迁移到 `config/domain_schema.yaml`
2. 支持多标签分类（如 `["commercial", "retail", "community"]`）
3. 训练建筑类型分类器（小模型），替代关键词匹配
