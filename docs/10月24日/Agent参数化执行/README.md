# Agent 参数计算与构造展开

本次按“模型选择设计、程序落实确定性计算”的分工修改现有生产链。没有新增 LangGraph 节点，没有做模型对照实验，也没有把 10 月 23 日的整栋建筑脚本作为默认模板。

## 实际改动

1. `app/design/parametric.py` 提供设计和构件共用的声明式计算。模型在 JSON 根声明 `parameters`，使用 `=表达式` 引用共享参数或只读事实，用 `$repeat` 展开重复项。支持有限数学运算和 JSON 引用，不使用 eval/exec，不提供 Python 程序、文件、网络或模块导入能力。参数循环依赖、非有限结果、非法访问和展开超限给出具体路径，不截断产物。
2. `architecture/design_workflow.py` 在图纸契约校验前展开；设计审核、DesignDocument、计划和 UI 继续消费原来的完整数值数据。局部补丁也可以计算，但展开后仍经过原有修改路径权限检查。图纸诊断保留输入声明、计算版本、输入/事实/输出 hash；格式修订不继续开启思考。
3. `plan/construction.py` 将主体的 `walls`、`slabs` 声明转换为既有 WILD。墙从图纸宿主取得端点；板按体量、语义楼层、厚度计算范围和板底，扣除显式挑空，同材质同厚度的体量重叠楼板只保留一份。不同材料或厚度的重叠范围报冲突。特殊曲墙、坡板等继续走原生 geometry。
4. `run_marker_generate` 把展开结果送入既有材质绑定、共墙处理、局部采纳、关系检查和装配链。失败声明进入后续修订上下文；成功与失败的原始模型输出保留在 trace。构件思考设置尊重请求中的 `thinking_mode=False`。
5. 材质引用可以使用已批准角色，程序通过当前材质方案映射到实际 ID。已有材质 ID 和显式定义优先，未声明角色不会被猜测成默认材质。真实试跑中的失败回复已离线回放通过。
6. 通用几何的 `component` 别名此前会漏掉单个 box 的整体尺寸检查；已纳入原有几何关系检查。校验器版本提升至 `1.1`，避免旧快照冒充新检查结论。
7. 单个原生构件可省略图纸已确定的字段：门窗宽高及安装位置、阳台/雨棚尺寸、未旋转缩放 box 的中心与尺寸、自动矩形屋面的覆盖范围与支承位置等。程序只补缺失字段，显式错误值继续由原验收拒绝；不把整组尺寸用于多构件组合，不替旋转、曲面或未确定设计选择几何。补齐字段和来源输入记录在 construction trace。

参数化声明属于 Agent 输入表达。最终 WILD 和前端/Core 协议没有增加 `parameters`、`walls`、`slabs` 或表达式字段。

## 清理与兼容

- 楼梯开口与主体挑空共用 `subtract_rectangles`，移除了原楼梯拆板函数中的重复差集代码。
- 删除主体提示里重复要求模型抄写标高、板底和世界边界的段落，改为明确构造声明与原生几何的职责。
- 构件输出协议保留原 Schema 和坐标/宿主语义，删除与 Schema 重复的必填、可选字段清单。
- 删除设计回复提取时可能继续接受内部局部对象的重试逻辑；通过共享 JSON 提取器的 `outer_only` 模式保留外层错误。其他调用仍保留原提取行为。
- 修正现有知识文档中过时的 `program` 接口承诺。试跑关闭了索引自动同步，真实检索使用既有索引；新计算协议直接由当前 system prompt 提供。知识文件的索引更新仍走项目现有增量同步机制。
- 原生数值 JSON 仍可提交；未启用 `parameters` 的普通字符串不会被当成表达式。保留物件、编辑和离线编译仍使用的既有入口，没有删除历史产物或改动前端/Core。

## 验证

### 离线回归

[verify.py](verify.py) 调用真实生产函数，模型与检索替身有明确标记；不是模型能力评估。

最终 [verification.json](verification.json) 记录 **135 项通过**，覆盖参数依赖、重复与嵌套展开、只读事实、非法表达式、重复预算、平移和方向变化、楼面顶与挑空面积、楼梯开口幂等、稳定 ID、宿主和尺寸拒绝、材质角色解析、构造失败后的局部修订，以及设计补丁的原权限链。另删去真实门窗、屋顶、格栅中图纸已确定的字段，再补齐并验证与原几何一致；组合、旋转和明确曲面不被按整体 box 自动补齐。

完整回放经过 `plan_node → run_marker_generate → compile_node`，产物见 [offline.wild](offline.wild)，构造与装配证据见 [offline-pipeline.json](offline-pipeline.json)。另对真实生成保存的全部 17 个标记及最终候选重新执行了当前代码的检查。

静态检查：10 个修改/新增 Python 文件的未定义名检查为 0；AST 解析与 `git diff --check` 通过。

### 一次真实生成

目录：[parametric_smoke_20261024_092741](parametric_smoke_20261024_092741/summary.json)。

使用当前配置 **qwen3.8-flash**，关闭思考，以单层 L 形双翼庭院小别墅进行一次功能验证。调用生产设计、材质、计划、执行/重规划、装配和校验函数；仅隔离本地验证会话确认图纸，不修改生产审核节点，也未验证 Studio 中断恢复与前端交互。

