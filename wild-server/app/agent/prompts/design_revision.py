"""图纸检索与纠错提示词。"""

import json

from app.domain.design.parametric import PARAMETRIC_PROTOCOL


DESIGN_KNOWLEDGE_INSTRUCTION = (
    "如果对某个字段、空间关系或构造表达有具体疑问，可以调用 search_design_knowledge，"
    "每次检索聚焦一个问题。信息足够时直接提交 JSON。"
    "检索内容仅供参考，沿用当前任务的用户要求和图纸契约。"
)


def build_design_repair_prompt(
    repair_paths: list[str],
    validation_issue: str,
    issue: str,
    reference: dict,
) -> str:
    return (
        "你正在修订已有建筑图纸。仅修正校验错误，保留用户要求、其他实例与稳定 ID。"
        '\n只返回 {"operations":[{"op":"add|replace|remove","path":"/字段/下标/属性","value":新值}]}。'
        "path 是相对图纸根的 JSON Pointer；remove 不写 value；数组下标保持当前稿编号。"
        "优先修改具体属性，不能替换已有实体数组或更改稳定 ID。"
        "只有被保留墙完整覆盖的重复墙才能整项 remove；须在同一补丁迁移全部引用并核对新宿主的方向、offset 和标高。"
        "墙删除由程序最后按原稿下标倒序执行；其他实例不能整项删除，也不能用删墙修复部分搭接。"
        "缺少正确楼层的宿主时，可在获准的 /walls/- 追加新墙；不能把二层门窗改挂首层墙。"
        "程序会在副本上应用补丁并重新检查完整图纸。"
        + PARAMETRIC_PROTOCOL
        + "\nfacts.current_design 是当前已展开图纸；补丁路径仍指向展开后的实例。"
        "\n允许修改的范围："
        + json.dumps(repair_paths, ensure_ascii=False)
        + "\n图纸校验错误："
        + validation_issue
        + ("\n上一补丁未通过：" + issue if issue != validation_issue else "")
        + "\n当前相关设计数据："
        + json.dumps(reference, ensure_ascii=False)
    )
