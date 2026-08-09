# WildAgent 文档目录

> 从 0 开始了解项目的阅读顺序。按编号递进阅读，每份文档解决一个层次的问题。

---

## 01 — 项目理念与价值

**文件**：[`README.md`](../README.md)

解决：项目是什么、为什么要做、和市面工具的区别。

内容：
- 项目定位：AI 辅助的参数化 3D 建筑编辑器
- 与 Meshy/Tripo 的本质区别
- 为什么需要 Agent 而不是 prompt 模板
- 应用场景与终局想象

---

## 02 — 架构设计方案

**文件**：[`架构设计方案.md`](../架构设计方案.md)

解决：系统怎么运行、模块边界在哪、代码该改哪里。

内容：
- 产品定义与核心原则
- 当前资产与边界
- 技术选型
- 项目目录结构（代码位置权威索引）
- 核心数据模型（Blueprint / ScenePatch）
- 前端架构（Store / 渲染管线 / 属性面板 / 构件库）
- 后端架构（REST API / WebSocket / Agent 模块）
- Agent 架构（工具清单 / 校验流水线 / LangGraph 规划）

---

## 03 — 项目进展总结

**文件**：[`项目进展总结.md`](../项目进展总结.md)

解决：当前做到哪了、哪些功能已有、哪些还在开发。

内容：
- 三大模块状态总览
- 技术栈清单
- Phase 1-4 开发阶段状态
- 核心架构设计（Blueprint / ScenePatch / 数据流）
- 前端关键模块
- 后端关键模块
- 当前优先级
- 关键文件索引

---

## 04 — 快速熟悉笔记

**文件**：[`agent.md`](../agent.md)

解决：给 AI 和新开发者的快速上下文建立。

内容：
- 项目一句话 + 四条不可破坏的边界
- 顶层结构
- `.wild` / Blueprint 规范要点
- ScenePatch 协议详解
- 前端 `wild-web` 关键目录与数据流
- 后端 `wild-server` 关键目录与 API
- Agent 与校验流水线（18 个工具）
- 运行命令
- 修改代码时的建议入口
- 已知文档差异

---

## 05 — 项目阶段路线文档

**文件**：[`docs/项目阶段路线文档.md`](项目阶段路线文档.md)

解决：六个阶段各自解决什么问题、用了什么技术、为什么选它。

内容：
- Phase 1：前端基础框架（已完成）
- Phase 2：后端 Agent MVP（已完成）
- Phase 3：LangGraph 智能编排（**生成编排已落地，见 `wild-server/app/agent/graph.py`**）
- Phase 4：前端交互与渲染升级（待开始）
- Phase 5：AI 组件模块化（待开始）
- Phase 6：测试部署与稳定化（待开始）
- 技术堆叠关系图
- 核心不变边界

---

## 06 — 从开发到部署完整指南

**文件**：[`docs/从开发到部署完整指南.md`](从开发到部署完整指南.md)

解决：怎么把项目跑起来、怎么部署到服务器。

内容：
- 项目概览与部署架构
- 本地开发环境搭建（前端 + 后端）
- Docker 容器化
- GitLab CI/CD 流水线
- 生产服务器部署
- 环境变量配置
- 常见问题排查

---

## 07 — 服务器环境变量配置

**文件**：[`docs/服务器环境变量配置.md`](服务器环境变量配置.md)

解决：后端部署时 `.env` 文件怎么写。

内容：
- 文件路径与 Jenkins 参数
- `.env` 完整模板
- 每个变量的含义与取值
- 权限设置
- 修改后如何生效

---

## 08 — 前后端接口文档

**文件**：[`wild-web/docs/FRONTEND_API.md`](../wild-web/docs/FRONTEND_API.md)

解决：前后端通信协议、数据格式和 API 规范。

内容：
- 通信架构（WebSocket + REST）
- WebSocket Agent API（消息格式、心跳协议）
- REST API（场景 CRUD）
- 数据类型定义
- ScenePatch 协议
- 错误处理规范

---

## 09 — WILD 语言规范

**目录**：[`wild-web/wild-lang/`](../wild-web/wild-lang/)

解决：`.wild` 文件的完整语法和语义定义。

内容：
- `SPEC.md` — 语言规范总览
- `PRIMITIVES.md` — 通用参数化形体（box/sphere/cylinder/profile_sweep）
- `MATERIALS.md` — 材质系统（PBR 数值 + 纹理）
- `BEHAVIORS.md` — 物理与动画行为
- `VERSIONING.md` — 版本策略（永不删除）
- `SCHEMA.json` — JSON Schema 校验

---

## 10 — RAG 知识库

**目录**：[`wild-server/storage/knowledge_base/`](../wild-server/storage/knowledge_base/)

解决：AI 生成蓝图时参考的规范化知识。

内容：
- `BLUEPRINT-SPEC-MINIMAL.md` — 基础规范（直接注入 System Prompt）
- `BLUEPRINT-SPEC-FULL.md` — 完整规范（进入 RAG 分片）
- `building_types/` — 建筑类型知识（住宅/公建/工业等）
- `components/` — 构件知识（墙/门/窗/屋顶等）
- `recipes/` — 组装配方（低层/高层/大跨等模板）
- `patterns/` — 可复用设计模式

---

## 阅读路径建议

**快速上手**（30 分钟）：
```
01 → 04 → 06（只看"本地开发"部分）→ 跑起来
```

**深入理解**（2-3 小时）：
```
01 → 02 → 03 → 04 → 05
```

**开发实战**：
```
04（修改代码指南）→ 08（接口文档）→ 09（语言规范）→ 10（知识库）
```

**部署上线**：
```
06 → 07
```

---

## 开发过程文档归档

开发过程中产生的技术方案、修复报告、阶段总结等文档，已全部移至 [`docs-dev/`](../docs-dev/) 目录，按原始位置分类存放。

详见 [`docs-dev/README.md`](../docs-dev/README.md)。
