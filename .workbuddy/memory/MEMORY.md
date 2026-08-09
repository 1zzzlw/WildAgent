# WildAgent 项目记忆

## 用户偏好（重要，跨会话复用）

### 模型路由偏好
- **后端代码修改任务**：使用 `deepseek-pro` 模型
- **前端代码修改任务**：使用 `kimi-k3` 模型
- 适用：项目内 bug 修复、架构调整、代码优化、新功能开发

备注：本会话被绑定到单一模型实例，偏好用于：未来会话复用、自动化路由、跨任务派发时的子代理选型。

## 项目结构
- 后端 `wild-server/`：FastAPI + LangGraph（多节点精密模式 + 单体 LangChain 模式）
- 前端 `wild-web/`：Vue 3 + TS + Three.js + Pinia
- RAG：`RAGSpecLoader`（Chroma + DashScope embedding）已是默认实现
- 设计文档之间存在矛盾（工具数 16/18、是否 RAG、是否自动 PUT），以代码现状为准

## LangGraph 节点拓扑（精密模式）
入口按用户请求是否需要生成 / 修改分发；详细分支以代码为准。

## 已修复的缺陷（2026-08-06）
详见 `技术解决总结/` 目录三份文档 + `.workbuddy/code-review-2026-08-06.md`
- 后端 B1/B3/B4/B6/B8/B9（ws_agent/spatial_tools/agent_service）
- 前端 F1/F2/F3/F4/F5/F6（scenePatch/sceneStore/renderEntity/AIChatPanel/agentBridge）

## 已知问题（待办，2026-08-06 持续处理）
- AIChatPanel 节点思考可独立折叠（处理中）
- 合并（merge）节点需要补校验+修复+循环思维过程（处理中）
- LangGraph 模式生成质量低（别墅放了很多门、栏杆位置奇怪）—— 提示词和 RAG 调用待优化（处理中）
- Token 消耗未显示（处理中）
