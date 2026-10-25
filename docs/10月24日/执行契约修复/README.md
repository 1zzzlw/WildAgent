# 执行契约修复与验证

本轮依据[两次真实生成诊断](../最新两次生成诊断/README.md)修改现有执行、参数展开和共享验收入口。保留之前未提交的改动，没有新增 Agent 节点、重试轮数或配置，没有调用真实模型。原始会话、批准图纸和场景文件保持不变。

## 修改内容

| 位置 | 本轮修改 | 保留的边界 |
| --- | --- | --- |
| `app/design/relations.py` | 灯具材质检查按实际编译语义读取 `body[].material` 及缺失时的继承材质 | 显式 body 已覆盖全部材质时，顶层正确材质不能掩盖错误子部件材质 |
| 同上及 `app/agent/plan/construction.py` | 原生家具检查 `dimensions`；按批准中心和高度计算底部锚点，并补齐缺失字段 | 不覆盖已有错误坐标；错误坐标被拒绝并返回期望值。倾斜家具不使用竖直高度换算，列待复核 |
| `construction.py` / `implementation.py` | 展开后及验收共用实体结构校验；原生类型所属容器从能力面读取；错误容器无损归位 | 不丢弃实体，不猜测未知实体类型；重复 ID、尺寸、引用等仍进入原验收 |
| 同上 | 嵌套列表报准确 `/geometry/.../索引` 路径与 `value/values` 写法；行外 `entities`、`lightBody` 等字段报具体结构错误 | 通用参数数组重复仍可生成坐标数组，不把所有数组都强制展平 |
| `app/design/parametric.py` | 缺失字段列出实际可用字段及直接子对象中的候选路径；关键字访问提示 `["from"]`；条件表达式提示使用 `items` | 不增加任意执行能力，不自动猜测字段或改写设计分支 |
| `relations.py` / `construction.py` | 单轴 box 屋面上表面公式由安装与验收共用；自动单坡整板的投影尺寸匹配时，确定性修正 X/Z 中心并留证据 | 不改坡角、板厚、尺寸、Y 标高；显式设计位置、多片复杂屋面和尺寸不匹配时不自动修正 |
| `relations.py` | 裸坡板与实际直墙的屋面底/墙顶关系检查；报告墙段端点、屋面底标高及最大空隙 | 排除共用连续高墙；多实体自定义支承仍列待复核，覆盖正确不宣称完整接合 |

清理了被共享结构校验替代的重复检查，以及原先在执行循环中另做一次的空容器转换。没有清理无关历史代码。

## 真实记录回放结果

1. **第一次四个灯具**：原始正确片段全部通过材质与原验收。错误子部件材质依然被拒；顶层字段无法替错误灯体蒙混过关。
2. **第二次主沙发**：保存回复把 X=15 写成 X=0，当前共享验收和片段接收均拒绝。另用明确标记的“省略图纸已确定字段”样本验证尺寸及底部锚点可由代码补齐；这不代表旧错误坐标直接获准。
3. **第二次厨房**：三项错误重复声明均在几何处理之前报告准确索引和 `values` 提示，不再误报没有实体。
4. **构造深化**：保存的同一段回复仍有 10 项合法、1 项入口不合法。10 项均经过当前 `construct_system → _accept_fragment`，实际几何验收全部通过。入口保持独立拒绝。
5. **车库屋顶**：自动消除约 1.55 厘米的投影中心偏差。但真实渲染显示坡面与墙顶仍有空隙，因此又补上了有限承托检查。最终回放拒绝该候选，指出两侧墙段最大空隙约 1.975 米；与主楼共用的连续高墙不误报。

第 5 项是本轮重要的验证边界：初次只修投影时，候选通过原有检查且能正常渲染，但视觉上明显未完成。证据保存在 [roof-gap-before.png](roof-gap-before.png)、[对应 WILD](roof-gap-before.wild) 和 `roof-gap-before-manifest.json`。最终代码不会将这个裸坡板作为完整屋顶采用；本轮没有代替模型选择或新增屋面支承构造。

## 已执行验证

- [12 组回归](verify.py)：包含真实失败片段、多组家具位置/高度/朝向、屋面 X/Z 坡向、正负坡角、不同跨度/板厚/出檐，以及错误材质、错误尺寸、支承缺失、显式位置不被覆盖、倾斜家具不被误换算等反例。全部通过，见 [after.log](after.log)。
- 原参数化执行回归 **135 项通过**，见 [parametric-regression.log](parametric-regression.log)。
- 原构造系统回归 **126 项通过**，见 [construction-regression.log](construction-regression.log)。日志中的 JSON 提取失败来自刻意提供的无效/截断回复样本。
- [保存回复回放](replay.py)新增真实模型调用 **0 次**。结果见 [replay.json](replay.json)。
- 最终回放局部建筑经当前 Core 编译与重建：**607 meshes，0 错误、0 警告**，见 [core.log](core.log)。
- 进行了四视图真实 WebGL 渲染，并查看透视和顶视图；图片及指纹在 [render](render/render_manifest.json)。
- `git diff --check` 通过。

## 交付物的含义

[replay-second.wild](replay-second.wild) 是离线局部回放产物：在原场景副本中替换 10 项通过验收的构造，并用字段省略样本验证沙发定位。缺少封闭支承的车库屋顶没有采用，其他原先放弃的构件也没有凭空补齐。因此，这个文件不是第二栋建筑已经修复完成的交付证明，也不是新的完整模型生成。

[replay-design.json](replay-design.json) 记录本地回放使用的深化设计副本；不会回写用户的批准设计。`replay.json` 记录构造通过情况、投影修正、屋顶拒绝原因和家具字段补齐。

本轮完成的是已复现执行缺陷的修复及离线验证。尚未重新运行完整模型生成；尚不能据此给出真实成功率、成本降幅或达到 10 月 23 日观感的结论。设计比例、室内动线以及自定义屋面支承仍需后续真实生成和渲染验收。

## 复现命令

在项目根目录执行：

```powershell
$env:SystemRoot = [Environment]::GetFolderPath('Windows')
$env:WINDIR = $env:SystemRoot
$env:PYTHONUTF8 = '1'
.\wild-server\.venv\Scripts\python.exe 'docs/10月24日/执行契约修复/verify.py'
.\wild-server\.venv\Scripts\python.exe 'docs/10月24日/Agent参数化执行/verify.py'
.\wild-server\.venv\Scripts\python.exe 'docs/10月24日/构造深化与确定性实现/verify.py'
.\wild-server\.venv\Scripts\python.exe 'docs/10月24日/执行契约修复/replay.py'
node wild-web/scripts/validate-generated.mjs 'docs/10月24日/执行契约修复/replay-second.wild'
node wild-web/scripts/render-baseline.mjs 'docs/10月24日/执行契约修复/replay-second.wild' 'docs/10月24日/执行契约修复/render' --presentation --time=day --quality=high
```

Windows 工具子进程缺少 `SystemRoot/WINDIR` 时会出现 Python 网络初始化或 Node 随机源初始化错误；上面显式恢复系统目录，不修改项目 `.env`。

`prior-tracked.patch`、两个 `*.before.py` 和 `probe.before.json` 用于区分本轮开始前已有的改动与当时诊断结果，不参与生产执行。
