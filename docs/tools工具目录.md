# WildAgent 工具目录

本文档列出 WildAgent 项目中所有可用的开发工具、脚本和测试文件。

---

## 📂 目录结构

```
wild-server/
├── scripts/          # 开发和运维脚本
├── tests/            # 单元测试和集成测试
└── examples/         # 示例代码
```

---

## 🔧 Scripts（脚本工具）

位置：`wild-server/scripts/`

### 1. inspect_knowledge_chunks.py
**功能**：知识库分片检查工具

**用途**：
- 对 Markdown 文件或目录进行分片分析
- 查看每个分片的 metadata 和内容
- 统计分片数量、大小分布、实体分组等

**使用方法**：
```bash
# Windows PowerShell - 一行命令（推荐）
$env:PYTHONPATH="."; uv run --no-project python scripts/rag/inspect_knowledge_chunks.py storage/knowledge_base/building_types/residential/villas.md

# Windows PowerShell - 如果遇到中文乱码，先设置输出编码
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::UTF8
$env:PYTHONPATH="."; uv run --no-project python scripts/rag/inspect_knowledge_chunks.py storage/knowledge_base/building_types/residential/villas.md

# Linux/Mac - 一行命令
PYTHONPATH=. uv run --no-project python scripts/rag/inspect_knowledge_chunks.py storage/knowledge_base/building_types/residential/villas.md

# 检查整个目录
$env:PYTHONPATH="."; uv run --no-project python scripts/rag/inspect_knowledge_chunks.py storage/knowledge_base

# 显示完整内容
$env:PYTHONPATH="."; uv run --no-project python scripts/rag/inspect_knowledge_chunks.py storage/knowledge_base/components/windows.md --show-content

# 限制处理文件数量
$env:PYTHONPATH="."; uv run --no-project python scripts/rag/inspect_knowledge_chunks.py storage/knowledge_base --limit 5

# 自定义分片参数
$env:PYTHONPATH="."; uv run --no-project python scripts/rag/inspect_knowledge_chunks.py storage/knowledge_base --chunk-size 600 --chunk-overlap 100

# 表格形式输出（简洁模式）
$env:PYTHONPATH="."; uv run --no-project python scripts/rag/inspect_knowledge_chunks.py storage/knowledge_base --table

# 输出到文件
$env:PYTHONPATH="."; uv run --no-project python scripts/rag/inspect_knowledge_chunks.py storage/knowledge_base --output chunks.json
```

**参数说明**：
- `path`: Markdown 文件或目录路径（必需）
- `--namespace`: 命名空间，默认 `test`
- `--chunk-size`: 分片大小，默认 900
- `--chunk-overlap`: 分片重叠，默认 150
- `--show-content`: 显示完整内容
- `--table`: 表格形式输出
- `--no-summary`: 不显示统计摘要
- `--limit`: 限制处理的文件数量
- `--output`: 输出到 JSON 文件

**详细文档**：`scripts/README_INSPECT_CHUNKS.md`

---

### 2. check_sync_status.py
**功能**：检查知识库同步状态

**用途**：
- 查看 Chroma 向量数据库同步状态
- 对比本地文件和索引的差异
- 识别需要更新或删除的文档

**使用方法**：
```bash
python scripts/rag/check_sync_status.py
```

---

### 3. update_building_category.py
**功能**：批量更新建筑类型 metadata

**用途**：
- 为知识库文档添加 `building_category` 字段
- 支持 commercial、residential、public、industrial、agricultural

**使用方法**：
```bash
# 自动运行（已内置文件映射）
python scripts/building/update_building_category.py

# 查看帮助
python scripts/building/update_building_category.py --help
```

---

### 4. test_building_category.py
**功能**：测试建筑类型分类功能

**用途**：
- 验证 RAG 检索时的建筑类型过滤
- 测试不同查询的检索准确率

**使用方法**：
```bash
python scripts/building/test_building_category.py
```

**测试用例**：
- "社区商铺" → 商业建筑
- "现代别墅" → 居住建筑
- "厂房" → 工业建筑

---

### 5. evaluate_component_rag.py
**功能**：评估组件知识库 RAG 性能

**用途**：
- 测试 RAG 检索质量
- 评估不同查询的召回率和精确度

