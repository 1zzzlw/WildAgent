# WildAgent Server

后端提供 FastAPI REST/WebSocket、持久化 LangGraph 工作流、RAG 与 Blueprint 校验。

阅读顺序见 [代码阅读路线](../docs/代码阅读路线.md)，Agent 目录职责见 [app/agent/README.md](app/agent/README.md)。配置和测试说明见 [正式文档](../docs/README.md)。

```powershell
uv sync
uv run uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

图的定义在 [app/agent/graph.py](app/agent/graph.py)，图形查看脚本在 [tests/misc/show_langgraph_graph.py](tests/misc/show_langgraph_graph.py)。
