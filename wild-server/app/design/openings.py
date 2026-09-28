"""开口 token 的唯一文法（设计文档 §3.3）。

图纸里一个立面槽位就是一个 **开口 token**：

    "window"        —— 只说"这里是窗"，形态由编译器派生（旧值，必须继续支持）
    "door:slide"    —— 显式指定形态
    "empty"         —— 这个开间不开洞（不是构件）

🔴 **为什么只能有一个解析函数**：token 会被四处读——契约校验（`contracts.py`）、
归一化（`planning.py::_normalize_pattern`）、立面编译（`facade.py`）、
已解析设计（`resolver.py`）。分头写 `token.split(":")` 必然分叉，
而这四个地方的分叉**不会报错**，只会让"图纸说的形态"和"编出来的形态"悄悄不一致
（`MEMORY.md`："同一件事被两处解析就会要求收敛"）。所有地方一律走 :func:`split_opening`。

🔴 **form 直接用引擎闭集，不做改名映射**：`form` 的取值域就是 WILD 蓝图
``openingInteractionSpec.mode``（`wild-core/schema.json`）里的 ``swing/slide/lift``，
外加一个 :data:`FIXED_FORM`（``fixed`` = 不可开启，编译时不写 ``interaction``）。

不引入"casement → swing"这类翻译表：图纸到蓝图本来就是"填参数"（编译器 = 解释器），
多一层改名只会多一个会漂移的分叉点，而且两层名字最终仍要对齐引擎。
:func:`test_forms_match_the_engine_interaction_enum` 会把这条口径钉在 schema 上。

🔴 **宽容规则只丢形态，绝不丢开口**（红线"能力缺失只标记不阻断"）：
形态名认不出（模型写了 ``window:casement``）时降级成纯类型 ``"window"``，
让它照常生成、由编译器派生形态；**不能**把整个槽位判成 ``"empty"``——
那等于因为一个形容词拼错就删掉一扇窗。
"""

from __future__ import annotations

from typing import Any

#: 开口类型闭集。``empty`` 不是构件，是"这个开间不开洞"。
OPENING_KINDS: tuple[str, ...] = ("door", "window", "empty")

#: ``form`` 中属于引擎 ``interaction.mode`` 的那部分。
#: 🔴 必须与 `wild-core/schema.json` 的 ``openingInteractionSpec.mode`` 一致（有漂移守卫）。
INTERACTION_FORMS: tuple[str, ...] = ("swing", "slide", "lift")

#: 不是引擎枚举值：``fixed`` = 固定、不可开启 ⇒ 产物里**不写** ``interaction``。
FIXED_FORM = "fixed"

#: 每一类开口允许的形态。**这是数据，不是分支**——加/减形态改这里，不改任何 `if`。
#:
#: - ``door``：门必须能开，所以**不含** ``fixed``（`MEMORY.md`：门构件 ``interaction`` 是必填）。
#: - ``window``：固定窗是真实做法，所以含 ``fixed``；不含 ``lift``（"提升窗"不存在）。
FORMS_BY_KIND: dict[str, frozenset[str]] = {
    "door": frozenset({"swing", "slide", "lift"}),
    "window": frozenset({"swing", "slide", FIXED_FORM}),
}

#: 类型与形态之间的分隔符。
_FORM_SEPARATOR = ":"


def split_opening(token: Any) -> tuple[str, str | None]:
    """``"door:slide"`` → ``("door", "slide")``；``"window"`` → ``("window", None)``。

    返回的 ``kind`` **保证**在 :data:`OPENING_KINDS` 里；认不出的一律降级（不抛异常）。
    """

    if not isinstance(token, str):
        return ("empty", None)
    text = token.strip().lower()
    if not text:
        return ("empty", None)
    kind, _, form = text.partition(_FORM_SEPARATOR)
    kind = kind.strip()
    form = form.strip()
    if kind not in OPENING_KINDS:
        return ("empty", None)
    if kind == "empty" or not form or form not in FORMS_BY_KIND[kind]:
        # `empty` 没有形态；形态名不认识 ⇒ **保留开口、丢掉形态**（不降级成 empty）。
        return (kind, None)
    return (kind, form)


def opening_kind(token: Any) -> str:
    """只要类型。契约校验 / 计数 / ``"door" in pattern`` 这类判断一律用它。"""

    return split_opening(token)[0]


def opening_token(kind: str, form: str | None) -> str:
    """反向组合（归一化回写 pattern 时用）。形态非法时退化成纯类型。"""

    clean = str(kind or "").strip().lower()
    if clean not in OPENING_KINDS:
        return "empty"
    if clean == "empty" or not form:
        return clean
    form_text = str(form).strip().lower()
    if form_text not in FORMS_BY_KIND[clean]:
        return clean
    return f"{clean}{_FORM_SEPARATOR}{form_text}"


__all__ = [
    "FIXED_FORM",
    "FORMS_BY_KIND",
    "INTERACTION_FORMS",
    "OPENING_KINDS",
    "opening_kind",
    "opening_token",
    "split_opening",
]
