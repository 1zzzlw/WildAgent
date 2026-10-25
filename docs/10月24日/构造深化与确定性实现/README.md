# 构造深化与确定性实现（2026-10-24）

本轮把“模型决定构造，程序实现几何”接到现有建筑主链。模型仍决定形式、比例、分格和材料分工；程序负责坐标、层叠、墙面安装和整组验收。没有增加 LangGraph 节点、模型专属分支或整栋建筑模板。

## 当前行为

1. 首轮图纸集中表达完整体量、空间、洞口和构件意图；移除首轮重复的详细构造协议。
2. `standard/detailed` 图纸通过原校验后、用户审核前，对有尺寸的显式 door/window/cornice 执行至多一次构造深化。没有目标时不调用。
3. 深化只补 `form.construction`，不能改体量、洞口位置/尺寸或增删构件。每个提案组仍经过完整图纸校验；有效组采用，失败组保留原设计，原因记录在诊断和审核警告中。服务异常保留已有图纸；没有新增自动重试。
4. 用户批准后，完整构造直接展开为原生 WILD，走已有 Schema、空间、引用、尺寸、装配与最终验收。这些构件不再调用执行模型或检索。
5. 每组构造整体采用；不能丢掉失败层、柱或窗套后声明成功。构造与实际宿主冲突时给出标记、设计路径和数值，归为设计修订，阻断交付。

三组构造的定义、字段校验、展开和协议集中在 [construction_systems.py](../../../wild-server/app/design/construction_systems.py)：

| 系统 | 模型明确决定 | 程序落实 |
| --- | --- | --- |
| `cornice.layered_band` | 延伸轴、各层高度比例/深度比例/材料 | 保持整体尺寸，逐层生成几何 |
| `door/window.framed_opening` | 框深/框宽、门扇或玻璃、分格、可选门窗套 | 原生真实洞口，框扇分格，沿实际宿主安放装饰 |
| `door.entrance` | 门系统、顶板、檐底、可选前柱及柱底标高 | 同一门与墙确定遮蔽范围、檐底和支承关系 |

门窗套明确 `embed`；入口柱明确 `baseY`，避免将门槛标高自动当成柱底。保留四向墙、斜墙及共墙反向映射的现有坐标语义。支持的是直墙与直线叠层，特殊曲面、侧亮窗或其他造型继续使用原路径，不自动套用这些系统。

新构造依然是设计数据，不增加外部模型资产。原有编辑、物件、特殊构件和离线编译入口保留。清理了首轮与深化阶段重复的构造说明，复用现有宿主定位、验收、材质和片段装配；未删除历史建筑文件。

## 实测发现与修复

- 首次几何验收拒绝窗套背面与墙面完全共面，改为显式嵌入深度；没有放宽校验。
- 运行时门要求 interaction，构造契约现用当前引擎字段 Schema 校验它。
- 墙示意数据在 `ResolvedDesign.model_dump()` 中被排除，深化现在直接传递 `projection_elements`，避免模型猜墙边界。
- 首次渲染发现测试入口柱底沿用了门槛高度，构造增加明确柱底标高；最终测试图纸选取地面标高。
- 真实整楼调用的前两次输出在 JSON 数字位置写了裸算式；原格式修订只传空对象，丢失未解析稿。现在下一轮收到完整原始回复，已有真实失败稿回归。
- 一次真实深化包含三个有效提案、一个错误入口提案。原来一处错误否决整批；现在逐提案组验证完整图纸，采用有效部分，错误提案保留原设计并说明原因。没有猜补框材质或擅自把 `framed_opening` 改成 `entrance`。

## 验证及证据边界

**离线回归：** [verify.py](verify.py) / [verification.json](verification.json) 的 **126 项**通过；前一轮参数化回归 **135 项**仍通过。包括尺寸/平移/四朝向/斜墙、共墙反向定位、漏件拒绝、重复执行、构造冲突阻断、深化局部采用、服务失败保留原稿、真实错误 JSON 的原稿传递。模型和检索替身、冲突注入在脚本中明确标记。

