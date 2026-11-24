"""生成错误的用户说明，保持责任环节与实际原因。"""


def _generation_failure_message(node_outputs: dict, final_state: dict) -> str:
    """优先返回真实上游错误，避免骨架失败被笼统的 Blueprint 缺失覆盖。"""
    terminal_model_error = final_state.get("terminal_model_error")
    if isinstance(terminal_model_error, dict) and terminal_model_error.get("user_message"):
        return str(terminal_model_error["user_message"])
    return (
        node_outputs.get("skeleton", {}).get("error")
        or node_outputs.get("execute", {}).get("error")
        or (final_state.get("plan") or {}).get("error")
        or final_state.get("error")
        or "最终 Blueprint 缺失"
    )


def _friendly_graph_error(exc: Exception) -> str:
    """隐藏框架内部提示，向用户说明递归保护真正代表什么。"""
    message = str(exc)
    if "recursion limit" in message.lower() or "graph_recursion_limit" in message.lower():
        return (
            "生成流程超过安全步数，系统已停止，避免继续循环消耗模型额度。"
            "请查看最先失败的节点；若是额度或鉴权错误，请先修复模型服务配置后重新生成。"
        )
    return message
