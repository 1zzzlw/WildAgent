"""启动一个本地页面，展示当前代码实际编译出的 LangGraph 图。

直接运行：
    python -B tests/show_langgraph_graph.py

仅生成并检查图文件（适合 CI）：
    python -B tests/show_langgraph_graph.py --no-serve
"""

from __future__ import annotations

import argparse
import html
import sys
import tempfile
import webbrowser
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


SERVER_ROOT = Path(__file__).resolve().parents[1]
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def _build_assets(output_dir: Path, enable_callback: bool) -> tuple[Path, Path, int]:
    from app.agent.component_registry import get_implemented_components
    from app.agent.graph import build_generation_graph

    drawable = build_generation_graph(enable_callback=enable_callback).get_graph()
    node_names = set(drawable.nodes)
    required_nodes = {
        "classifier",
        "chat",
        "patch",
        "architecture",
        "skeleton",
        "merge",
        "final_validate",
    }
    if enable_callback:
        required_nodes.add("callback")
    for config in get_implemented_components():
        required_nodes.update({
            f"{config.component_type}_gen",
            f"{config.component_type}_val",
        })
    missing = sorted(required_nodes - node_names)
    if missing:
        raise RuntimeError(f"编译图缺少节点: {', '.join(missing)}")

    mermaid_text = drawable.draw_mermaid()
    output_dir.mkdir(parents=True, exist_ok=True)
    mermaid_path = output_dir / "wildagent_langgraph.mmd"
    html_path = output_dir / "wildagent_langgraph.html"
    mermaid_path.write_text(mermaid_text, encoding="utf-8")
    html_path.write_text(
        _html_document(mermaid_text, enable_callback),
        encoding="utf-8",
    )
    return mermaid_path, html_path, len(node_names)


def _html_document(mermaid_text: str, enable_callback: bool) -> str:
    callback_label = "开启" if enable_callback else "关闭"
    escaped_mermaid = html.escape(mermaid_text)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>WildAgent LangGraph</title>
  <style>
    body {{ margin: 0; padding: 24px; color: #172033; background: #f5f7fb;
            font-family: Inter, "Microsoft YaHei", sans-serif; }}
    main {{ max-width: 1800px; margin: auto; }}
    .panel {{ overflow: auto; padding: 24px; border: 1px solid #dbe2ee;
              border-radius: 14px; background: white; box-shadow: 0 8px 28px #16213e14; }}
    .meta {{ margin: 0 0 16px; color: #5a6578; }}
    .mermaid {{ min-width: 1200px; text-align: center; }}
    details {{ margin-top: 16px; }}
    pre {{ white-space: pre-wrap; word-break: break-word; }}
  </style>
</head>
<body>
  <main>
    <h1>WildAgent 当前 LangGraph</h1>
    <p class="meta">由运行时代码即时编译 · callback：{callback_label}</p>
    <section class="panel"><pre class="mermaid">{escaped_mermaid}</pre></section>
    <details><summary>查看 Mermaid 源码</summary><pre>{escaped_mermaid}</pre></details>
  </main>
  <script type="module">
    import mermaid from "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs";
    mermaid.initialize({{ startOnLoad: true, securityLevel: "loose", theme: "neutral" }});
  </script>
</body>
</html>
"""


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, _format: str, *_args) -> None:
        return


def main() -> int:
    parser = argparse.ArgumentParser(description="展示当前代码实际编译出的 LangGraph 图")
    parser.add_argument(
        "--callback",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="是否包含校验失败后的 callback 回路（默认开启）",
    )
    parser.add_argument(
        "--serve",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="是否启动本地页面并打开浏览器（默认开启）",
    )
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(tempfile.gettempdir()) / "wildagent-langgraph",
    )
    args = parser.parse_args()

    mermaid_path, html_path, node_count = _build_assets(
        args.output_dir.resolve(),
        args.callback,
    )
    print(f"LangGraph 检查通过：{node_count} 个节点")
    print(f"Mermaid: {mermaid_path}")
    print(f"HTML: {html_path}")

    if not args.serve:
        return 0

    handler = partial(_QuietHandler, directory=str(args.output_dir.resolve()))
    server = ThreadingHTTPServer(("127.0.0.1", args.port), handler)
    url = f"http://127.0.0.1:{args.port}/{html_path.name}"
    print(f"浏览器地址：{url}")
    print("按 Ctrl+C 停止展示服务。")
    webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
