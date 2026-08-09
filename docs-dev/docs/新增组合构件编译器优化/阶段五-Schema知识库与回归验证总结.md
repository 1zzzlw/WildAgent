# 阶段五：Schema、知识库与回归验证总结

## 阶段目标

让组合构件不只在前端编译器中“能够运行”，还要被 WILD Schema、后端解析与校验、Agent 提示词、知识库规范和回归测试共同识别，避免同一种构件在不同链路中出现不同解释。

## Schema 与类型约束

`wild-web/wild-lang/schema.json` 已为 `geometry.components` 增加三个受支持类型：

- `door`
- `window`
- `railing`

Schema 约束覆盖必填字段、正数尺寸、三维坐标、窗棂数量、栏杆横杆层数和禁止额外字段等边界。`geometry.elements` 与 `geometry.components` 仍是两套不同层级：前者是 Core 基础构件，后者是编译器输入。

前后端类型同步增加 `ComponentSpec`，避免页面、ScenePatch 和编译器各自维护互不一致的临时结构。

## 后端链路同步

后端已经同步支持：

- Blueprint 解析时校验 `geometry.components` 的结构与必填字段。
- 基础元素和组合构件共享同一个 ID 命名空间。
- 空场景判断同时考虑 `elements` 与 `components`。
- 空间工具检查门窗的 `parentWall` 引用是否存在且确实为墙体。
- ScenePatch 支持 `add_component`、`update_component`、`remove_component`。
- 场景列表和会话摘要统计组合构件数量。
- Agent 提示词明确要求 `door/window/railing` 只能写入 `geometry.components`。

后端仍保存语义级组合构件，不保存编译器生成的临时基础元素，因而不会在多次加载后反复展开或污染源文件。

## 知识库同步

本阶段使用项目的 `wild-knowledge-ingest` 规范核对并更新了以下知识层：

- `BLUEPRINT-SPEC-MINIMAL.md`：加入可直接生成的门、窗、栏杆最小契约和完整示例。
- `BLUEPRINT-SPEC-FULL.md`：加入组合构件结构、参数和能力边界。
- `components/engine-capability-boundaries.md`：把三个组合构件标记为受支持，并与 Core builder 分开描述。
- `components/proposed-component-extensions.md`：从待实现清单中移除本阶段已落地的基础门窗栏杆能力。
- `components/doors.md`、`components/windows.md`：区分已经支持的静态基础能力与仍处于 proposed 的高级变体。
- `recipes/assembly-templates.md`、`recipes/component-building-matrix.md`：将生成建议改为 `geometry.components`。
- 居住建筑扩展资料和组件目录：更新能力边界与索引说明。

这些修改的目的不是让 RAG 直接输出编译后的 primitive，而是让它先检索业务语义，再生成稳定的组合构件参数，最后由确定性编译器展开。

## 兼容处理

旧 Blueprint 中曾把 `double`、`lattice` 写入 `opening.style`。这两个值表达的是门扇或窗格外观，不是洞口轮廓。解析器现在把它们无歧义地归一化为 `rectangular`，新文档则要求详细门窗改用组合构件。

没有 `geometry.components` 的旧 Blueprint 不经过额外复制或展开，原有 11 种 Core 能力保持不变。

## 验证结果

| 验证项 | 结果 |
|---|---|
| `npm run build` | 通过，TypeScript 类型检查与 Vite 构建成功 |
| `node scripts/check-component-compiler.mjs` | 通过，覆盖门、窗、栏杆展开、错误隔离、ID、Schema、渲染和 ScenePatch |
| `node scripts/check-wild-core.mjs` | 通过，6 份既有 `.wild` 样例、11 项 Core 能力均可重建 |
| 后端 `unittest discover` | 47 项全部通过 |
| 文档规范检查 | 0 个 error，28 个结构类 warning |
| 真实 RAG 分片预览 | 10 份文件生成 190 个 chunk，2 个 oversized atomic warning |
| `git diff --check` | 通过，无空白错误 |

最终回归时，现有 `AgentService` 初始化逻辑同步了知识库索引，日志结果为 `total=337, updated=30, deleted=0`。

## 保留警告及原因

文档规范检查中的 28 个 warning 分为：16 个短章节、7 个仅作为路径容器的标题、4 个长章节和 1 个长代码块。它们不包含无效元数据或无效 JSON；本次没有为了消除统计数字而重写与组合构件无关的历史正文。

真实分片预览保留两个原子块提醒：

1. `BLUEPRINT-SPEC-MINIMAL.md` 的完整小屋 JSON 示例约 2193 字符。保持完整是为了让示例可以被严格解析，避免拆成无法独立理解的半段 JSON。
2. `components/windows.md` 中一个约 978 字符的既有窗型业务片段略高于 900 字符目标，仍保持业务实体完整。

两者都只是 warning，Loader 会完整入库；后续应通过检索评测决定是否拆成“完整样例文件 + 短引用说明”，而不是仅按字符数机械切断。

## 阶段结论

第一批组合构件已经形成完整闭环：

```text
知识库业务规则
  → Agent 生成 geometry.components
  → Schema 与后端校验
  → 组合构件编译器确定性展开
  → wild-core 重建
  → 前端诊断与 ScenePatch 修改
```

本阶段完成的是静态、可重复生成的门、窗、栏杆。交互行为、曲面依附、更多高级构件和大规模性能优化明确留到后续阶段。