[constructed.wild](constructed.wild) 是固定测试设计与历史主体片段的生产函数装配结果；[design.json](design.json)、[state.json](state.json)、[compile.json](compile.json) 保留完整输入与过程。Core 72 个网格，0 错误；[最终正面图](render-offline-final/front.png) 和 [渲染清单](render-offline-final/render_manifest.json) 来自真实 Chromium/WebGL，已查看入口顶板、檐底、支柱、窗分格与叠层檐口。`render-offline` 是增加柱底参数之前的渲染记录，不代表最终图纸。

**真实整楼试跑：** [construction_smoke_20261024_191241](construction_smoke_20261024_191241/summary.json)，qwen3.8-flash，3 次调用、154.39 秒、50,443 token。前两次 JSON 裸算式，第三次缺少 facades 必填字段，止于图纸阶段。没有可交付建筑，不能记为成功。原始状态、回复和 trace 保留。此后修复了原稿传递、精简首轮协议，但没有再次调用整楼生成；新行为的证据是离线回归。

**一次真实构造深化：** [refinement_smoke_20261024_191923](refinement_smoke_20261024_191923/summary.json)，qwen3.8-flash，1 次调用、14.844 秒，输入 5,770 / 输出 1,048 token。使用之前保存的 L 形图纸，真实模型提出四个构件深化；入口缺少 `frameMaterial`，且在 `framed_opening` 中放入 `canopy`，当时整批未采用。完整回复保存在 [refinement.json](refinement_smoke_20261024_191923/refinement.json)。入口完整字段示例随后补充，但未再调用模型验证新提示词。

**同一真实回复的离线回放：** [refinement_replay_20261024_192237](refinement_replay_20261024_192237/summary.json)。采用两扇窗及叠层檐口，错误入口保留原设计。三个构件的生产执行均为 0 模型调用，其他构件沿用保存片段并重新验收；装配 `complete`、全部 17 个标记落实。产物 [building.wild](refinement_replay_20261024_192237/building.wild)，Core 131 个网格，编译/重建 0 错误、0 警告；[四视图清单](refinement_replay_20261024_192237/render/render_manifest.json) 对应 SHA256 `9f2f0964ca806b8cab36fb5c6d24b2c82534d49f86c0a7df9a520034b62ee2f4`，四张实际渲染均已查看。

这是“一次真实设计输出 + 最终代码离线实现”的证据，不是最终代码完成整栋全新模型生成。首次回放脚本漏传审核版本，没有进入 plan；修复验证脚本后回放通过，两次均未新增模型调用。真实调用、失败稿和初次回放目录未覆盖。

视觉上，测试小屋能确认细部几何；L 形图纸回放仍然保留原来的简单体量、立面组织和屋面交接，未达到 10 月 23 日作品效果。生产主链尚无自动看图修订，这次截图属于人工验证。没有多模型成功率、平均成本下降或 Xiaomi 模型验证结论。

静态检查覆盖本会话 16 个修改/新增业务 Python 文件：未定义名 0，AST 通过，`git diff --check` 通过。

## 重放

项目根 PowerShell：

```powershell
$env:SystemRoot = [Environment]::GetFolderPath('Windows')
$env:WINDIR = $env:SystemRoot
$env:PYTHONUTF8 = '1'
& '.\wild-server\.venv\Scripts\python.exe' 'docs/10月24日/构造深化与确定性实现/verify.py'
& '.\wild-server\.venv\Scripts\python.exe' 'docs/10月24日/构造深化与确定性实现/live_refinement.py' 'docs/10月24日/构造深化与确定性实现/refinement_smoke_20261024_191923/refinement.json'
```

以上两条均不产生真实模型调用。`live_refinement.py` 不传回放文件时才调用真实模型一次；`live_smoke.py` 是独立整楼功能验证，上限 18 次调用、360 秒。仅隔离本地验证会话确认图纸，不改变生产审核节点；各脚本关闭 RAG 自动同步。
