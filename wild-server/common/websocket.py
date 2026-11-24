"""编辑器在线状态和生成任务共用的事件信封。"""

AGENT_PROTOCOL_VERSION = "1.0"


def versioned_event(payload: dict) -> dict:
    return {**payload, "protocol_version": AGENT_PROTOCOL_VERSION}