**使用方法**：
```bash
python scripts/rag/evaluate_component_rag.py
```

---

### 6. deployment_preflight.py
**功能**：部署前健康检查

**用途**：
- 验证生产环境配置
- 测试 LLM 模型连通性
- 在 Jenkins 部署流程中自动执行

**使用方法**：
```bash
# 直接运行（需要配置 .env）
python -m scripts.deployment_preflight

# Docker 环境
docker run --rm --env-file .env <image> python -m scripts.deployment_preflight
```

---

## 🧪 Tests（测试文件）

位置：`wild-server/tests/`

测试文件详细说明请参考：**[测试文件说明文档](./TESTING_GUIDE.md)**

### 核心功能测试
- `test_agent_graph_execution.py` - Agent 图执行流程
- `test_agent_graph_routing.py` - Agent 路由逻辑
- `test_agent_delivery.py` - Agent 结果交付

### 组件生成测试
- `test_component_blueprint.py` - 组件蓝图生成
- `test_component_state_reducer.py` - 组件状态合并
- `test_component_validation_recheck.py` - 组件验证重检

### RAG 相关测试
- `test_rag_semantic_chunking.py` - 语义分片
- `test_rag_index_sync.py` - 索引同步
- `test_rag_retrieval_cache.py` - 检索缓存
- `test_query_planner.py` - 查询规划

### Blueprint 处理测试
- `test_blueprint_normalizer.py` - Blueprint 归一化
- `test_blueprint_text_extraction.py` - 文本提取
- `test_blueprint_material_validation.py` - 材质验证

### 验证器测试
- `test_p0_implementation.py` - P0 方案（结构自检、查询改写）
- `test_p1_p2_implementation.py` - P1/P2 方案（事实/工具/推理自检）
- `test_spatial_validation.py` - 空间验证
- `test_validation_cache.py` - 验证缓存

### 其他测试
- `test_ws_agent_disconnect.py` - WebSocket 断线重连
- `test_session_turns.py` - 会话轮次管理
- `test_ip_geolocation.py` - IP 地理定位

**运行所有测试**：
```bash
# 激活虚拟环境
.\.venv\Scripts\activate  # Windows
source .venv/bin/activate  # Linux/Mac

# 设置 PYTHONPATH
$env:PYTHONPATH="."  # Windows PowerShell
export PYTHONPATH=.  # Linux/Mac

# 运行所有测试
python -m pytest tests/ -v

# 运行单个测试文件
python -m pytest tests/test_rag_semantic_chunking.py -v

# 运行指定测试
python -m pytest tests/test_rag_semantic_chunking.py::RAGSemanticChunkingTest::test_heading_path_and_entity_metadata_reach_every_length_part -v
```

---

## 📝 Examples（示例代码）

位置：`wild-server/examples/`

### p0_usage_example.py
**功能**：P0 优化方案使用示例

**用途**：
- 演示结构自检的使用
- 演示查询改写的使用
- 演示领域配置的使用

**使用方法**：
```bash
python examples/p0_usage_example.py
```

---

## 🎯 常用工作流

### 1. 检查知识库分片质量
```bash
# 1. 查看整体统计
uv run python scripts/rag/inspect_knowledge_chunks.py storage/knowledge_base --table

# 2. 检查特定文件的详细分片
uv run python scripts/rag/inspect_knowledge_chunks.py storage/knowledge_base/building_types/residential/villas.md --show-content

# 3. 验证分片大小合理性
uv run python scripts/rag/inspect_knowledge_chunks.py storage/knowledge_base --chunk-size 600
```

### 2. 更新知识库并测试
```bash
# 1. 修改知识库文档
# （编辑 storage/knowledge_base/... 文件）

# 2. 更新 building_category（如果需要）
uv run python scripts/building/update_building_category.py

# 3. 检查同步状态
uv run python scripts/rag/check_sync_status.py

# 4. 测试 RAG 检索
uv run python scripts/building/test_building_category.py
```

### 3. 运行完整测试
```bash
# 1. 使用 uv run 运行测试
uv run python -m pytest tests/ -v

# 或者设置 PYTHONPATH
$env:PYTHONPATH="."  # Windows
python -m pytest tests/ -v

# 3. 查看覆盖率（如果安装了 pytest-cov）
uv run python -m pytest tests/ --cov=app --cov-report=html
```

