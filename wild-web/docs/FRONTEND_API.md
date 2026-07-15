# WILD 建筑编辑器 - 前后端接口文档

本文档面向后端开发者，定义前后端通信协议、数据格式和 API 规范。

## 目录

- [通信架构](#通信架构)
- [WebSocket Agent API](#websocket-agent-api)
- [REST API](#rest-api)
- [数据类型定义](#数据类型定义)
- [ScenePatch 协议](#scenepatch-协议)
- [错误处理](#错误处理)

---

## 通信架构

### 协议选择

| 功能 | 协议 | 端点 |
|---|---|---|
| AI Agent 对话 | WebSocket | `ws://localhost:8000/ws/agent` |
| 场景保存/加载 | REST | `http://localhost:8000/api/scenes` |
| 场景校验 | REST | `http://localhost:8000/api/validate` |

### 为什么使用 WebSocket？

Agent 对话需要：
1. **流式响应**: Agent 思考过程实时推送
2. **双向通信**: 用户确认/拒绝 patch
3. **长连接**: 避免频繁建立 HTTP 连接

---

## WebSocket Agent API

### 连接端点

```
ws://localhost:8000/ws/agent
```

### 连接生命周期

```
前端 connect() 
  -> 后端 onopen 
  -> 前端发送 user_message 
  -> 后端返回 agent_step / patch_proposal / agent_reply
  -> 前端应用 patch 或确认
```

### 前端发送的消息类型

#### 1. 用户消息请求

**类型**: `user_message`

**何时发送**: 用户在 AI 对话面板输入消息并点击发送

**数据结构**:

```typescript
{
  type: 'user_message',
  request_id: string,        // 唯一请求 ID，格式: req_${timestamp}_${random}
  session_id: string,        // 会话 ID
  scene_id?: string,         // 场景 ID（可选）
  scene_revision: number,    // 当前场景 revision
  message: string,           // 用户输入的消息
  scene_summary: {           // 场景摘要
    elements_count: number,
    types: string[],         // ['wall', 'column', 'roof']
    bbox?: {
      min: [number, number, number],
      max: [number, number, number]
    },
    materials?: string[]
  },
  selection: string[]        // 当前选中的构件 ID 列表
}
```

**示例**:

```json
{
  "type": "user_message",
  "request_id": "req_1704067200000_abc123",
  "session_id": "session_1704067100000",
  "scene_id": "scene_001",
  "scene_revision": 8,
  "message": "在别墅右侧加一个中式凉亭",
  "scene_summary": {
    "elements_count": 42,
    "types": ["wall", "floor", "roof", "opening", "column"],
    "bbox": {
      "min": [-8, 0, -6],
      "max": [8, 8, 10]
    }
  },
  "selection": []
}
```

---

### 后端返回的消息类型

#### 1. Agent 执行步骤

**类型**: `agent_step`

**何时发送**: Agent 正在执行某个步骤时（可选，用于显示进度）

**数据结构**:

```typescript
{
  type: 'agent_step',
  request_id: string,        // 对应的请求 ID
  stage: string,             // 步骤标识: 'inspecting' / 'planning' / 'validating'
  content: string            // 步骤说明文本
}
```

**示例**:

```json
{
  "type": "agent_step",
  "request_id": "req_1704067200000_abc123",
  "stage": "inspecting",
  "content": "正在读取当前建筑边界和可放置区域。"
}
```

#### 2. Patch 提案

**类型**: `patch_proposal`

**何时发送**: Agent 生成了场景修改方案

**数据结构**:

```typescript
{
  type: 'patch_proposal',
  request_id: string,
  patch: ScenePatch          // 完整的 ScenePatch 对象（见下文）
}
```

**示例**:

```json
{
  "type": "patch_proposal",
  "request_id": "req_1704067200000_abc123",
  "patch": {
    "type": "scene_patch",
    "patch_id": "patch_1704067201000_xyz789",
    "base_revision": 8,
    "source": "agent",
    "mode": "proposal",
    "requires_confirmation": true,
    "operations": [
      {
        "op": "add_element",
        "element": {
          "id": "col_01",
          "type": "column",
          "base": [10, 0, 0],
          "height": 3.5,
          "bottomRadius": 0.25,
          "topRadius": 0.25,
          "material": "red_wood"
        }
      }
    ],
    "summary": "将在别墅右侧添加四根红木柱和一个双层中式屋顶。"
  }
}
```

#### 3. Agent 文本回复

**类型**: `agent_reply`

**何时发送**: Agent 完成处理，返回最终文本消息

**数据结构**:

```typescript
{
  type: 'agent_reply',
  request_id: string,
  content: string            // Agent 的回复文本
}
```

**示例**:

```json
{
  "type": "agent_reply",
  "request_id": "req_1704067200000_abc123",
  "content": "我已生成凉亭方案。请确认后应用到场景。"
}
```

#### 4. 错误响应

**类型**: `error`

**何时发送**: 处理失败时

**数据结构**:

```typescript
{
  type: 'error',
  request_id: string,
  error: string              // 错误信息
}
```

**示例**:

```json
{
  "type": "error",
  "request_id": "req_1704067200000_abc123",
  "error": "无法解析用户意图：描述过于模糊"
}
```

---

## REST API

### 1. 创建场景

**端点**: `POST /api/scenes`

**请求体**:

```json
{
  "name": "新建筑",
  "blueprint": {
    "meta": {
      "version": "1.0",
      "type": "building",
      "name": "新建筑"
    },
    "geometry": {
      "elements": []
    },
    "materials": {}
  }
}
```

**响应**:

```json
{
  "scene_id": "scene_001",
  "revision": 1
}
```

### 2. 获取场景

**端点**: `GET /api/scenes/{scene_id}`

**响应**:

```json
{
  "scene_id": "scene_001",
  "revision": 8,
  "blueprint": {
    "meta": { ... },
    "geometry": { ... }
  }
}
```

### 3. 保存场景

**端点**: `PUT /api/scenes/{scene_id}`

**请求体**:

```json
{
  "revision": 8,
  "blueprint": { ... }
}
```

**响应**:

```json
{
  "success": true,
  "revision": 9
}
```

### 4. 校验场景

**端点**: `POST /api/validate`

**请求体**:

```json
{
  "blueprint": { ... }
}
```

**响应**:

```json
{
  "valid": true,
  "issues": [
    {
      "level": "warning",
      "message": "构件 col_01 引用了不存在的材质: wood",
      "elementId": "col_01"
    }
  ]
}
```

---

## 数据类型定义

### Blueprint 结构

```typescript
interface Blueprint {
  meta: {
    version: string          // "1.0"
    type: string             // "building"
    name: string
    author?: string
    description?: string
  }
  geometry: {
    elements: GeometryElement[]
    templates?: Record<string, GeometryElement>
    instances?: InstanceRef[]
    placements?: Placement[]
  }
  materials?: Record<string, MaterialDef>
  behaviors?: BehaviorsSection
  editor?: EditorMetadata
}
```

### GeometryElement

```typescript
interface GeometryElement {
  id: string                 // 唯一 ID
  type: GeometryElementType  // 构件类型
  [key: string]: unknown     // 根据 type 不同有不同参数
}

type GeometryElementType = 
  | 'wall' 
  | 'floor' 
  | 'column' 
  | 'beam' 
  | 'roof' 
  | 'opening' 
  | 'stair' 
  | 'furniture'
  | 'dense_brick'
  | 'body'
```

### 常用构件参数

#### Wall（墙体）

```typescript
{
  id: string,
  type: 'wall',
  from: [number, number, number],  // 起点坐标
  to: [number, number, number],    // 终点坐标
  height: number,                  // 高度
  thickness: number,               // 厚度
  material?: string                // 材质名称
}
```

#### Column（柱子）

```typescript
{
  id: string,
  type: 'column',
  base: [number, number, number],  // 底部坐标
  height: number,                  // 高度
  bottomRadius: number,            // 底部半径
  topRadius: number,               // 顶部半径
  style?: string,                  // 柱式: 'plain' / 'doric' / 'ionic'
  material?: string
}
```

#### Roof（屋顶）

```typescript
{
  id: string,
  type: 'roof',
  roofType: string,                // 'gable' / 'hip' / '庑殿' / '歇山'
  span: number,                    // 跨度
  depth: number,                   // 进深
  height: number,                  // 高度
  thickness?: number,              // 厚度
  tiers?: number,                  // 层数（重檐）
  material?: string
}
```

#### Floor（地板）

```typescript
{
  id: string,
  type: 'floor',
  region: [number, number, number][], // 多边形顶点
  thickness: number,
  material?: string
}
```

---

## ScenePatch 协议

### 核心概念

**ScenePatch** 是所有场景修改的统一格式，无论来自用户手动操作还是 Agent 建议。

### 完整结构

```typescript
interface ScenePatch {
  type: 'scene_patch',
  patch_id: string,              // 唯一 ID
  base_revision: number,         // 基于哪个 revision
  source: 'user' | 'agent' | 'system',
  mode: 'apply' | 'proposal',    // apply: 直接应用, proposal: 需要确认
  requires_confirmation: boolean, // 是否需要用户确认
  operations: SceneOperation[],  // 操作列表
  summary?: string               // 可选的修改说明
}
```

### 操作类型

#### 1. 添加构件

```typescript
{
  op: 'add_element',
  element: GeometryElement
}
```

**示例**:

```json
{
  "op": "add_element",
  "element": {
    "id": "col_05",
    "type": "column",
    "base": [0, 0, 0],
    "height": 3.5,
    "bottomRadius": 0.25,
    "topRadius": 0.25
  }
}
```

#### 2. 修改构件参数

```typescript
{
  op: 'update_element',
  id: string,                    // 要修改的构件 ID
  changes: Record<string, unknown> // 要修改的字段
}
```

**示例**:

```json
{
  "op": "update_element",
  "id": "col_03",
  "changes": {
    "height": 3.8,
    "bottomRadius": 0.3
  }
}
```

#### 3. 删除构件

```typescript
{
  op: 'remove_element',
  id: string
}
```

#### 4. 添加/更新材质

```typescript
{
  op: 'upsert_material',
  name: string,
  material: {
    name: string,
    baseColor?: [number, number, number],
    metallic?: number,
    roughness?: number
  }
}
```

#### 5. 模板操作

```typescript
// 添加模板
{
  op: 'add_template',
  name: string,
  template: GeometryElement
}

// 更新模板
{
  op: 'update_template',
  name: string,
  changes: Record<string, unknown>
}

// 删除模板
{
  op: 'remove_template',
  name: string
}
```

#### 6. 实例化

```typescript
{
  op: 'add_instance',
  instance: {
    id: string,
    template: string,              // 模板名称
    position?: [number, number, number],
    rotation?: [number, number, number],
    scale?: [number, number, number]
  }
}
```

#### 7. 批量放置

```typescript
{
  op: 'add_placement',
  placement: {
    id: string,
    template: string,
    region: unknown,               // 放置区域
    spacing?: number
  }
}
```

### Patch 应用流程

```
前端收到 patch
  ↓
检查 base_revision 是否匹配当前 revision
  ↓
应用到 Blueprint 副本
  ↓
校验 Blueprint
  ↓
调用 wild-core reconstructEntity (smoke test)
  ↓
成功 → 替换 Blueprint + revision++
失败 → 拒绝 patch 并返回错误
```

### 确认规则

| 操作类型 | 默认是否需要确认 |
|---|---|
| 单个构件添加 | 否 |
| 单个构件修改 | 否 |
| 单个构件删除 | 是 |
| 批量添加（>5个） | 是 |
| 批量删除 | 是 |
| 覆盖整个场景 | 是 |
| 一键整理 | 是 |

---

## 错误处理

### HTTP 错误码

| 状态码 | 含义 |
|---|---|
| 200 | 成功 |
| 400 | 请求格式错误 |
| 404 | 场景不存在 |
| 409 | Revision 冲突 |
| 500 | 服务器内部错误 |

### WebSocket 错误

通过 `error` 类型消息返回：

```json
{
  "type": "error",
  "request_id": "req_xxx",
  "error": "错误描述"
}
```

### 常见错误场景

1. **Revision 冲突**: 前端 patch 基于旧的 revision
2. **Blueprint 校验失败**: 生成的 Blueprint 不符合规范
3. **构件 ID 冲突**: 添加的构件 ID 已存在
4. **材质引用不存在**: 构件引用了未定义的材质
5. **父元素不存在**: opening 的 parentWall 不存在

---

## 前端行为约定

### 1. Revision 管理

- 前端维护当前 `revision`
- 每次成功应用 patch 后 `revision++`
- 发送 patch 时必须包含正确的 `base_revision`

### 2. 选择状态

- 前端将当前选中的构件 ID 通过 `selection` 字段发送
- 后端应优先处理选中的构件（例如"把这个柱子加高"）

### 3. 场景摘要

- 每次发送消息时包含 `scene_summary`
- 帮助 Agent 快速了解当前场景状态
- 避免 Agent 每次都需要读取完整场景

### 4. 确认机制

- 如果 `requires_confirmation: true`，前端会显示确认 UI
- 用户确认后才应用 patch
- 用户可以拒绝 patch

---

## 开发建议

### 后端开发者应该：

1. **严格遵守 ScenePatch 格式**: 所有场景修改都通过 patch
2. **返回完整的 Blueprint**: 不要返回部分字段
3. **设置合理的 requires_confirmation**: 批量操作、删除操作应该需要确认
4. **提供清晰的 summary**: 帮助用户理解 patch 内容
5. **处理 revision 冲突**: 检查 base_revision 是否匹配
6. **校验 Blueprint**: 生成的 Blueprint 应该通过前端的校验器

### 测试建议

1. 使用 WebSocket 客户端工具测试 Agent 通信
2. 准备多种测试场景（空场景、复杂场景）
3. 测试错误场景（revision 冲突、无效 patch）
4. 测试长时间连接和重连
5. 测试并发请求

---

## 示例：完整对话流程

### 1. 用户发送消息

```json
{
  "type": "user_message",
  "request_id": "req_001",
  "session_id": "session_001",
  "scene_id": "scene_001",
  "scene_revision": 8,
  "message": "加一根柱子在中心位置",
  "scene_summary": {
    "elements_count": 12,
    "types": ["wall", "floor"]
  },
  "selection": []
}
```

### 2. Agent 返回步骤（可选）

```json
{
  "type": "agent_step",
  "request_id": "req_001",
  "stage": "planning",
  "content": "正在计算中心位置..."
}
```

### 3. Agent 返回 Patch

```json
{
  "type": "patch_proposal",
  "request_id": "req_001",
  "patch": {
    "type": "scene_patch",
    "patch_id": "patch_001",
    "base_revision": 8,
    "source": "agent",
    "mode": "proposal",
    "requires_confirmation": false,
    "operations": [
      {
        "op": "add_element",
        "element": {
          "id": "col_center",
          "type": "column",
          "base": [0, 0, 0],
          "height": 3.5,
          "bottomRadius": 0.25,
          "topRadius": 0.25
        }
      }
    ],
    "summary": "在场景中心添加一根 3.5 米高的柱子"
  }
}
```

### 4. Agent 返回文本

```json
{
  "type": "agent_reply",
  "request_id": "req_001",
  "content": "已在场景中心添加柱子。"
}
```

### 5. 前端应用 Patch

前端收到 patch 后：
- 检查 `base_revision: 8` 匹配当前 revision
- 应用到 Blueprint
- 校验通过
- 更新 revision 为 9
- 调用 wild-core 重建
- 渲染到 Three.js 场景

---

## 附录

### A. 支持的构件类型完整列表

| 类型 | 中文名 | 主要参数 |
|---|---|---|
| wall | 墙体 | from, to, height, thickness |
| floor | 地板 | region, thickness |
| column | 柱子 | base, height, bottomRadius, topRadius |
| beam | 梁 | from, to, width, height |
| roof | 屋顶 | roofType, span, depth, height |
| opening | 门窗 | parentWall, from, width, height |
| stair | 楼梯 | from, to, steps, width |
| furniture | 家具 | subtype, position, dimensions |
| dense_brick | 密集砖块 | region, brickSize |
| body | 化身 | bodyParts |

### B. 常用材质参数

```typescript
{
  name: string,
  baseColor: [number, number, number],  // RGB [0-1]
  metallic: number,                     // 0-1
  roughness: number,                    // 0-1
  opacity?: number,                     // 0-1
  emissive?: [number, number, number]   // 自发光
}
```

### C. 联系方式

如有疑问，请联系前端团队或查看：
- 前端代码: `wild-web/src/`
- 类型定义: `wild-web/src/types/`
- 架构文档: `架构设计方案.md`
