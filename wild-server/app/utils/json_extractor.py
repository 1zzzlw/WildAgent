"""
通用 JSON 提取工具 —— 从 LLM 回复中提取 JSON 对象或数组

消除 door/window/roof/railing 节点中重复的 _extract_component_array 和 _extract_roof_object。

🔴 **为什么不用** ``re.findall(r"\\{[\\s\\S]*\\}")``（2026-10-08 事故）：
那个模式是**贪婪**的，只会产出一个"从第一个 ``{`` 到最后一个 ``}``"的跨度。模型
先写对了对象、后面又多吐一段时（现场实测：``{"shape": "l_shape", ...}`` 换行后接
``volumes: [{"id": "main_volume...`` ），这个跨度必然横跨两段 ⇒ ``json.loads`` 抛
``Extra data: line 2 column 1`` ⇒ 明明拿到了正确对象却报"输出不是合法 JSON 对象"，
白烧一轮模型调用。更糟的是 ``max(matches, key=len)`` 在此时只会**更偏向**那段垃圾
（它更长）。

现在用 ``json.JSONDecoder.raw_decode`` 在**每个** opener 位置试解析：它只吃一个
完整值、天然忽略后面的多余内容 —— "模型多吐了一段"从此不再是错误。取**第一个**
可用值（而不是最长的）：模型把答案写在最前面，后面跟的才是多余内容；"取最长"在
模型连吐多个块（如 ``volumes:``、``facades:``）时会挑错那一段。
"""
import json
import re
from typing import Any, Callable, Iterator

from loguru import logger

#: 日志里截断的文本长度（与旧实现一致）。
_EXCERPT = 200


def extract_json_array(text: str) -> list:
    """从 LLM 回复中提取 JSON 数组。

    空数组 ``[]`` 是**合法答案**（"本次没有片段"），不跳过 —— 调用方自己判空。
    """
    value = _first_json_value(text, "[", lambda item: isinstance(item, list))
    if value is None:
        _log_miss("数组", text)
        return []
    return value


def extract_json_object(text: str) -> dict | None:
    """从 LLM 回复中提取 JSON 对象。

    跳过空对象 ``{}``：对本模块的调用方（设计块字段、材质方案、物件方案、plan
    策略…）空 dict 从来不是有效载荷，继续往后扫才找得到真正的那个。
    """
    value = _first_json_value(text, "{", lambda item: isinstance(item, dict) and bool(item))
    if value is None:
        _log_miss("对象", text)
        return None
    return value


def _first_json_value(
    text: str,
    opener: str,
    accept: Callable[[Any], bool],
) -> Any | None:
    """按"先看围栏、再看全文"的顺序，取第一个被 ``accept`` 接受的完整 JSON 值。

    为什么要扫两趟：``_extract_from_code_block`` 只取**第一个**围栏。模型常把
    分析写成第一个围栏、答案放进第二个围栏 —— 只扫第一个围栏会一无所获。围栏里
    没找到就退回全文扫，两种写法都能命中；正常情况（答案就在第一个围栏里）第一趟
    就返回，不会被正文里顺带提到的对象抢走。
    """

    for source in (_extract_from_code_block(text), text):
        stripped = source.strip() if isinstance(source, str) else ""
        if not stripped:
            continue
        for value in _iter_json_values(stripped, opener):
            if accept(value):
                return value
    return None


def _iter_json_values(text: str, opener: str) -> Iterator[Any]:
    """按出现序产出文本里**每一个**能完整解析出来的 JSON 值。

    在每个 ``opener`` 位置尝试 ``raw_decode``：解析失败（那是正文里的一个花括号、
    或对象被截断）就换下一个位置，不抛给调用方。
    """

    decoder = json.JSONDecoder()
    position = text.find(opener)
    while position != -1:
        try:
            value, _end = decoder.raw_decode(text, position)
        except ValueError:  # JSONDecodeError 是 ValueError 的子类
            pass
        else:
            yield value
        position = text.find(opener, position + 1)


def _extract_from_code_block(text: str) -> str:
    """从 markdown 代码块中提取内容，失败则返回原文"""
    json_block_pattern = r"```(?:json)?\s*\n(.*?)\n```"
    matches = re.findall(json_block_pattern, text, re.DOTALL)

    if matches:
        return matches[0].strip()
    return text.strip()


def _log_miss(kind: str, text: str) -> None:
    """一个完整值都扫不出来时才报 —— 日志文本里不再混进"其实拿到了"的误报。"""

    excerpt = (text or "").strip()[:_EXCERPT]
    logger.error(f"JSON {kind}提取失败（文本里没有完整可解析的{kind}）: {excerpt}")
