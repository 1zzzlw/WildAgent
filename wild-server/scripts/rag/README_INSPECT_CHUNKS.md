---
AIGC:
    Label: "1"
    ContentProducer: 001191440300708461136T1XGW3
    ProduceID: 120c9aab85e3ed979ff6cbda3bbcb633_aa2254a49ae711f19bec525400826444
    ReservedCode1: 4J3muRbb+ttEcKNqqabYq6XxrXVw3B3aMqX1ld5gaeug9FfL2crqKkNcE5qrzvmv2ZynBWhIdly6dS3K87dwLDlGGXL1cx7sV3aEjHMmJKr0AjDb7L3Eg+vluHLvOFNxqtMX5k++Ey9al6ANNMILwShJPT5MotIaeZmiqNdGXF1PCxofTd5MDkNRhtQ=
    ContentPropagator: 001191440300708461136T1XGW3
    PropagateID: 120c9aab85e3ed979ff6cbda3bbcb633_aa2254a49ae711f19bec525400826444
    ReservedCode2: 4J3muRbb+ttEcKNqqabYq6XxrXVw3B3aMqX1ld5gaeug9FfL2crqKkNcE5qrzvmv2ZynBWhIdly6dS3K87dwLDlGGXL1cx7sV3aEjHMmJKr0AjDb7L3Eg+vluHLvOFNxqtMX5k++Ey9al6ANNMILwShJPT5MotIaeZmiqNdGXF1PCxofTd5MDkNRhtQ=
---





# 知识库分片检查工具使用指南

`inspect_knowledge_chunks.py` 是一个用于检查和分析知识库 Markdown 文件分片的工具，可以直接调用 `app/spec/loader.py` 中的 `MarkdownChunker`，把分片结果以可读形式展示出来，便于验证知识库配置和分片策略。

---

## 功能特点

- 对单个文件或整个目录进行分片分析
- 查看每个分片的 metadata 和内容摘要
- 表格形式展示分片信息（简洁模式）
- 详细统计：分片数量、大小分布、实体分布
- 自定义分片参数（chunk_size、chunk_overlap）
- 自动生成 Markdown 检查报告与控制台日志到 `scripts/reports/` 目录（可用 `--output` / `--log-output` 自定义路径）

---

## 快速开始

### 环境准备

本项目使用 uv 管理依赖。推荐先激活虚拟环境，再设置 `PYTHONPATH`：

```bash
# 1. 激活虚拟环境
.\.venv\Scripts\activate  # Windows PowerShell
source .venv/bin/activate  # Linux/Mac

# 2. 设置 PYTHONPATH（让脚本可以 import app.spec.loader）
$env:PYTHONPATH="."  # Windows PowerShell
export PYTHONPATH=.  # Linux/Mac
```

如果不想手动激活虚拟环境，也可以使用 `uv run --no-project`（仍需设置 `PYTHONPATH`）：

```bash
# Windows PowerShell
$env:PYTHONPATH="."
uv run --no-project python scripts/rag/inspect_knowledge_chunks.py storage/knowledge_base/building_types/residential/villas.md

# Linux/Mac
export PYTHONPATH=.
uv run --no-project python scripts/rag/inspect_knowledge_chunks.py storage/knowledge_base/building_types/residential/villas.md
```

### 基本用法

```bash
# 检查单个文件
python scripts/rag/inspect_knowledge_chunks.py storage/knowledge_base/building_types/residential/villas.md

# 检查整个目录
python scripts/rag/inspect_knowledge_chunks.py storage/knowledge_base

# 表格形式输出（推荐，信息更紧凑）
python scripts/rag/inspect_knowledge_chunks.py storage/knowledge_base --table
```

**一行命令（不激活虚拟环境）**

```bash
# Windows PowerShell
$env:PYTHONPATH="."; uv run --no-project python scripts/rag/inspect_knowledge_chunks.py storage/knowledge_base --table

# Linux/Mac
PYTHONPATH=. uv run --no-project python scripts/rag/inspect_knowledge_chunks.py storage/knowledge_base --table
```

