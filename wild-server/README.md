# WildAgent Server

后端提供 FastAPI REST/WebSocket、快速 Agent、LangGraph 精密编排、RAG 与确定性 Blueprint 校验。

正式架构、配置和测试说明见 [`../docs/`](../docs/README.md)，不要在本目录新增阶段总结或修复报告；这类历史材料统一放到 `../docs-dev/wild-server/`。

```powershell
uv sync
uv run uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```
