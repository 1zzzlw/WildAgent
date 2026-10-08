"""Agent Server / Studio 入口必须能被**真的加载** —— 它是全仓库唯一没人 import 的入口。

背景（2026-10-08 线上事故）：`app/agent/generation/` 分组搬迁后，
`langsmith_tools/studio_graph.py` 仍写着旧路径 `generation.components`，于是
``langgraph dev`` 启动直接 ``GraphLoadError: No module named
'app.agent.generation.components'`` 起不来。

为什么全套守卫都没拦住：那个文件**既不在 `app/` 也不在 `tests/`**，所以
`test_agent_module_boundaries` 的包边界扫描、`check_undefined_names`、
以及所有 `from app... import ...` 的用例都碰不到它。而它是启动必经之路。

本用例按 ``langgraph.json`` 声明的路径与变量名**真的把图加载一遍**，
让"入口腐烂"变成一条会红的用例，而不是等到起服务器才发现。
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

SERVER_ROOT = Path(__file__).resolve().parents[2]
LANGGRAPH_JSON = SERVER_ROOT / "langsmith_tools" / "langgraph.json"


def test_langgraph_config_declares_the_studio_entry():
    assert LANGGRAPH_JSON.is_file(), f"缺少 {LANGGRAPH_JSON}"

    config = json.loads(LANGGRAPH_JSON.read_text(encoding="utf-8"))

    assert config.get("graphs"), "langgraph.json 必须声明至少一张图"


def test_every_declared_graph_can_be_loaded():
    """逐张图按 ``路径:变量`` 加载并取变量 —— 这一步就是启动时炸的地方。"""

    config = json.loads(LANGGRAPH_JSON.read_text(encoding="utf-8"))

    for graph_id, spec in config["graphs"].items():
        path, _, variable = spec.partition(":")
        assert path, f"{graph_id}: 未声明入口文件路径"

        module_path = (SERVER_ROOT / path).resolve()
        assert module_path.is_file(), f"{graph_id}: 入口文件不存在 {module_path}"

        module_spec = importlib.util.spec_from_file_location(
            f"_studio_entry_{graph_id}", module_path
        )
        assert module_spec is not None and module_spec.loader is not None
        module = importlib.util.module_from_spec(module_spec)
        # 不许 try/except：这里要的就是"导入失败就红"，而不是静默跳过。
        module_spec.loader.exec_module(module)

        name = variable or "graph"
        assert getattr(module, name, None) is not None, f"{graph_id}: 缺少变量 {name}"