---

## 命令行参数

### 必需参数

- `path` - Markdown 文件或目录路径

### 可选参数

#### 分片配置
- `--namespace <name>` - 命名空间，默认 `test`
- `--chunk-size <size>` - 分片大小（字符数），默认 900
- `--chunk-overlap <size>` - 分片重叠（字符数），默认 150

#### 输出控制
- `--table` - 表格形式输出（简洁模式）
- `--show-content` - 显示每个分片的完整内容
- `--no-summary` - 不显示统计摘要

#### 处理限制
- `--limit <n>` - 限制处理的文件数量（仅用于目录）

#### 输出文件
- `--output <file>` - 报告 Markdown 输出路径，默认 `scripts/reports/inspect_chunks_<时间戳>.md`
- `--log-output <file>` - 控制台日志保存路径，默认 `scripts/reports/chunks_console_<时间戳>.txt`
- `--no-log-output` - 不保存控制台日志（默认启用日志保存）

---

## 使用示例

### 1. 检查单个文件的分片

```bash
$env:PYTHONPATH="."; uv run --no-project python scripts/rag/inspect_knowledge_chunks.py storage/knowledge_base/building_types/residential/villas.md
```

**输出内容**：
- 每个分片的详细信息（ID、长度、metadata、内容预览）
- 统计分析（长度分布、实体分组等）

### 2. 表格形式查看分片（推荐）

```bash
$env:PYTHONPATH="."; uv run --no-project python scripts/rag/inspect_knowledge_chunks.py storage/knowledge_base/building_types/residential/villas.md --table
```

**输出示例**：

```
分片信息表
====================================================================================================
No   文件            实体               类型        长度   分类
---- --------------- ------------------ -------- ------ --------
1    villas.md       villa              building_t 139    residential
2    villas.md       modern_villa       building_t 770    residential
...
====================================================================================================
总计: 13 个分片

标题路径列表
====================================================================================================
  1. 居住建筑：别墅
  2. 居住建筑：别墅 > 1.1 现代别墅（架空层 + 水平长窗） > 构件清单
...
```

### 3. 检查整个目录

```bash
$env:PYTHONPATH="."; uv run --no-project python scripts/rag/inspect_knowledge_chunks.py storage/knowledge_base --table
```

扫描目录下所有 Markdown 文件并生成汇总表格。

### 4. 限制处理文件数量

```bash
# 只处理前 5 个文件
$env:PYTHONPATH="."; uv run --no-project python scripts/rag/inspect_knowledge_chunks.py storage/knowledge_base --limit 5 --table
```

适用于快速查看或调试。

### 5. 查看完整内容

```bash
$env:PYTHONPATH="."; uv run --no-project python scripts/rag/inspect_knowledge_chunks.py storage/knowledge_base/components/windows.md --show-content
```

显示每个分片的完整 Markdown 内容。

### 6. 自定义分片参数

```bash
# 使用更小的分片
$env:PYTHONPATH="."; uv run --no-project python scripts/rag/inspect_knowledge_chunks.py storage/knowledge_base --chunk-size 600 --chunk-overlap 100 --table
```

用于测试不同分片策略的效果。

### 7. 只看统计，不看明细

```bash
$env:PYTHONPATH="."; uv run --no-project python scripts/rag/inspect_knowledge_chunks.py storage/knowledge_base --table --no-summary
```

跳过统计摘要，只显示表格。

---

## 输出说明

### 表格模式输出

#### 分片信息表

| 列名     | 说明                              |
| -------- | --------------------------------- |
| 序号     | 分片编号                          |
| 文件     | 源文件名                          |
| 实体名称 | entity_name（如 modern_villa）    |
| 类型     | doc_type（如 building_type）      |
| 主题     | topic（如 assembly, constraints） |
| 长度     | 分片内容长度（字符数）            |
| 分类     | building_category（如 residential） |

#### 标题路径列表

显示每个分片的完整标题层级，方便理解文档结构。

