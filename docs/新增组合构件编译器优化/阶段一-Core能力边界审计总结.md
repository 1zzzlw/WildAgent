# 阶段一：Core 能力边界审计总结

## 阶段目标

在不修改现有渲染行为的前提下，确认 WILD Core、组合构件编译层和后续扩展模块各自应负责什么，并找出组合构件接入现有蓝图链路时必须经过的入口。

## 审计范围

- `wild-web/src/wild-core/types.ts`
- `wild-web/wild-lang/schema.json`
- `wild-web/src/wild-core/src/primitive/registry.ts`
- `wild-web/src/wild-core/src/primitive/parser.ts`
- `wild-web/src/wild-core/src/primitive/resolver.ts`
- `wild-web/src/wild-core/src/primitive/expander.ts`
- `wild-web/src/renderer/wildCoreAdapter.ts`
- `wild-web/src/stores/sceneStore.ts`
- `wild-web/src/types/scenePatch.ts`
- `wild-web/src/wild/scenePatch.ts`
- `wild-server/app/utils/blueprint_parser.py`
- `wild-server/app/tools/spatial_tools.py`
- `wild-server/app/services/agent_service.py`
- `wild-server/app/agent/prompts.py`

## 当前能力结论

当前注册表共有 11 个 builder。

| 类型 | 状态 | 本次定位 |
|---|---|---|
| `primitive` | stable | 通用几何 Core |
| `wall` | stable | 建筑 Core |
| `floor` | stable | 建筑 Core |
| `stair` | stable | 建筑 Core |
| `column` | partial | 结构 Core，继续保留 |
| `beam` | partial | 结构 Core，继续保留 |
| `roof` | partial | 建筑 Core，继续保留 |
| `opening` | partial | 墙体开洞与覆盖面 Core，继续保留 |
| `furniture` | partial | 兼容保留，未来迁移到组合构件或资产层 |
| `body` | partial | 暂时保留，后续单独评估职责 |
| `dense_brick` | experimental | 兼容保留，未来迁移为可选扩展 |

## 本次不直接删除类型的原因

现有 `.wild` 文件、知识库示例和后端生成结果都可能引用 `furniture`、`body` 或 `dense_brick`。直接删除 builder 会破坏旧场景，因此本次采用“兼容保留、建立替代能力、后续迁移”的策略。

## 组合构件层的接入位置

当前前端加载和渲染主链路是：

```text
Blueprint
  → wildCoreAdapter
  → wild-core reconstructEntity
  → Three.js 渲染
```

组合构件编译器应位于 `wildCoreAdapter` 与 `wild-core` 之间。它只接收普通 Blueprint 数据，输出只包含现有 Core 类型的 Blueprint 副本，不直接创建 Three.js 对象。

```text
Blueprint（elements + components）
  → 组合构件编译器
  → Blueprint（展开后的 elements）
  → wild-core
```

## 已确认的可复用坐标规则

`opening.from` 不是普通世界坐标，而是：

```text
[沿父墙起点的距离, 开口底部世界 Y, 墙体法向偏移]
```

门窗编译器可以复用这个规则生成洞口，并根据父墙方向计算门框、窗框和窗棂的世界位置及 Y 轴旋转。第一版只对直线墙生成框体；曲线墙继续保留 opening 能力，但组合框体会返回明确的不支持诊断。

## 已确认的系统改动点

为了让组合构件不只存在于前端测试样例，还能进入真实 AI 工作流，需要同步调整：

1. 前端 Blueprint 类型与 JSON Schema。
2. 独立 TypeScript 编译器和组件注册表。
3. `wildCoreAdapter` 的渲染前编译入口。
4. 前后端 ScenePatch 的组件增删改操作。
5. 后端 Blueprint 轻量校验与空间引用校验。
6. Agent Prompt 与知识库的能力边界说明。
7. 独立 smoke test，并继续执行原有 Core 回归测试。

## 阶段决策

- 本次不新增 `door`、`window`、`railing` 渲染 builder。
- 本次新增的是 `geometry.components` 语义输入和编译能力。
- 编译结果必须只使用现有 `opening`、`primitive`、`beam` 等 Core 类型。
- 编译过程不修改源 Blueprint，避免重复重建时不断追加子元素。
- 子元素 ID 必须由组件 ID 确定性生成，便于诊断和测试。
- 单个组件编译失败不阻止原生构件和其他合法组件渲染，错误以 `COMPONENT_COMPILE_FAILED` 诊断返回。

## 阶段结果

阶段一只完成审计和边界决策，没有改变现有运行行为。下一阶段将在该边界内实现独立编译器基础框架。
