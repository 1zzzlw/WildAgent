# RAG 分片结果怎么看

这份文档专门解释 `inspect_knowledge_chunks.py` 生成的控制台输出和 Markdown 报告。目标不是看懂每个哈希算法，而是判断：

> 这些 chunk 是否适合进入向量库，并能在脱离原文件后独立帮助 Agent。

## 1. 三十秒快速判断

拿到一份分片输出后，先只回答下面六个问题：

1. 总分片数是否符合文档的自然主题数量？
2. 每个分片的 `heading_path` 是否能说清它属于谁、解决什么问题？
3. 单独阅读一个分片时，能否理解它，不需要翻前一片？
4. JSON、表格、公式和对应解释有没有被拆断？
5. `entity_type / entity_name / topic / status / authority` 是否与正文一致？
6. 有没有空壳、重复、互相冲突或混入多个无关主题的分片？

六项都通过，只能说明“分片结构可以进入检索实验”。它还不能证明事实正确，也不能证明向量召回率高。

## 2. 推荐阅读顺序

不要从长 ID 开始读。顺序应该是：

```text
本次配置
  ↓
最后的统计分析
  ↓
每个 chunk 的 heading_path + 完整内容
  ↓
关键业务 metadata
  ↓
part_index / parent_chunk_id
  ↓
哈希、mtime 等诊断字段
```

这样能先判断整体是否异常，再检查具体边界。

## 3. 先看本次配置

输出开头通常是：

```text
配置: chunk_size=900, chunk_overlap=150
```

它的真实含义是：

- `chunk_size=900`：普通长文本的物理长度兜底预算，不是要求每片都接近 900 字符；
- `chunk_overlap=150`：只有普通长文本被切成多个 part 时，相邻 part 才会保留部分重复上下文；
- Markdown 标题会先建立业务边界；
- fenced code 保持原子，不会为了满足 900 字符从中间切断；
- 长表格按行拆分，并为每个子表重复表头。

所以出现 125、347、657 字符的 chunk 都很正常。不能因为没有达到 900 字符就认为“浪费了向量”。语义完整比凑长度重要。

## 4. 再看统计分析

示例结果：

```text
总分片数: 4
最小: 125 字符
最大: 657 字符
平均: 323 字符
中位数: 347 字符
```

统计数字主要用于发现异常，不直接决定好坏。

| 现象 | 可能含义 | 下一步 |
|---|---|---|
| 大量分片小于约 100 字符 | 可能存在空壳标题、只有一句“如下”的说明 | 打开完整内容逐片检查 |
| 少量 100～200 字符分片 | 如果能独立回答一个明确问题，可以保留 | 不要为了凑长度强行合并 |
| 普通文本远大于 `chunk_size` | 标题边界可能不足 | 优先增加真实子标题 |
| JSON/代码块大于 `chunk_size` | Loader 为保护原子性主动保留 | 判断示例是否应按业务主题重构 |
| 同一实体产生很多 part | 实体内容可能过宽 | 看 `part_index` 边界是否仍自包含 |
| 同一文件出现很多极相似 chunk | 可能重复或标题拆得过碎 | 检查正文和 `body_hash` |

长度没有通用的“满分区间”。建筑构成合同可能比较长，单条能力边界可以很短，关键是能否独立回答问题。

## 5. 每个分片先看标题和正文

### 5.1 `heading` 与 `heading_path`

例如：

```text
基础静态窗组合构件 > 当前支持的基础静态窗 > 参数契约
```

这条路径已经说明：

- 领域：基础静态窗组合构件；
- 实体：当前支持的基础静态窗；
- 本片主题：参数契约。

一个合格标题路径应当让你只看标题就能大致预测正文。下面这些路径质量较差：

```text
其他
补充说明
A 方案
示例
参数
```

它们脱离父文档后缺少实体名称，容易产生语义很弱的向量。

### 5.2 `知识路径`

正文开头的：

```text
> 知识路径：基础静态窗组合构件 > 当前支持的基础静态窗 > 参数契约
```

是 Loader 主动重复的上下文。它会和正文一起向量化，让一个 chunk 离开原文件后仍知道自己属于哪个实体。

检查时要确认知识路径没有串到另一个实体。例如窗参数片不能错误地写成门构件路径。

### 5.3 完整内容

对正文执行“四个独立性问题”：

1. 这片在回答一个什么问题？
2. 不看相邻 chunk，正文是否仍然成立？
3. 约束对象和适用条件是否明确？
4. 如果有 JSON/表格，它的解释是否也在本片或标题路径中？

