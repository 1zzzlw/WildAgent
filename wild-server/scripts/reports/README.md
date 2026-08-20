---
AIGC:
    Label: "1"
    ContentProducer: 001191440300708461136T1XGW3
    ProduceID: 120c9aab85e3ed979ff6cbda3bbcb633_99b5e31c9c4911f184de525400f8a581
    ReservedCode1: z9azDVdQ/E0BGjokht8kkmrMIK0QhXYJLy9hxxt8YodVFVwKBaIv8pXSknjUhtSB4BgsrZFozg6rozuIeVOUvOjI2/B+UaSYDaktHK8jEIqIdhjuAXIhjK4TuI6SNcvsly6In6jiLTR7uue7v7xiktNsqDIk5RXFluDL37tEHvTflw+0KEcGgi96DyE=
    ContentPropagator: 001191440300708461136T1XGW3
    PropagateID: 120c9aab85e3ed979ff6cbda3bbcb633_99b5e31c9c4911f184de525400f8a581
    ReservedCode2: z9azDVdQ/E0BGjokht8kkmrMIK0QhXYJLy9hxxt8YodVFVwKBaIv8pXSknjUhtSB4BgsrZFozg6rozuIeVOUvOjI2/B+UaSYDaktHK8jEIqIdhjuAXIhjK4TuI6SNcvsly6In6jiLTR7uue7v7xiktNsqDIk5RXFluDL37tEHvTflw+0KEcGgi96DyE=
---





# reports/ — 脚本运行产物

## 目录说明

`scripts/rag/` 下分片检查脚本（`inspect_knowledge_chunks.py`、`inspect_chunks_demo.py`）与检索评测脚本（`eval_retrieval.py`）的默认输出目录，存放运行生成的 Markdown 报告与控制台日志，非可执行脚本。

## 文件类型

| 文件 | 来源脚本 | 说明 |
|---|---|---|
| `inspect_chunks_<时间戳>.md` | inspect_knowledge_chunks.py | 分片检查报告（信息表 + 标题路径 + 统计分析） |
| `chunks_report_<时间戳>.md` | inspect_chunks_demo.py | 分片展示报告（分片明细 + metadata 分组） |
| `chunks_console_<时间戳>.txt` | 两个脚本 | 控制台原始输出日志（Tee 双写，与终端逐行一致） |
| `eval_retrieval_<时间戳>.md` | eval_retrieval.py | 检索效果评测报告（汇总统计 + 信号提示 + 分组分布 + 逐题 Top-K 命中明细） |
| `eval_console_<时间戳>.txt` | eval_retrieval.py | 评测控制台原始输出日志（Tee 双写，与终端逐行一致） |

## 如何阅读分片分析报告

分片分析报告（`inspect_chunks_<时间戳>.md`）分为三部分：

### 1. 分片信息表

| 列 | 作用 |
|---|---|
| 文件 | 分片来源文档，用于定位"哪个文档分得异常" |
| 实体 / 类型 | 对应 metadata 的 entity_type / building_category，是检索时的过滤维度 |
| 长度 | 字符数，判断分片质量的第一指标 |

### 2. 标题路径列表

展示每条分片在文档树中的层级上下文（如 `玻璃幕墙骨架—玻璃组装配方 > 方案 B 组装步骤`）。这一列是向量化后能否找回上下文的关键：路径只有一层说明分片丢失了所属章节语境，单独向量化后语义容易漂移；路径完整则检索时可利用 heading/path 回溯父级上下文做拼接。

### 3. 统计分析

长度分布（最小 / 最大 / 平均 / 中位数）、按文件分组统计，用于快速定位异常分片。

## 分片格式如何影响向量化效果

| 分片属性 | 向量化后作用 | 判断标准 |
|---|---|---|
| 粒度（长度） | 决定 embedding 向量承载的语义量 | 过碎（<150）语义残缺；过大（>1000）向量被稀释，一个向量混多种主题 |
| 语义完整性 | 决定向量是否"言之有物" | 一个分片是否讲清一件事（完整参数表、完整组装步骤），而不是被标题切得七零八落 |
| metadata | 检索后处理：过滤 + 上下文拼接 + 溯源 | 过滤类（namespace / entity_type / building_category / role_tags）、上下文类（parent_chunk_id / heading / path）、溯源类（source_file / body_hash 去重） |

## 体检要点（异常信号）

- **长度分布**：平均 / 中位数应在 200-800 字符的理想区间；最大值过大（>1000）需定位排查，命中后往往需要二次处理
- **小分片密集**：同文件连续出现大量 <300 字符分片，说明按标题切分过碎，建议调大 chunk-size 或合并标题层级
- **标题路径不完整**：分片缺少父级上下文，建议开启父子分片拼接
- **实体 / 类型列大面积为空**：metadata 未正确落库，检索过滤能力会打折扣

## 如何量化验证向量化效果

静态报告只能体检，实际效果需做检索实验：

1. **人工抽样**：挑 20-30 个典型问题（如"怎么组装玻璃幕墙骨架"），跑检索链路看 Top-5 命中是否相关、是否命中正确分片
2. **对比实验**：用 `--chunk-size` / `--chunk-overlap` 参数跑多组配置（如 900/150、1200/200、600/100），对同一批问题对比命中准确率
3. **关注失败模式**：
   - 漏召回：答案跨多个分片被切断 → 调大 chunk-size 或做父子块拼接
   - 乱召回：命中分片主题混杂（一个向量混多个实体）→ 调小 chunk-size 或加强 metadata 过滤

## 如何阅读检索评测报告（eval_retrieval）

检索评测报告（`eval_retrieval_<时间戳>.md`）用于量化"检索到底好不好"：

- **汇总统计**：空召回率、平均 Top-1 距离、每问平均命中数、平均同源率，快速判断整体水平
- **信号提示**：脚本自动给出的统计异常观察（如空召回率高、同源率 >60% 提示漏召回）
- **分组分布**：按实体 / 按文件查看命中集中度，识别"泛化过强"或"某文件被无关问题命中"
- **逐题明细**：每条问题的 Top-K 命中分片表（距离 / 来源文件 / 标题路径 / 实体 / 内容摘要），人工复核 Top-1 是否命中正确章节，据此区分漏召回 / 乱召回 / 浅召回

完整"报告怎么看"说明（数字含义、失败模式识别、优化方向决策）见
`scripts/rag/README_EVAL_RETRIEVAL.md`。

## 说明

- 文件由 `scripts/rag/` 下的分片检查 / 检索评测脚本在 wild-server 根目录运行后默认输出到本目录（脚本通过 `Path(__file__).resolve().parents[1] / "reports"` 定位），目录不存在自动创建；可用 `--output` / `--log-output` 自定义路径，`--no-log-output` 关闭日志保存。
- 本目录文件为运行产物，可随时清理或归档。
*（内容由AI生成，仅供参考）*
*（内容由AI生成，仅供参考）*
*（内容由AI生成，仅供参考）*