| 项目 | 实测 |
| --- | --- |
| 最终状态 | complete |
| 逻辑模型调用 | 13 次，传输记录 13 次 |
| 总耗时 | 97.64 秒 |
| Token | 输入 117,382，输出 9,034，合计 126,416 |
| 标记落实 | 17 / 17 |
| 后端检查 | 17 项通过，0 错误、0 警告 |
| WILD | 18 个基础元素、8 个组合构件 |
| Core | 119 个网格，编译/重建 0 错误、0 警告 |
| 真实渲染 | Chromium/WebGL 白天四视图，已逐张查看 |

证据：[原始 trace](parametric_smoke_20261024_092741/trace.json)、[原始状态](parametric_smoke_20261024_092741/state.json)、[正式 WILD](parametric_smoke_20261024_092741/building.wild)、[Core 日志](parametric_smoke_20261024_092741/core.log)、[渲染清单](parametric_smoke_20261024_092741/render/render_manifest.json)、[透视](parametric_smoke_20261024_092741/render/perspective.png)、[正面](parametric_smoke_20261024_092741/render/front.png)、[侧面](parametric_smoke_20261024_092741/render/side.png)、[俯视](parametric_smoke_20261024_092741/render/top.png)。

WILD SHA256：`3579496f1f54c5ace442ff5be65402e99b5b5f4036978b5be89b7d11d641db03`，与渲染清单输入一致。生成结束时保存的 summary 中 `rendered=false` 是当时状态；后续渲染证据独立保留，没有倒写原始运行。

模型真实采用情况与问题：

- 图纸首次使用参数与重复展开；第一次出现内墙与体量围护重复，第二次局部修订通过。
- 主体首次使用 `walls`，程序展开了 9 面图纸墙；模型把楼板简写放进 geometry，未通过。保留正确墙片段后，下一轮返回原生楼板通过。因此，**这次真实运行没有证明模型成功使用 slabs**；slabs 的证据来自离线生产函数回归。
- 木格栅构件使用参数表达。檐口经历材质角色引用错误、负值表达式写法错误后完成。
- 看图能确认 L 形体量、屋面和开口，但立面层次、入口表达、屋面交接和庭院组织仍显简单，未达到 10 月 23 日参考作品的精细程度。

真实试跑后补齐了材质角色解析、通用 box 尺寸检查，并澄清简写层级和负值表达式格式。没有再调用模型重跑整栋建筑；[validation-latest.json](parametric_smoke_20261024_092741/validation-latest.json) 是最终代码对同一实际产物的新校验快照。真实材质失败回复也通过了新代码的离线回放，详见 verification.json。

### 追加一次屋顶任务调用

用户要求继续后，增加了单个原生构件的确定字段补齐，并用 [native_smoke.py](native_smoke.py) 对同一已批准图纸的两个屋顶做一次独立任务验证，其余构件沿用保存的结果。

[实测汇总](native_smoke_20261024_141757/summary.json)：qwen3.8-flash 调用 **1 次**，10.963 秒，输入 10,202 / 输出 533 token；两个屋顶一次通过。模型采用了参数表达式和材质角色，但仍返回完整字段，**没有采用省略已知字段的写法**。字段自动补齐的采用情况仍只有离线回放证据，不能声称真实模型已经因此缩短输出。

验证脚本首次直接使用旧履约清单评估新实体，且汇总错误对象时序列化失败；已修正脚本。该次 [原始状态](native_smoke_20261024_141757/state.json)、[原始 trace](native_smoke_20261024_141757/trace.json) 与初始候选保持不动，随后对保存状态走正式 `compile_node` 离线装配，**没有新增模型调用**。输出 [compiled.wild](native_smoke_20261024_141757/compiled.wild)，新履约清单与最终检查均通过，Core 编译/重建 0 错误，119 个网格。

[渲染清单](native_smoke_20261024_141757/render/render_manifest.json) 对应 SHA256 `72596d03e90429da4cfe4bfe02384dfbdc1eff2b6335ea895256cfc67bd42462`；四视图真实渲染完成，已查看 [透视图](native_smoke_20261024_141757/render/perspective.png)。它验证了本次局部执行与渲染，没有解决建筑整体构图和细部层次偏弱的问题。

## 当前边界

这次证明计算/展开入口已连通且真实模型会使用其中的能力，不能证明多模型稳定性、成功率改善或成本下降。上述单次用量也不能称为低成本。

程序接管的是明确参数、引用和关系的落实；体量组合、构造选择和审美取舍仍由模型决定。已有生产主链没有因此变成自动截图与视觉修订闭环，本次看图是验证工作。关系冲突继续显式报错，没有放宽验收或删掉设计来制造成功。

## 重放命令

在项目根 PowerShell 执行；环境变量只作用于当前进程。当前运行环境缺少 Windows 目录变量时，Python asyncio 可能出现 WinError 10106，Node 也可能无法初始化，以下设置修复的是启动环境。

```powershell
$env:SystemRoot = [Environment]::GetFolderPath('Windows')
$env:WINDIR = $env:SystemRoot
$env:PYTHONUTF8 = '1'
& '.\wild-server\.venv\Scripts\python.exe' 'docs/10月24日/Agent参数化执行/verify.py'
node wild-web/scripts/validate-generated.mjs 'docs/10月24日/Agent参数化执行/parametric_smoke_20261024_092741/building.wild'
```

[live_smoke.py](live_smoke.py) 是会产生真实模型调用的独立验证入口，单轮上限 18 次调用、360 秒，输出新目录；不属于普通离线重放。
[native_smoke.py](native_smoke.py) 会读取已保存图纸并重新调用屋顶任务，上限 2 次调用、180 秒，同样不属于普通离线重放。
