"""Agent WebSocket 协议的版本化 envelope。"""

AGENT_PROTOCOL_VERSION = "1.0"


def versioned_event(payload: dict) -> dict:
    """复制事件并附加当前协议版本，避免调用方原地修改数据。"""
    event = dict(payload)
    event["protocol_version"] = AGENT_PROTOCOL_VERSION
    return event
