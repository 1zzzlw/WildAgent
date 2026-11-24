"""图纸修订使用的 JSON Pointer 操作。"""

from typing import Any


def pointer_tokens(path: str) -> list[str]:
    return [token.replace("~1", "/").replace("~0", "~") for token in path.lstrip("/").split("/")]

def apply_operation(data: dict[str, Any], op: str, path: str, value: Any) -> None:
    tokens = pointer_tokens(path)
    if not tokens or any(token == "" for token in tokens):
        raise ValueError(f"无效 JSON Pointer: {path}")
    parent: Any = data
    for token in tokens[:-1]:
        if isinstance(parent, list):
            try:
                parent = parent[int(token)]
            except (ValueError, IndexError) as exc:
                raise ValueError(f"路径不存在: {path}") from exc
        elif isinstance(parent, dict) and token in parent:
            parent = parent[token]
        else:
            raise ValueError(f"路径不存在: {path}")
    key = tokens[-1]
    if isinstance(parent, list):
        if key == "-" and op == "add":
            parent.append(value)
            return
        try:
            index = int(key)
        except ValueError as exc:
            raise ValueError(f"列表下标无效: {path}") from exc
        if op == "add":
            if index < 0 or index > len(parent):
                raise ValueError(f"列表下标越界: {path}")
            parent.insert(index, value)
        elif op == "replace":
            if index < 0 or index >= len(parent):
                raise ValueError(f"路径不存在: {path}")
            parent[index] = value
        else:
            if index < 0 or index >= len(parent):
                raise ValueError(f"路径不存在: {path}")
            parent.pop(index)
        return
    if not isinstance(parent, dict):
        raise ValueError(f"路径父节点不可修改: {path}")
    if op == "add":
        parent[key] = value
    elif op == "replace":
        if key not in parent:
            raise ValueError(f"路径不存在: {path}")
        parent[key] = value
    else:
        if key not in parent:
            raise ValueError(f"路径不存在: {path}")
        del parent[key]
