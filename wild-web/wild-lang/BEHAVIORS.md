# 原语动态系统 v1.0

本文档定义原语语言中所有动态行为——物理属性、动画控制参数和交互脚本。这些参数由原语引擎编译为物理模拟指令和事件处理逻辑，在所有合规客户端上执行结果完全一致。

---

## 一、物理属性 (Physics)

物理属性定义了构件在世界中的物理存在——质量、碰撞体和运动约束。这些参数不定义具体的物理模拟算法，只定义物理世界的初始条件。

### 1.1 顶层字段

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `physics` | object | 否 | 物理属性容器 |

### 1.2 物理属性参数

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `mass` | number | 是 | 质量（千克）。设为 0 表示静态不可移动物体（如建筑结构） |
| `collisionShape` | string | 是 | 碰撞体近似形状，见下方枚举 |
| `constraints` | array | 否 | 运动约束数组 |

**collisionShape 枚举**：

| 值 | 说明 |
|----|------|
| `"box"` | 长方体碰撞盒，紧贴构件的包围盒 |
| `"sphere"` | 球体碰撞，适用于柱体等圆形截面构件 |
| `"capsule"` | 胶囊体，适用于人物或圆柱形动态物体 |
| `"mesh"` | 精确网格碰撞体，使用构件生成的完整三角网格。开销较大，仅用于需要精确碰撞的物体 |

### 1.3 约束 (Constraints)

约束定义了构件之间的机械连接关系。当前支持两种约束类型：

#### hinge — 铰链约束

物体可绕指定轴旋转，模拟门的开合、杠杆的转动等。

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `type` | string | 是 | 固定值 `"hinge"` |
| `target` | string | 是 | 被约束的构件 ID |
| `axis` | string | 是 | 旋转轴：`"x"` / `"y"` / `"z"` |
| `limit` | [number, number] | 否 | 旋转角度范围（度），如 `[0, 90]` 表示可打开 90 度 |

#### slider — 滑动约束

物体可沿指定轴平移，模拟抽屉、拉门等。

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `type` | string | 是 | 固定值 `"slider"` |
| `target` | string | 是 | 被约束的构件 ID |
| `axis` | string | 是 | 滑动轴：`"x"` / `"y"` / `"z"` |
| `limit` | [number, number] | 否 | 滑动范围（米），如 `[0, 1.5]` 表示可拉出 1.5 米 |

### 1.4 示例

```json
{
  "physics": {
    "mass": 20,
    "collisionShape": "box",
    "constraints": [
      {
        "type": "hinge",
        "target": "main_door",
        "axis": "z",
        "limit": [0, 90]
      }
    ]
  }
}
二、动画控制参数 (Animation)
动画控制参数只驱动化身的运动方式，不适用于建筑。它们不存储任何具体的骨骼动画帧，只定义影响运动风格的物理量。原语引擎根据这些参数实时计算化身的运动姿态。

2.1 顶层字段
字段	类型	必需	说明
animation	object	否	动画控制参数容器
2.2 动画控制参数
字段	类型	必需	说明
walkStyle	number	否	步态倾向，0.0（稳重踱步）– 1.0（轻快跳跃）。默认 0.5
posture	number	否	体态倾向，0.0（佝偻）– 1.0（挺拔）。默认 0.7
clothStiffness	number	否	布料刚度，0.0（丝绸般飘动）– 1.0（僵硬如板）。默认 0.6
clothDamping	number	否	布料阻尼，0.0（持续摆动）– 1.0（迅速恢复静态）。默认 0.4
windResponse	number	否	对风的敏感度，0.0（无风响应）– 1.0（完全随风飘动）。默认 0.7
2.3 示例
json
{
  "animation": {
    "walkStyle": 0.3,
    "posture": 0.8,
    "clothStiffness": 0.7,
    "clothDamping": 0.5,
    "windResponse": 0.9
  }
}
2.4 引擎处理说明
所有动画参数在客户端实时计算。相同参数输入 → 相同运动结果输出。

walkStyle 影响步幅、身体起伏幅度和手臂摆动幅度。

clothStiffness 和 clothDamping 影响斗篷和织物的物理模拟参数。

windResponse 控制风动效果对布料的影响程度。

三、交互脚本 (Scripts)
交互脚本定义了事件驱动的行为逻辑。它是一组指令集，由原语引擎内置的极简虚拟机解释执行。脚本不包含任何图灵完备的逻辑——只执行有限的安全指令。

3.1 顶层字段
字段	类型	必需	说明
scripts	array	否	交互脚本数组。每个元素定义了一个事件→动作的映射
3.2 脚本结构
json
{
  "on_click": {
    "condition": "event.target == 'main_door'",
    "actions": [
      { "type": "toggle_hinge", "target": "main_door" },
      { "type": "play_sound", "sound": "door_creak" }
    ]
  }
}
事件类型
事件	说明
on_click	玩家点击/触碰该构件时触发
on_enter	玩家进入该构件的触发器区域时触发
on_leave	玩家离开该构件的触发器区域时触发
未来版本可能扩展更多事件类型。

条件表达式
condition 字段是可选的。若为空，脚本总是执行。条件使用简单的字符串表达式，引擎解析后与事件上下文比较。当前支持的表达式包括：

"event.target == '构件ID'" — 判断被点击/触发的构件 ID

3.3 动作指令集
当前版本支持的指令：

指令	参数	说明
toggle_hinge	target (string)	切换指定铰链约束的启用状态（开↔关）
play_sound	sound (string)	播放指定音效。音效名由客户端音频库解析
set_material	target (string), material (string)	临时改变指定构件的材质为材质库中的另一个材质
show_text	text (string)	在界面上显示文本提示
teleport	destination (Vec3)	将玩家传送至指定局部坐标
3.4 完整示例
json
{
  "scripts": [
    {
      "on_click": {
        "condition": "event.target == 'main_door'",
        "actions": [
          { "type": "toggle_hinge", "target": "main_door" },
          { "type": "play_sound", "sound": "heavy_door_creak" }
        ]
      }
    },
    {
      "on_enter": {
        "actions": [
          { "type": "show_text", "text": "你走进了一个古老的房间。" }
        ]
      }
    },
    {
      "on_click": {
        "condition": "event.target == 'magic_orb'",
        "actions": [
          { "type": "set_material", "target": "chamber_lamp", "material": "lamp_gold" },
          { "type": "play_sound", "sound": "magic_chime" },
          { "type": "show_text", "text": "灯火变成了金色。" }
        ]
      }
    }
  ]
}
3.5 安全性
交互脚本不包含任何图灵完备的逻辑。没有循环、没有变量、没有条件分支（除事件过滤条件外）。

所有指令由原语引擎内置的虚拟机解释执行，不能访问客户端内存、文件系统或网络。

teleport 指令的目的地限制在建筑局部坐标范围内。

play_sound 指令的音效名由客户端审核后的安全音效列表解析。未识别的音效名自动忽略。

四、版本兼容
本文件定义的所有动态原语字段和指令均为 v1.0 标准。未来版本可能增加新的事件类型、新的动作指令或新的动画参数，但不会删除或修改任何已有定义。v1.0 中合法的脚本在 v2.0 中继续有效且语义不变。

许可
本动态系统定义以 MIT 协议开源。任何原语引擎实现可自由引用本文档定义的物理参数、动画模型和指令集。