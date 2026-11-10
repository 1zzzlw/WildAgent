# 数据化构件配方（recipes）

这里的每份 `.json` 就是一个构件。**加构件不再改引擎**。

## 今天加一个构件要做什么

1. 复制一份现有配方改成你的；
2. 在 `index.ts` 的 `RECIPES` 里加一行 import；
3. 跑 `node wild-web/scripts/component-golden.mjs`。

不需要动：`componentRegistry.ts`、`wild-core/types.ts`、`schema.json`（两份）、
`PropertyPanel.vue`、`LibraryPanel.vue`、`componentDisplay.ts`、
`blockPlacement.ts`、`main.py`。

对比迁移前：加「风扇」要改 9 处（6 处是登记性重复声明）。现在只剩数据。

> 显示名 `label` / 图标 `icon` / 拖入初始值 `defaults` / 材质字段 `materialFields`
> 也写在配方里。构件面板、属性面板、拖入默认值三处全部从配方读 ——
> 所以这三种「面板登记」同样不用改代码。

## 配方结构

| 字段 | 作用 |
|---|---|
| `type` | 对应 `component.type`，全局唯一 |
| `host` | 宿主种类，**闭集**：`position` / `none` / `roof` / `wall` |
| `params` | 参数表，字段名即作用域变量名，同时供属性面板使用 |
| `guards` | 参数校验，`expr` 为假则拒绝编译（替代手写 `throw`） |
| `elements[]` | 元素模板；`id` / `type` / `repeat` / `behavior` 是保留键，其余原样进 element |

### 表达式

任何值写成 `{ "$": "表达式" }` 就参与求值，否则按字面量处理。

作用域变量 = 组件自身的全部字段（`width` / `radius` / `material` …），外加：

| 变量 | 含义 |
|---|---|
| `id` | 组件 id |
| `pos.x / pos.y / pos.z` | `position` 的分量视图（数组没有 `.x`，所以单列） |
| `i` / `n` / `t` | 仅在 `repeat` 内：序号 / 总数 / 归一化进度 |
| `angle` | 仅 `polar`：当前角度（弧度） |

可用函数：`min max abs round floor ceil sqrt hypot clamp if default cos sin tan deg`。
运算符：`+ - * / %`、`== != < <= > >=`、`&& || !`、`a ? b : c`、`a ?? b`。
数值缺失时用 `radius ?? 0.65` 写默认值 —— **不要在配方里另建一层默认值表**。

### 复制

```json
"repeat": { "kind": "polar",  "count": "bladeCount ?? 4" }
"repeat": { "kind": "linear", "count": "slatCount ?? 12", "step": ["0", "0", "0"] }
"repeat": { "kind": "stack",  "count": "floorCount", "stepY": "floorHeight" }
```

单构件副本上限 512，超了直接报错（防止一份坏配方把浏览器打死）。

## 边界（这不是缺陷，是物理边界）

- **宿主角是闭集**。`wall`（沿墙距离/标高/法向偏移 → 世界坐标）、`roof`（屋面高度求解）
  需要读相邻元素，只能由引擎实现。要一种新的宿主语义，仍然得动引擎。
- **行为种类是闭集**。`behavior.kind` 只能是 `rotor` / `elevator` / `light` / `opening` / `none`，
  它们复用 `mechanismRuntime` 已有运行时。要一种新的机构运动（比如液压、卷扬），仍然得动运行时。
- **不跑任意代码**。表达式只解释白名单语法树，`primitive/registry.ts` 的
  「蓝图不能携带或执行 JavaScript」同样适用于这里。加一行 `eval` 就等于把数据格式
  变成代码执行入口。

准确的承诺：新构件落在 **「4 种宿主 × 5 种行为」** 的张成空间内 → 零改引擎；
出了这个空间 → 要动引擎，但改动点是「加一个宿主求解器」或「加一个行为运行时」，
而不是今天这种 9 处散弹式修改。

## 验证

```bash
node wild-web/scripts/component-golden.mjs           # 比对 + 引擎重建 + 面板覆盖
node wild-web/scripts/component-golden.mjs --write    # 只在确认改动是有意的时候
node wild-web/scripts/panel-smoke.mjs                 # 真渲染构件面板，检查条目文案
```

`component-golden.mjs` 做四件事：
1. 原有 12 种构件 + 新构件的 element 序列与基线**逐字段**比对
   （round 到 1e-6 米，浮点末位噪声不会假红）；
2. 真跑一次 `reconstructEntity`，任何 error / 空几何 / 0 三角形都算失败 ——
   编译通过不等于引擎能重建；
3. 能力清单必须包含 fixture 里的每种类型；
4. `getRecipeDefaults()` 必须给出 `position`，且 `buildComponentEntries()` 覆盖全部类型。

`panel-smoke.mjs` 用 vite 的 SSR 通道把 `LibraryPanel.vue` 真渲染成 HTML，
检查关键文案与格子数量 —— 面板漏一格不会让任何类型检查变红。