### 4. 部署前检查
```bash
# 1. 语法检查
uv run python -m compileall app/

# 2. 运行测试
uv run python -m pytest tests/ -q

# 3. 健康检查
uv run python -m scripts.deployment_preflight
```

---

## 📚 相关文档

- **[测试文件说明](./TESTING_GUIDE.md)** - 详细的测试文件说明和使用指南
- **[开发指南](./DEVELOPMENT.md)** - 开发环境配置和工作流程
- **[部署指南](./DEPLOYMENT.md)** - 生产部署流程
- **[架构文档](./ARCHITECTURE.md)** - 系统架构设计

---

## 🔍 快速查找

| 我想... | 使用工具 |
|--------|---------|
| 查看知识库分片 | `inspect_knowledge_chunks.py` |
| 测试 RAG 检索 | `test_building_category.py` 或 `evaluate_component_rag.py` |
| 更新建筑分类 | `update_building_category.py` |
| 检查索引同步 | `check_sync_status.py` |
| 部署前检查 | `deployment_preflight.py` |
| 运行单元测试 | `python -m pytest tests/` |
| 查看 LangGraph 流程图 | `tests/show_langgraph_graph.py` |

---

## ❓ 常见问题

### 1. Windows PowerShell 中文乱码

**问题**：运行脚本时，中文显示为乱码或 `???`

**解决方案**：在运行脚本前设置 PowerShell 输出编码
```powershell
# 方法1：临时设置（当前会话有效）
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::UTF8

# 方法2：永久设置（添加到 PowerShell 配置文件）
notepad $PROFILE
# 在文件中添加：
# $OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::UTF8
```

**或者**：使用 Windows Terminal（推荐），默认支持 UTF-8

### 2. ModuleNotFoundError: No module named 'app'

**问题**：运行脚本时找不到 `app` 模块

**解决方案**：需要同时设置 `PYTHONPATH` 和使用 `uv run --no-project`
```powershell
# Windows PowerShell
$env:PYTHONPATH="."
uv run --no-project python scripts/script_name.py

# 或一行命令
$env:PYTHONPATH="."; uv run --no-project python scripts/script_name.py

# Linux/Mac
PYTHONPATH=. uv run --no-project python scripts/script_name.py
```

### 3. 测试文件都被跳过

**问题**：运行 pytest 时所有测试都被跳过

**解决方案**：
```bash
# 1. 确保在 wild-server 目录下
cd wild-server

# 2. 激活虚拟环境（如果使用 venv）
.\.venv\Scripts\activate  # Windows
source .venv/bin/activate  # Linux/Mac

# 3. 使用 uv run 执行
uv run python -m pytest tests/ -v

# 4. 查看跳过原因
uv run python -m pytest tests/ -v -rs
```

### 4. 如何查看分片表格输出

**使用 `--table` 参数**：
```bash
$env:PYTHONPATH="."; uv run --no-project python scripts/rag/inspect_knowledge_chunks.py storage/knowledge_base --table
```

**输出示例**：
```
========================================================================================================================
分片信息表
========================================================================================================================
序号 文件               实体名称                类型       主题       长度   分类
---- ------------------ ---------------------- ---------- ---------- ------ ----------
1    villas.md          现代简约别墅            component  window     856    residential
2    villas.md          欧式古典别墅            component  door       742    residential
...
```

---

## ⚙️ 环境要求

### 运行方式

**使用 uv run（需要设置 PYTHONPATH）**
```bash
# Windows PowerShell
$env:PYTHONPATH="."
uv run --no-project python scripts/script_name.py

# 或一行命令
$env:PYTHONPATH="."; uv run --no-project python scripts/script_name.py

# Linux/Mac
export PYTHONPATH=.
uv run --no-project python scripts/script_name.py

# 或一行命令
PYTHONPATH=. uv run --no-project python scripts/script_name.py
```

### 依赖要求

所有工具和测试都需要：
- Python 3.12+
- 已安装依赖：`uv sync` 或 `pip install -e .`

部分工具的额外要求：
- **RAG 相关**：需要 Chroma 数据库和 embedding 配置
- **LLM 测试**：需要配置 `.env` 文件中的模型参数
- **部署检查**：需要完整的生产环境配置

---

更新时间：2026-08-18