典型失败：

```text
分片 A：具体 JSON 如下：
分片 B：{ "type": "window", ... }
```

分片 A 没有答案，分片 B 缺少解释，两者都不适合独立召回。

## 6. 关键 metadata 怎么看

metadata 不需要全部背下来，可以分成三组。

### 6.1 第一组：必须人工确认的业务字段

| 字段 | 含义 | 示例中应该怎么看 |
|---|---|---|
| `doc_scope` | 是否进入普通生成召回 | `generation` 会参与；`index` 通常被排除 |
| `doc_type` | 文档类别 | 窗规则应为 `component` |
| `entity_type` | 业务实体类型 | 当前例子应为 `window` |
| `entity_name` | 稳定实体名 | 四片都属于 `static_window_component` |
| `topic` | 本实体的主题分类 | 当前文件用 `schema` 表示 Schema 规则 |
| `status` | 成熟度 | `supported` 可进入正式召回；`proposed` 会被排除 |
| `authority` | 事实权威性 | `engine` 表示来自当前引擎事实；`inferred` 会被排除 |
| `wild_version` | 适用版本 | 示例为 `1.1`，应与当前规范一致 |
| `primary_terms` | 主术语 | 正式实体名、稳定技术术语和实际 WILD 类型/字段 |
| `synonyms` | 同义词 | 英文翻译、别名、俗称或用户常用输入；没有时为空字符串 |

正文和这些字段必须互相一致。最危险的情况不是字段缺少，而是字段写错：例如正文讲门，metadata 却标成 `entity_type=window`，过滤检索就会把错误知识送给窗节点。

### 6.2 第二组：来源与分片结构字段

| 字段 | 用途 |
|---|---|
| `source / source_file` | 当前 Markdown 文件名 |
| `path` | 文件在本机的完整位置 |
| `declared_source` | 文档声明的事实来源，例如 Schema 文件 |
| `heading_path` | 原 Markdown 标题路径 |
| `chunk_index` | 当前文件生成后的全局顺序 |
| `parent_chunk_id` | 同一标题 section 的父标识 |
| `part_index` | 一个父 section 被长度兜底后生成的第几个物理 part |

`source` 与 `declared_source` 不冲突：

- `source=windows-supported.md` 表示本 chunk 来自哪个知识文档；
- `declared_source=wild-web/wild-lang/schema.json` 表示这份知识依据什么事实来源。

### 6.3 第三组：通常不用人工判断语义的诊断字段

| 字段 | 用途 |
|---|---|
| `ID` | Chroma 中的稳定分片标识 |
| `content_hash` | 包含知识路径的完整内容哈希 |
| `body_hash` | 更偏向业务正文的哈希，用于发现跨文件重复 |
| `mtime` | 来源文件最后修改时间 |
| `namespace` | 逻辑索引隔离名称 |

这些字段主要用于同步、去重和定位问题。哈希看起来随机是正常的，不需要判断“数值好不好”。

`namespace=test` 表示这次是预览/测试分片，不表示已经进入生产 `wild_spec` 索引。

## 7. `parent_chunk_id` 和 `part_index` 怎么看

### 情况 A：没有触发长度拆分

```text
parent_chunk_id: ...某个标题 section...
part_index: 0
```

如果每个父 ID 只出现一次，且 `part_index` 都是 0，说明这些 chunk 主要由 Markdown 标题产生，长度兜底没有继续拆它们。

你提供的四个窗分片全部属于这种情况。因此本次 `chunk_overlap=150` 实际没有参与内容生成。

### 情况 B：触发长度拆分

```text
parent_chunk_id: same-parent
part_index: 0

parent_chunk_id: same-parent
part_index: 1
```

这表示同一个标题 section 太长，被拆成多个物理 part。此时要重点检查：

- part 0 和 part 1 都重复了知识路径；
- 每个 part 仍能理解；
- 句子没有从奇怪的位置断开；
- 解释与对应示例没有分家；
- 相邻 part 的少量重复来自 overlap，不是原文重复。

不要仅因为出现 `part_index=1` 就判定失败。只有边界破坏语义时才需要重构。

## 8. JSON 和表格怎么验收

### JSON

检查：

- 开头和结尾的三个反引号都存在；
- 标为 `json` 的内容是严格 JSON；
- 没有 `//`、`/* */`、尾随逗号；
- 片段明确说明是否为完整 `.wild`；
- 示例依赖的 `parentWall`、材质等引用在完整场景中有来源；
- 文字描述和数值一致。