### 统计分析

#### 长度统计
- 最小 / 最大 / 平均 / 中位数

#### 按维度分组
- 按文件分组
- 按实体名称分组
- 按文档类型分组
- 按建筑类型分组

### 文件输出

运行后默认在 `scripts/reports/` 目录生成两个文件（脚本位于 `scripts/rag/`，通过 `Path(__file__).parents[1] / "reports"` 定位）：

| 文件 | 说明 |
| --- | --- |
| `chunks_console_<时间戳>.txt` | 控制台原始输出日志（Tee 双写，与终端内容逐行一致），可用 `--log-output` 自定义路径、`--no-log-output` 关闭 |
| `inspect_chunks_<时间戳>.md` | Markdown 检查报告（检查对象、分片信息表、标题路径列表、统计分析），可用 `--output` 自定义路径 |

```bash
# 自定义日志与报告输出路径
$env:PYTHONPATH="."; uv run --no-project python scripts/rag/inspect_knowledge_chunks.py storage/knowledge_base --table --log-output logs/console.txt --output reports/inspect.md

# 关闭控制台日志保存（仅控制台展示 + Markdown 报告）
$env:PYTHONPATH="."; uv run --no-project python scripts/rag/inspect_knowledge_chunks.py storage/knowledge_base --table --no-log-output
```

---

## 常见使用场景

### 1. 验证知识库分片质量

**问题**：如何确认知识库分片是否合理？

**方法**：
```bash
$env:PYTHONPATH="."; uv run --no-project python scripts/rag/inspect_knowledge_chunks.py storage/knowledge_base --table
```

**检查要点**：
- 每个分片长度适中（不要过长或过短）
- 标题路径完整（包含所有层级）
- entity_name 正确分配
- building_category 准确标记

### 2. 调试 RAG 检索问题

**问题**：为什么某个查询检索不到相关内容？

**方法**：
```bash
# 1. 检查文件是否被正确分片
$env:PYTHONPATH="."; uv run --no-project python scripts/rag/inspect_knowledge_chunks.py storage/knowledge_base/building_types/commercial/shops.md --table

# 2. 查看 metadata 是否正确
$env:PYTHONPATH="."; uv run --no-project python scripts/rag/inspect_knowledge_chunks.py storage/knowledge_base/building_types/commercial/shops.md

# 3. 检查内容是否完整
$env:PYTHONPATH="."; uv run --no-project python scripts/rag/inspect_knowledge_chunks.py storage/knowledge_base/building_types/commercial/shops.md --show-content
```

### 3. 优化分片策略

**问题**：如何找到最佳的 chunk_size 和 chunk_overlap？

**方法**：
```bash
# 测试不同配置
$env:PYTHONPATH="."; uv run --no-project python scripts/rag/inspect_knowledge_chunks.py storage/knowledge_base --chunk-size 600 --chunk-overlap 100 --table
$env:PYTHONPATH="."; uv run --no-project python scripts/rag/inspect_knowledge_chunks.py storage/knowledge_base --chunk-size 900 --chunk-overlap 150 --table
$env:PYTHONPATH="."; uv run --no-project python scripts/rag/inspect_knowledge_chunks.py storage/knowledge_base --chunk-size 1200 --chunk-overlap 200 --table
```

**比较指标**：
- 分片总数
- 平均长度
- 长度分布
- 标题路径完整性

### 4. 新增知识库后验证

**问题**：添加新的知识库文件后如何验证？

**方法**：
```bash
# 1. 检查新文件的分片
$env:PYTHONPATH="."; uv run --no-project python scripts/rag/inspect_knowledge_chunks.py storage/knowledge_base/new_category/new_file.md --table

# 2. 验证 metadata 继承
$env:PYTHONPATH="."; uv run --no-project python scripts/rag/inspect_knowledge_chunks.py storage/knowledge_base/new_category/new_file.md

# 3. 确认与现有分片不冲突
$env:PYTHONPATH="."; uv run --no-project python scripts/rag/inspect_knowledge_chunks.py storage/knowledge_base --table | grep new_entity
```

