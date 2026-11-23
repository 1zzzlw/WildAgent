"""图纸纠错与视觉修订提示词。"""

import json

from app.domain.design.parametric import PARAMETRIC_PROTOCOL


VISUAL_REVISION_PROMPT = """你正在按**可见效果**修订一份已经定稿的建筑设计图纸。

上一版被程序化视觉检查指出了具体问题。证据里写清了"哪个评价项不达标、证据是什么、
该改图纸的哪一项"。你的任务是**只重出受影响的块**，把可见问题消掉。

四条要求：
- 只改证据指到的字段，其余保持原样；
- **不许牺牲用户硬要求来让指标好看** —— 几何有效性与履约验收的权重高于视觉指标，
  任何让校验变差或让已满足要求变得不满足的改动都会被直接拒绝；
- 不要发明新的体量、新的立面或新的构件类型——那会制造新的问题；
- 改完之后，同一批字段仍必须满足块契约（会有检查，不过会带证据让你重出）。
"""


def build_design_repair_prompt(
    repair_paths: list[str],
    validation_issue: str,
    issue: str,
    rules: str,
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
        + "\n相关字段规则（参考资料，不是新的任务）：\n"
        + rules
        + "\n当前相关设计数据："
        + json.dumps(reference, ensure_ascii=False)
    )