分片脚本只保证结构不被切断，不会自动证明字段受引擎支持。

### 表格

检查：

- 表头和分隔行存在；
- 每行仍属于同一个实体；
- 超长表格拆片后，每片都重复表头；
- 表格后的关键约束没有和表格失去关系。

## 9. 你这份窗分片的实际判读

输入文件：`components/windows-supported.md`  
配置：`chunk_size=900`、`chunk_overlap=150`

| 分片 | 回答的问题 | 长度 | 判定 | 原因 |
|---|---|---:|---|---|
| #1 当前支持的基础静态窗 | 这个组件是什么、能做什么 | 165 | 通过 | 短但有完整定义、宿主和编译结果，不是空壳 |
| #2 参数契约 | 支持哪些字段和约束 | 657 | 通过 | 表格完整，字段要求和法向/厚度约束保持在一起 |
| #3 有效 JSON 片段 | 正确的组件 JSON 怎么写 | 347 | 通过 | fenced JSON 完整，并明确“不是完整 `.wild` 文件” |
| #4 当前边界 | 哪些交互和字段尚未实现 | 125 | 通过 | 独立回答能力边界，避免模型把未支持能力当事实 |

整体结论：

- 四片都属于 `static_window_component`，实体 metadata 一致；
- 四片的标题主题互补，没有把定义、参数、示例和边界混成一个大块；
- 每个 `parent_chunk_id` 不同且 `part_index=0`，说明标题主动建立了四个业务边界；
- 没有发生普通文本二次切分，因此 overlap 没有触发；
- JSON 和表格保持完整；
- `status=supported`、`authority=engine`、`doc_scope=generation`，满足正式召回的 metadata 条件；
- `namespace=test` 说明这是预览结果，不代表已经写入生产索引。

这份结果可以进入下一步“向量召回评测”。它不能单独证明：

- JSON 中每个字段已经通过当前 Schema/渲染器验证；
- 用户问“窗怎么生成”时一定能在 Top-K 召回正确片；
- Agent 召回后一定会采用这些规则。

## 10. 常见误区

### 误区一：chunk 越接近 900 越好

错误。900 是普通长文本上限预算，不是目标长度。125 字符的能力边界如果语义完整，比把它和无关参数强行合并更好。

### 误区二：分片数越少越好

错误。一个巨大 chunk 混合定义、参数、示例和限制，会让 embedding 表意模糊。分片数量应接近自然业务问题数量。

### 误区三：控制台显示完整，所以向量召回一定正确

错误。分片检查只验证输入向量库前的内容结构；召回排序还受问题表达、embedding、metadata 过滤和 Top-K 影响。

### 误区四：`content_hash` 不同说明内容冲突

错误。不同正文或不同知识路径本来就会得到不同哈希。判断重复要结合 `body_hash` 和实际正文。

### 误区五：有 overlap 就一定会出现重复文字

错误。只有普通长文本真正被拆成多个 part 时 overlap 才生效。你这份结果没有触发。

## 11. 分片通过后做什么

先做离线流程冒烟：

```powershell
cd E:\AgentProject\WildAgent\wild-server
$env:PYTHONPATH="."
.\.venv\Scripts\python.exe scripts\rag\eval_retrieval.py `
  --embedding hash --limit 5 --no-log-output
```

再评测已有真实索引：

```powershell
.\.venv\Scripts\python.exe scripts\rag\eval_retrieval.py
```

如果要比较分片参数，必须重新 embedding 并使用临时索引：

```powershell
.\.venv\Scripts\python.exe scripts\rag\eval_retrieval.py `
  --temporary-index --chunk-size 600 --chunk-overlap 100
```

完整关系是：

```text
分片结构通过
  ≠ 事实一定正确
  ≠ Recall@K 一定高
  ≠ Agent 一定采用

分片检查 → 事实审计 → 向量召回评测 → Agent 吸收评测
```

## 12. 可复制的验收清单

```text
[ ] 分片数量与自然主题数量大致一致
[ ] 每片标题路径包含明确实体和主题
[ ] 每片脱离相邻内容仍可理解
[ ] 没有空壳或只写“如下”的 chunk
[ ] JSON、表格、公式及其解释没有拆断
[ ] entity_type / entity_name / topic 与正文一致
[ ] status / authority / doc_scope 符合召回用途
[ ] 多 part 的 parent_chunk_id 相同且 part_index 连续
[ ] 没有竞争性重复或互相冲突的正文
[ ] 已确认“结构通过”不等于“召回通过”
```