### 5. 查找重复内容

**问题**：不同文件是否有重复内容？

**方法**：
```bash
# 检查 body_hash（内容哈希）
$env:PYTHONPATH="."; uv run --no-project python scripts/rag/inspect_knowledge_chunks.py storage/knowledge_base > chunks_analysis.txt

# 查找相同的 body_hash
grep "body_hash" chunks_analysis.txt | sort | uniq -d
```

---

## 配合其他工具使用

### 1. 与 check_sync_status.py 配合

```bash
# 1. 检查同步状态
$env:PYTHONPATH="."; uv run --no-project python scripts/rag/check_sync_status.py

# 2. 查看具体分片
$env:PYTHONPATH="."; uv run --no-project python scripts/rag/inspect_knowledge_chunks.py storage/knowledge_base --table

# 3. 重新索引
# （在 AgentService 中自动触发）
```

### 2. 与 test_building_category.py 配合

```bash
# 1. 检查分类标记
$env:PYTHONPATH="."; uv run --no-project python scripts/rag/inspect_knowledge_chunks.py storage/knowledge_base/building_types --table

# 2. 测试分类检查
$env:PYTHONPATH="."; uv run --no-project python scripts/building/test_building_category.py

# 3. 如有问题，更新 metadata
$env:PYTHONPATH="."; uv run --no-project python scripts/building/update_building_category.py
```

---

## 相关脚本

### inspect_chunks_demo.py（分片展示报告）

`inspect_chunks_demo.py` 是本工具的分片展示版本：在控制台打印分片来源、数量、字符数、内容摘要与合法性检查结果，同时把同样的分片展示信息写入 Markdown 报告文件（默认生成到 `scripts/reports/` 目录，文件名为 `chunks_report_<时间戳>.md`）。

控制台输出默认通过 Tee 双写同时保存到独立日志文件（默认生成到 `scripts/reports/` 目录，文件名为 `chunks_console_<时间戳>.txt`），避免终端滚动展示不全的问题；日志文件与 Markdown 报告互不干扰。

```bash
# 生成单个文件的展示报告（控制台日志默认同时保存）
$env:PYTHONPATH="."; uv run --no-project python scripts/rag/inspect_chunks_demo.py storage/knowledge_base/building_types/residential/villas.md

# 生成整个知识库的展示报告
$env:PYTHONPATH="."; uv run --no-project python scripts/rag/inspect_chunks_demo.py storage/knowledge_base --limit 5

# 自定义控制台日志路径
$env:PYTHONPATH="."; uv run --no-project python scripts/rag/inspect_chunks_demo.py storage/knowledge_base --limit 5 --log-output logs/console.txt

# 关闭控制台日志保存（仅控制台展示 + Markdown 报告）
$env:PYTHONPATH="."; uv run --no-project python scripts/rag/inspect_chunks_demo.py storage/knowledge_base --limit 5 --no-log-output
```

控制台日志相关参数：
- `--log-output <file>`：自定义控制台日志保存路径（默认 `scripts/reports/chunks_console_<时间戳>.txt`）
- `--no-log-output`：不保存控制台日志（默认启用日志保存）
- `--output <file>`：仅控制 Markdown 报告路径，与日志文件互不影响

输出内容：
- 控制台：每个分片的 ID、来源、标题路径、实体、类型、长度、状态、合法性、内容摘要，以及按分组展示的补充 metadata 字段（仅显示实际存在的字段）
- Markdown 文件：统计概览（数量/长度分布）、按实体分布、合法性检查结果、分片明细表格、每个分片的详细内容（补充 metadata 字段按分组完整列出，缺失显示 `-`）

补充 metadata 字段按以下分组展示（覆盖 `MarkdownChunker` 写入的全部字段）：

| 分组 | 字段 |
|---|---|
| 定位/溯源 | `path`、`_source`、`source_file`、`_extension`、`_file_name`、`declared_source` |
| 分片结构 | `namespace`、`heading_path`、`parent_chunk_id`、`part_index`、`chunk_index` |
| 内容校验 | `body_hash`、`content_hash` |
| 时间 | `mtime` |
| 文档分类 | `doc_scope`、`knowledge_layer`、`entity_type`、`topic`、`wild_version`、`keywords`、`building_category`、`entity_aliases`、`constraint_tags`、`role_tags` |

说明：
- 列表类字段（如 `keywords`、`entity_aliases`）以 `; ` 连接展示
- `mtime` 时间戳自动转为 `YYYY-MM-DD HH:MM:SS` 可读格式
- 单条 metadata 可能只包含部分字段，缺失字段在控制台不显示、在 Markdown 报告中显示为 `-`，不会报错

---

## 故障排查

### 问题：没有生成分片

**可能原因**：
- 文件不存在
- 文件为空
- 文件格式不是 Markdown

**解决方法**：
```bash
# 检查文件是否存在
ls storage/knowledge_base/path/to/file.md

# 查看文件内容
cat storage/knowledge_base/path/to/file.md
```

### 问题：分片过大或过小

**可能原因**：
- chunk_size 配置不当
- Markdown 结构特殊

**解决方法**：
```bash
# 调整参数
$env:PYTHONPATH="."; uv run --no-project python scripts/rag/inspect_knowledge_chunks.py <path> --chunk-size 1200 --chunk-overlap 200 --table
```

### 问题：metadata 缺失

**可能原因**：
- Frontmatter 格式错误
- rag-meta 注释语法不正确

**解决方法**：
```bash
# 查看原始分片内容
$env:PYTHONPATH="."; uv run --no-project python scripts/rag/inspect_knowledge_chunks.py <path> --show-content

# 检查 Markdown 文件的 Frontmatter
head -20 storage/knowledge_base/path/to/file.md
```

---

## 最佳实践

### 1. 定期检查知识库质量

每周或每次更新知识库后运行：
```bash
$env:PYTHONPATH="."; uv run --no-project python scripts/rag/inspect_knowledge_chunks.py storage/knowledge_base --table > weekly_chunks_report.txt
```

### 2. 提交前验证

修改知识库文件后，提交前检查：
```bash
$env:PYTHONPATH="."; uv run --no-project python scripts/rag/inspect_knowledge_chunks.py <modified_file> --table
```

### 3. 调试时使用详细模式

遇到问题时查看完整信息：
```bash
$env:PYTHONPATH="."; uv run --no-project python scripts/rag/inspect_knowledge_chunks.py <file> --show-content
```

### 4. 表格模式用于快速浏览

日常查看使用表格模式：
```bash
$env:PYTHONPATH="."; uv run --no-project python scripts/rag/inspect_knowledge_chunks.py storage/knowledge_base --table --limit 10
```

---

## 相关文档

- **[工具目录](../../docs/tools工具目录.md)** - 所有开发工具
- **[测试指南](../../docs/TESTING_GUIDE.md)** - 测试文件说明
- **[RAG 优化路线](../../docs/WildAgent-RAG与智能体优化路线.md)** - RAG 系统优化

---

## 技术细节

### 分片算法

使用 LangChain 的 `MarkdownHeaderTextSplitter`：
1. 按 Markdown 标题层级分割
2. 保留标题路径作为上下文
3. 超长章节按字符数二次分割（`RecursiveCharacterTextSplitter`）
4. 保持 JSON/表格结构完整

### Metadata 继承

- **文件级**：Frontmatter 中的 metadata
- **章节级**：rag-meta 注释中的 metadata
- **继承规则**：子标题继承父标题的 metadata，更深层标题上的声明覆盖祖先声明

### 去重机制

- **content_hash**：完整内容哈希（包括标题路径）
- **body_hash**：业务正文哈希（不含标题）
- 用途：跨文件识别重复内容

---

更新时间：2026-08-18
*（内容由AI生成，仅供参考）*
*（内容由AI生成，仅供参考）*
*（内容由AI生成，仅供参考）*
