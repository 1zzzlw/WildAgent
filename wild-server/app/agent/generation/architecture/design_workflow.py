"""设计期"逐块起草"执行器（设计文档 §1.6 的首次成图那一半）。

块全部落定后交给 ``normalize_architecture_plan`` → ``build_design_document_or_error``。
局部修订读取当前设计的稳定快照，仅返回本轮成功起草的字段。

三条设计取舍：
1. **提示词不重写**：基础提示词仍用 `build_architecture_plan_prompt`（它是调过的），
   本模块只在它后面追加"本轮只写哪一块 + 已定稿内容 + 该块的字段契约"。
   重写一份分块提示词等于把调制好的那份丢掉。
2. **失败不阻断**（用户红线）：某块重试到上限仍不合格，就**留空**交给下游归一化兜底。
   空字段会以 `defaulted` 的口径如实报出来，而不是掐掉整轮生成。
   **模型服务故障**仍按既有语义上抛（由调用方 `model_failure_result` 终止）。
3. **块间不变量就地拦**：能精确定义的就拦（见 `check_block_contract`），
   定义不清的**不假装拦**——把不存在的检查写进注释比不写更糟。

本模块被**两处**复用，共用同一套"块"的定义（设计文档 §1.6 的两半）：

- 首次成图：`architecture_planner` 逐块写全图；
- 缺陷回改：`convergence.py` 按 `design_field` 映射回块，用 ``only_blocks`` **只重出那几块**。
"""

from __future__ import annotations

import asyncio
import json
import time as _time
from copy import deepcopy
from dataclasses import replace
from typing import Any, Awaitable, Callable, Sequence

from loguru import logger

from app.agent.generation.architecture.design_blocks import (
    BLOCK_BY_NAME,
    DesignBlock,
    KnowledgeQuerySpec,
    ordered_blocks,
)
from app.agent.generation.architecture.design_plan import (
    apply_batch_outcomes,
    build_design_plan,
    next_batch,
    start_batch,
)
from app.agent.plan.contracts import PlanItem
from app.design.openings import opening_kind
from app.design.contracts import ComponentInstance, DesignConstraint
from pydantic import ValidationError
from app.llm.client import create_llm
from app.llm.invocation import invoke_llm, merge_token_usage, stream_llm
from app.utils.json_extractor import extract_json_object

#: 每块的尝试次数上限（含首次）。**有界**是硬要求：无界重试会在坏图上烧完预算。
_BLOCK_MAX_ATTEMPTS = 3

#: 每个块级检索意图最多召回的分片数。块提示词要短（§1.6 "短输出"的同一理由），
#: 所以每意图取 2 片、多意图去重后通常 2~6 片，足以覆盖该块最相关的知识。
_BLOCK_PER_QUERY = 2

#: 单块注入的知识文本上限（字符）。超过就按列表序截断：前几片是检索排名最高的，
#: 后面的本来就该被淘汰。**不截单片**（与 Loader 上下文预算同一纪律）。
_BLOCK_KNOWLEDGE_MAX_CHARS = 6000

ReasoningEmitter = Callable[[str, str], Awaitable[None]]


def _pick_block_fields(raw: Any, block: DesignBlock) -> dict[str, Any]:
    """只取本块负责的字段。模型多写了别的块就丢掉——那些块有它们自己的调用。"""

    if not isinstance(raw, dict):
        return {}
    return {field: raw[field] for field in block.fields if field in raw}


def _render_query_text(spec: KnowledgeQuerySpec, user_request: str) -> str:
    """把块级查询模板渲染成真实查询文本。``{request}`` 替换为用户请求。"""

    return spec.text.replace("{request}", user_request or "")


async def retrieve_block_knowledge(
    block: DesignBlock,
    user_request: str,
) -> tuple[str, dict[str, Any]]:
    """起草**前**为本块检索知识（设计文档 §1.5 "RAG 换位置"的设计期落点）。

    返回 ``(文本, 诊断)``。检索失败**不阻断**（返回空文本 + 错误诊断）：
    知识是"能写得更好"的输入，不是"写不出来"的理由——与块留空交兜底同一纪律。
    每条意图必须带 metadata 过滤（与 ``knowledge_tool.py`` 同一安全要求）。
    """

    diag: dict[str, Any] = {
        "queries": 0,
        "chars": 0,
        "hits": [],
        "error": "",
    }
    specs = getattr(block, "knowledge_queries", ()) or ()
    if not specs:
        return "", diag

    from app.spec.loader import SpecQuery

    queries = [
        SpecQuery(_render_query_text(spec, user_request), dict(spec.metadata_filter))
        for spec in specs
    ]
    diag["queries"] = len(queries)
    try:
        from app.services.agent_service import agent_service

        spec_loader = agent_service.spec_loader
    except Exception as exc:  # 基建不可用时如实记账，不阻断生成
        diag["error"] = f"{type(exc).__name__}: {exc}"
        return "", diag

    try:
        text = spec_loader.load_many(queries, per_query=_BLOCK_PER_QUERY)
    except Exception as exc:
        diag["error"] = f"{type(exc).__name__}: {exc}"
        return "", diag

    hits = [
        {
            "source": str(hit.metadata.get("source", "?")),
            "heading": str(hit.metadata.get("heading", "?")),
        }
        for hit in getattr(spec_loader, "last_results", []) or []
    ]
    diag["hits"] = hits
    diag["chars"] = len(text or "")
    if len(text) > _BLOCK_KNOWLEDGE_MAX_CHARS:
        text = text[:_BLOCK_KNOWLEDGE_MAX_CHARS]
    return text, diag


def format_block_knowledge(knowledge_text: str) -> str:
    """把块级检索文本格式化成本块提示词的一个章节。空文本返回空串。"""

    body = (knowledge_text or "").strip()
    if not body:
        return ""
    return (
        "\n\n# 本块专属知识库参考\n\n"
        "以下是检索到的与本块相关的 WILD 规范/形制/组装知识。字段写法与组装关系**以此为准**；"
        "造型取向仍由用户需求决定，知识不得静默改写用户已定的尺寸与风格：\n\n"
        f"{body}"
    )


def _contract_error_notes(errors: list[dict[str, Any]]) -> str:
    """把 pydantic 校验错误译成**能照着改**的中文短句。

    🔴 这段文本是**给模型的重试证据**（`_draft_one` 会把它拼进下一轮提示词），
    不是给人看的日志。旧写法直接 `f"{explicit_errors}"` —— 模型收到的是
    `[{'type': 'model_type', 'loc': (), 'msg': 'Input should be a valid dictionary…',
    'url': 'https://errors.pydantic.dev/2.13/v/model_type'}]`：

    - 字段路径、期望取值、实际值**三样都得自己从 repr 里挖**；
    - 真正的信息（该写哪几个键）完全不在里面。

    现场（2026-10-08）：roof 块连撞三轮、`extra_forbidden` / `model_type` 交替出现，
    模型在"数组"与"单对象"之间来回猜，最后整块作废、屋顶退回默认平屋顶。
    ``url`` 一律丢掉——它只会让模型去猜"是不是该打开那个网址"。
    """

    notes: list[str] = []
    for error in errors:
        path = ".".join(str(part) for part in (error.get("loc") or ())) or "顶层"
        kind = str(error.get("type") or "")
        got = error.get("input")
        context = error.get("ctx") or {}
        if kind == "extra_forbidden":
            notes.append(f"{path} 不是该字段允许的键（写了 {got!r}）")
        elif kind == "missing":
            notes.append(f"{path} 必填，没写")
        elif kind == "model_type":
            notes.append(f"{path} 必须是对象，实际是 {type(got).__name__}")
        elif kind.endswith("_type"):
            notes.append(f"{path} 类型不对（实际 {type(got).__name__} = {got!r}）")
        elif kind == "literal_error":
            notes.append(f"{path} 只能是 {context.get('expected')}，实际 {got!r}")
        elif kind in {"greater_than", "greater_than_equal", "less_than", "less_than_equal"}:
            notes.append(f"{path} 超出取值边界（实际 {got!r}）")
        elif kind.startswith(("string_too", "too_short", "too_long")):
            notes.append(f"{path} 长度不合法（实际 {got!r}）")
        else:
            notes.append(f"{path} 不合法：{error.get('msg')}（实际 {got!r}）")
    return "；".join(notes)


def check_block_contract(
    block: DesignBlock,
    picked: dict[str, Any],
    draft: dict[str, Any],
) -> str:
    """块落定前的就地检查。返回**空串 = 通过**，否则返回给模型看的证据。

    🔴 只写**能精确定义**的不变量。含糊的检查（"体量好不好看""立面节奏对不对"）
    不在这里假装拦——它们不是可判定的。

    当前覆盖：

    - 必填字段必须在（历史输出可省略 components）；
    - `facade`：每面 `ground_pattern` / `upper_pattern` 的**长度必须等于 bays**
      （长度不齐会让下游按 bays 切槽位时静默错位）；
    - `components`：配额是对象、实例满足现有契约；允许不选择额外装饰。

    🔴 **一条反面教训**：不要拿"下游一定会覆盖的值"当门禁。`door`/`window` 的上下限由
    `normalize_architecture_plan` 按立面 pattern 派生，曾用"必须与实际总数完全相等"去判，
    真模型连错 3 次 ⇒ **整块被丢弃**，连带丢掉这几种真正会被用的配额。
    """

    # 历史输出可省略实例；缺失保留旧实例，显式 [] 才表示清空。
    missing = [field for field in block.fields if field not in picked and field not in {"components", "design_constraints"}]
    if missing:
        return f"缺少字段 {missing}"

    # Give invalid explicit values back to the existing bounded block retry before
    # normalization degrades them. The contracts own supported fields and ranges.
    from app.design.contracts import MassingDecision, RoofDecision, StructuralGridDecision, VolumeDecision
    for field, contract in (("massing", MassingDecision), ("roof", RoofDecision),
                            ("structural_grid", StructuralGridDecision)):
        if field not in picked:
            continue
        value = picked[field]
        if field == "roof" and isinstance(value, list):
            # 迁移口径与 `normalize_architecture_plan` 一致：单元素数组就是那个对象。
            if len(value) == 1:
                value = value[0]
            else:
                # 🔴 2026-10-08 现场：模型**按契约写对了**（契约当时命令"多体量必须按体量
                # 分别声明屋顶"），是 schema 收不下（`ArchitectureDecisions.roof` 是**单个**
                # `RoofDecision`）。这种时候证据必须是**形状指令**，不能是 pydantic 的
                # `model_type` repr —— 模型没有任何办法从那句话里猜到"只能写一块"。
                return (
                    "roof 显式值不满足当前协议：只能写**一个对象**，不能是数组"
                    "（一块屋顶的风格模板，恰好 type / ridge_axis / overhang 三个键）。"
                    "多体量（L/U 形）的逐块屋面、出檐与避开内院/天井由系统按 volumes 自动派生，"
                    "**不要**在这里拆成多块。"
                )
        try:
            contract.model_validate(value)
        except ValidationError as exc:
            explicit_errors = [e for e in exc.errors() if e["type"] != "missing"]
            if explicit_errors:
                return (
                    f"{field} 显式值不满足当前协议：{_contract_error_notes(explicit_errors)}。"
                    "请照上面点出的键与取值修订该字段，不能依赖默认替换。"
                )
    if "volumes" in picked:
        volumes = picked["volumes"]
        if not isinstance(volumes, list) or not 1 <= len(volumes) <= 8:
            return "volumes 必须包含 1 到 8 个体量"
        for index, volume in enumerate(volumes):
            try:
                VolumeDecision.model_validate(volume)
            except ValidationError as exc:
                explicit_errors = [e for e in exc.errors() if e["type"] != "missing"]
                if explicit_errors:
                    return (
                        f"volumes[{index}] 显式值不满足当前协议："
                        f"{_contract_error_notes(explicit_errors)}。"
                        "每项必须写全 id、role、x、z、width、depth、start_floor、end_floor。"
                    )

    if "design_constraints" in picked:
        if not isinstance(picked["design_constraints"], list):
            return "design_constraints 必须是数组"
        try:
            for entry in picked["design_constraints"]:
                DesignConstraint.model_validate(entry)
        except (ValueError, TypeError) as exc:
            # `ValidationError` 是 `ValueError` 子类：能译成中文就译（证据是给模型读的）。
            if isinstance(exc, ValidationError):
                explicit_errors = [e for e in exc.errors() if e["type"] != "missing"]
                if explicit_errors:
                    return f"设计决定不满足契约：{_contract_error_notes(explicit_errors)}"
            return f"设计决定不满足契约: {exc}"

    if block.name == "facade":
        facades = picked.get("facades")
        if not isinstance(facades, dict) or not facades:
            return "facades 必须是以 front/back/left/right 为键的非空对象"
        for face, spec in facades.items():
            if not isinstance(spec, dict):
                return f"facades.{face} 必须是对象"
            bays = spec.get("bays")
            if not isinstance(bays, int) or isinstance(bays, bool) or bays < 1:
                return f"facades.{face}.bays 必须是正整数"
            for pattern_key in ("ground_pattern", "upper_pattern"):
                pattern = spec.get(pattern_key)
                if not isinstance(pattern, list):
                    return f"facades.{face}.{pattern_key} 必须是数组"
                if len(pattern) != bays:
                    return (
                        f"facades.{face}.{pattern_key} 长度 {len(pattern)} "
                        f"与 bays {bays} 不一致"
                    )
                for token in pattern:
                    # §3.3：**类型**写错要当场让模型重写（带证据），否则归一化会把它静默
                    # 变成"空槽位"——那是在偷偷丢一扇窗。**形态**名写错不在这里拦：
                    # 归一化只把形容词降级、开口照留（红线：能力缺失只标记、不阻断）。
                    kind = opening_kind(token)
                    if kind == "empty" and str(token).strip().lower() != "empty":
                        return (
                            f"facades.{face}.{pattern_key} 里的 {token!r} 不是合法开口，"
                            "每一项只能是 door／window／empty，或写成 类型:形态"
                        )
                    if pattern_key == "upper_pattern" and kind == "door":
                        return f"facades.{face}.upper_pattern 不允许放 door（{token!r}）"

    if block.name == "components":
        quota = picked.get("component_quota")
        if not isinstance(quota, dict):
            return "component_quota 必须是对象，可以为空"
        instances = picked.get("components", [])
        if not isinstance(instances, list):
            return "components 必须是数组，可以为空"
        for index, instance in enumerate(instances):
            try:
                ComponentInstance.model_validate(instance)
            except ValidationError as exc:
                # 同样是**给模型读的证据**：`f"{exc}"` 是多行 pydantic 报错（含网址），
                # 现场 `form: "modern_flat"` 就撞在这里 ⇒ 换成一行的字段/取值点名单。
                return (
                    f"components[{index}] 不满足实例契约：{_contract_error_notes(exc.errors())}。"
                    "每项必须有 type 与 host；`size` / `form` 是对象，"
                    "`form` 的键必须是引擎字段名。"
                )
    return ""


def describe_defects(defects: Sequence[Any] | None) -> list[str]:
    """把缺陷（``CompileDefect`` 或裸字符串）压成给模型看的一行行证据。

    用 ``getattr`` 而不是直接属性访问：收敛环里传进来的既可能是编译器产出的
    ``CompileDefect``，也可能是单测里手搓的字符串。两者都该能读。
    """

    lines: list[str] = []
    for item in defects or []:
        if isinstance(item, str):
            text = item.strip()
            if text:
                lines.append(text)
            continue
        evidence = str(getattr(item, "evidence", "") or "").strip()
        field = str(getattr(item, "design_field", "") or "").strip()
        if not evidence:
            evidence = str(item).strip()
        if not evidence:
            continue
        lines.append(f"{evidence}（图纸项：{field}）" if field else evidence)
    return lines


def render_block_contract(block: DesignBlock) -> str:
    """渲染块契约里的占位符。

    取值一律来自**唯一来源**——不在块表里另抄一份词表：抄两份的话，来源那边加一个
    成员，提示词就会继续教模型用旧的那套。

    - ``{material_roles}`` → `material.plan.ROLE_SPECS`（构件实例的材质角色名）；
    - ``{shape_enum}`` / ``{shape_volume_members}`` → `architecture.profile._SHAPE_ENUM`
      （体量形状词表，以及其中真有体量派生分支的那几个）。

    为什么必须把词表送到**字段所在的那一轮**：`material_role` 的教训（2026-10-08）
    —— 词表只活在 **另一个节点**的提示词里时，模型只能从检索到的别处借名词，
    于是写出"看起来对、词表不对"的值。`massing.shape` 同理：枚举以前只在
    整份 profile 的 JSON 里出现过，与"你要写的那个字段"隔了一层。
    """

    text = block.contract
    if "{material_roles}" in text:
        from app.agent.generation.material.plan import ROLE_SPECS

        text = text.replace("{material_roles}", "、".join(ROLE_SPECS))
    if "{shape_enum}" in text or "{shape_volume_members}" in text:
        from app.agent.generation.architecture.profile import _SHAPE_ENUM

        text = text.replace("{shape_enum}", "、".join(_SHAPE_ENUM))
        text = text.replace(
            "{shape_volume_members}",
            "、".join(name for name, kind in _SHAPE_ENUM.items() if kind == "volumes"),
        )
    return text


def build_block_prompt(
    base_prompt: str,
    block: DesignBlock,
    draft: dict[str, Any],
    defects: Sequence[Any] | None = None,
    knowledge_text: str = "",
    allow_design_changes: bool = False,
) -> str:
    """基础提示词 + 块级附注。附注只讲"这一轮写什么、别的已定稿、上次错在哪"。"""

    settled = {name: draft[name] for name in draft} if draft else None
    lines = [
        base_prompt,
        "",
        "# 本轮只写一个设计块",
        "",
        f"本轮是**分块起草**，你这一轮只负责 `{block.name}` 块。",
        "",
        # 🔴 只写"这些字段"还不够 —— **键名和嵌套形态**必须一起送到（2026-10-08 事故）：
        # 基础提示词里的"顶层直接给出唯一最终方案的字段"说的是整份方案，分块后它会被
        # 误读成"把子字段平铺到顶层"。现场实测：模型把 `massing` 的子字段
        # （shape/width/depth…）当成了顶层对象、`volumes` 另起一行写成 `volumes: [...]`，
        # 于是整块被判"输出不是合法 JSON 对象"。清单来自 `block.fields`（唯一事实源），
        # 不在这里另抄一份。
        "## 输出形态（先看这一条）",
        "",
        "只输出**一个** JSON 对象，顶层键**恰好**是这 "
        f"{len(block.fields)} 个："
        + "、".join(f"`{name}`" for name in block.fields)
        + "。下面 `- 键名：…` 说的是**那个键里面**该写什么，"
        "不是让你把它的内容平铺到顶层——某个键的值是对象/数组时，子字段必须留在"
        "那个对象/数组里；也不要另起一行写成 `键名: 值`，那不是 JSON。"
        "顶层出现清单之外的键，这一轮就会被判未通过并点名缺了哪些键。",
        "",
        "## 本轮必须输出这些字段（且只输出这些）",
        "",
        render_block_contract(block),
        "",
        "其余字段**已定稿**，由系统提供；写它们会被忽略，且浪费你的注意力。",
    ]
    knowledge_section = format_block_knowledge(knowledge_text)
    if knowledge_section:
        lines.append(knowledge_section)
    issue_lines = describe_defects(defects)
    if issue_lines:
        lines += [
            "",
            "## 上一版图纸编译后报出的缺陷（必须针对这些改）",
            "",
            *(f"- {line}" for line in issue_lines),
            "",
            "只修正上面这些，不要顺手改别的——别的块由它们自己的那一轮负责。",
        ]
    if settled:
        lines += [
            "",
            ("## 当前设计基准（本轮目标块可修订，其他块只读）" if allow_design_changes else "## 已定稿的前序块（只许引用，不许改写）"),
            "",
            "```json",
            json.dumps(settled, ensure_ascii=False, separators=(",", ":")),
            "```",
            "",
            ("当前是设计补全：可在本块契约内修订设计，新增对象必须有需求/缺口依据；其他块保持原样。"
             if allow_design_changes else "本块只能引用上面出现过的 id 与尺寸，不得引入新的体量、新的面或新的构件类型。"),
        ]
    else:
        lines += [
            "",
            "## 这是第一块",
            "",
            "没有任何前序内容可引用；本块的尺寸将决定后面所有块的坐标。",
        ]
    return "\n".join(lines)


async def draft_design_blocks(
    *,
    base_prompt: str,
    user_request: str,
    thinking_mode: bool,
    on_reasoning_delta: ReasoningEmitter | None = None,
    only_blocks: Sequence[str] | None = None,
    defects: Sequence[Any] | None = None,
    complexity_profile: dict[str, Any] | None = None,
    architecture_profile: dict[str, Any] | None = None,
    allow_probe: bool = True,
    current_plan: dict[str, Any] | None = None,
    allow_design_changes: bool = False,
    max_attempts: int | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """逐块起草，返回 ``(draft, diag)``。

    ``draft`` 只含成功落定的块字段；缺失的块**不阻断**，由下游归一化兜底。
    ``diag`` 记录每块的尝试次数、耗时与最后一条证据，供排查"哪一块最难写"。

    :param only_blocks: 只写这几块（收敛环"只重出受影响的块"用它）。
        ``None`` = 按档位全写。传进来的块名若不在该档位里会被忽略——档位是硬约束。
    :param defects: 上一版编译报出的缺陷。会作为**首轮证据**写进提示词，
        而不是让模型先白写一次再被驳。
    :param current_plan: 只读的当前设计。修订失败或字段未返回时，由调用方保留旧值。
    :param allow_probe: 是否把编译器作为**试算工具**交给模型（设计文档 §2.7）。
        工具只回诊断、不回蓝图，模型污染不了产物。
        ⚠️ **思考过程与试算工具不再二选一**（2026-09-28 起）：工具循环那条通道现在
        也能转发 ``reasoning_content``（回调是模型级的，挂在 ``config["callbacks"]`` 上），
        所以思考模式下**同时**有思考文本与工具。差别如实记进 ``diag.probe_tool``。
    """

    # 只读基准与本轮增量分开；未成功重写的字段不会清空旧方案。
    baseline = deepcopy(current_plan or {})
    draft: dict[str, Any] = {}
    blocks = ordered_blocks("standard")  # 固定使用标准档位（粒度选择已下线，2026-09-30）
    if only_blocks is not None:
        wanted = {str(name) for name in only_blocks}
        blocks = tuple(block for block in blocks if block.name in wanted)
    diag_blocks: list[dict[str, Any]] = []
    total_usage: dict[str, Any] | None = None
    #: 有没有工具循环可用。**与"要不要流式思考"正交**：`allow_probe` 决定有没有工具，
    #: 思考模式决定要不要转发 reasoning delta，两者可以同时成立。
    probe_specs: list[Any] = []
    if allow_probe:
        # 延迟导入：`app.agent.plan` 包在导入时会拉起 expand/strategy 等一串模块，
        # 而本模块在 architecture 侧被更早导入。而 `tool_loop` 的 langchain agent
        # 也是按需构建的（见 `build_tool_agent`）。
        from app.agent.generation.architecture.probe_tool import build_probe_tool
        from app.agent.plan.tool_loop import run_tool_loop

        probe_specs = [
            build_probe_tool(
                user_message=user_request,
                complexity_profile=complexity_profile,
                architecture_profile=architecture_profile,
            )
        ]

    #: 只有"没有工具可用"时才退回纯流式通道。
    use_streaming = thinking_mode and on_reasoning_delta is not None and not probe_specs
    probe_note = {
        "probe_tool": bool(probe_specs),
        "probe_tool_disabled_reason": "" if probe_specs else "调用方关闭了试算工具",
        "probe_tool_calls": 0,
    }
    if not blocks:
        return {}, {
            "blocks": [],
            "unsettled_blocks": [],
            "token_usage": None,
            "requested_blocks": [str(name) for name in only_blocks or ()],
            "plan": None,
            "batches": [],
            "knowledge_retrievals": 0,
            "knowledge_chars": 0,
            **probe_note,
        }

    async def _draft_one(
        block: DesignBlock,
        item: PlanItem,
        context: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any] | None, dict[str, Any]]:
        """跑一条设计块：带证据重试，**有界**（``item.run.max_attempts``）。

        本函数只管"把这一块写出来"；下一块是谁、能不能与谁并发，由
        :func:`design_plan.next_batch` 决定 —— 调度不再写在这里。
        """

        if allow_design_changes and "design_constraints" in block.fields:
            block = replace(block, fields=tuple(f for f in block.fields if f != "design_constraints"),
                            contract=block.contract.split("- design_constraints：", 1)[0]
                            + "设计决定已冻结，本轮不要输出 design_constraints。")
        prompt = build_block_prompt(base_prompt, block, context, defects, allow_design_changes=allow_design_changes)
        # 🔴 块级检索（§1.5）在**每次起草尝试前**只做一次：提示词重建（重试时追加
        # "上一次输出未通过"）不重查库。命中进本块提示词，也进诊断。
        knowledge_text = ""
        knowledge_diag: dict[str, Any] = {"queries": 0, "chars": 0, "hits": [], "error": ""}
        try:
            knowledge_text, knowledge_diag = await retrieve_block_knowledge(block, user_request)
            if knowledge_text:
                prompt = build_block_prompt(
                    base_prompt, block, context, defects, knowledge_text=knowledge_text, allow_design_changes=allow_design_changes
                )
        except Exception as exc:  # 检索路径自身的 bug 也不得阻断起草
            knowledge_diag["error"] = f"{type(exc).__name__}: {exc}"
        if knowledge_diag.get("error"):
            logger.warning(
                f"[architecture] 设计块 {block.name} 知识检索失败，继续用基础提示词: "
                f"{knowledge_diag['error']}"
            )
        attempts = 0
        settled = False
        last_issue = ""
        llm_ms = 0
        llm_chars = 0
        usage_total: dict[str, Any] | None = None

        while attempts < item.run.max_attempts and not settled:
            attempts += 1
            started = _time.time()
            content = ""
            usage: dict[str, Any] | None = None
            if use_streaming:
                llm = create_llm(enable_thinking=thinking_mode, streaming=True)

                async def emit_reasoning(delta: str) -> None:
                    assert on_reasoning_delta is not None
                    await on_reasoning_delta("architecture", delta)

                reply = await stream_llm(
                    llm,
                    [
                        {"role": "system", "content": prompt},
                        {"role": "user", "content": user_request},
                    ],
                    on_reasoning_delta=emit_reasoning,
                )
                content, usage = reply.content or "", reply.token_usage
            elif probe_specs:
                # §2.7 试算工具：模型可以先算一遍再交卷。工具只回诊断、不回蓝图，
                # 所以"模型多调几次"不会污染产物；调用次数由 tool_loop 的单条目预算卡死。
                # 思考模式下 `on_reasoning_delta` 一并交给工具循环转发（回调是模型级的），
                # 于是"有思考文本"和"有试算工具"不再互斥——`emit_reasoning` 的签名
                # 与 `run_tool_loop` 期望的 `(delta) -> awaitable` 不同，这里包一层。
                async def emit_from_loop(delta: str) -> None:
                    assert on_reasoning_delta is not None
                    await on_reasoning_delta("architecture", delta)

                loop_result = await run_tool_loop(
                    system_prompt=prompt,
                    user_message=user_request,
                    tool_specs=probe_specs,
                    thinking_mode=thinking_mode,
                    on_reasoning_delta=(
                        emit_from_loop if (thinking_mode and on_reasoning_delta) else None
                    ),
                )
                if loop_result.diag.get("error"):
                    # 🔴 **模型调不通必须上抛**，不能像 plan 条目那样只记诊断：
                    # 调用方要拿它走 `model_failure_result` 终止本轮（"服务坏了"不该被
                    # 伪装成"模型不会写"，更不该按"输出不是 JSON"白重试 3 次）。
                    # `run_tool_loop` 为 plan 条目设计，那里吞掉异常是对的；这里显式翻转。
                    raise RuntimeError(str(loop_result.diag["error"]))
                content = loop_result.text
                usage = loop_result.diag.get("token_usage")
                probe_note["probe_tool_calls"] += len(loop_result.trace)
                if loop_result.trace:
                    logger.info(
                        f"[architecture] 设计块 {block.name} 试算了 {len(loop_result.trace)} 次"
                        f"：{[entry['tool'] for entry in loop_result.trace]}"
                    )
            else:
                reply = await invoke_llm(
                    create_llm(enable_thinking=thinking_mode, streaming=False),
                    [
                        {"role": "system", "content": prompt},
                        {"role": "user", "content": user_request},
                    ],
                )
                content, usage = reply.content or "", reply.token_usage
            llm_ms += int((_time.time() - started) * 1000)
            llm_chars += len(content)
            usage_total = merge_token_usage(usage_total, usage)

            raw = extract_json_object(content)
            picked = _pick_block_fields(raw, block)
            # 🔴 判据分两种，别混成一句话（2026-10-08 事故）：
            #  - `raw is None` 才是"没给出合法 JSON 对象"；
            #  - 给出了对象、只是**顶层键不对**时，必须让 `check_block_contract` 说出
            #    **缺了哪些键** —— 它的 `missing` 分支就是为这一刻写的。
            # 旧写法 `... if picked else "输出不是合法 JSON 对象"` 用"picked 非空"短路，
            # 而这恰恰是 `picked` 恒为空的场景 ⇒ 那句"缺少字段 [...]"**永远够不到**，
            # 模型只收到无从下手的证据，白烧一轮重出。现场：模型把 `massing` 的子字段
            # 平铺到顶层、`volumes` 另起一行，报的就是"输出不是合法 JSON 对象"，
            # 而它缺的其实是 concept／massing／volumes 这三个顶层键。
            if raw is None:
                last_issue = "输出不是合法 JSON 对象"
            else:
                last_issue = check_block_contract(block, picked, context)

            if allow_design_changes and isinstance(raw, dict) and set(raw) - set(block.fields):
                last_issue = "补丁越权：仅允许写入 " + ", ".join(block.fields)
            if not last_issue:
                settled = True
                break

            logger.warning(
                f"[architecture] 设计块 {block.name} 第 {attempts} 次未通过：{last_issue}"
            )
            if on_reasoning_delta is not None:
                await on_reasoning_delta(
                    "architecture:progress",
                    f"\n设计块 {block.name} 未通过（{last_issue}），带证据重出...\n",
                )
            prompt = (
                f"{prompt}\n\n## 上一次输出未通过\n\n证据：{last_issue}\n"
                "请只修正上面指出的问题，重新输出**本轮该块的完整字段**。"
            )

        row = {
            "block": block.name,
            "settled": settled,
            "attempts": attempts,
            "llm_ms": llm_ms,
            "llm_chars": llm_chars,
            "last_issue": last_issue if not settled else "",
            "knowledge": knowledge_diag,
        }
        diag_blocks.append(row)
        if on_reasoning_delta is not None:
            await on_reasoning_delta(
                "architecture:progress",
                f"\n设计块 {block.name}："
                + ("已定稿\n" if settled else f"未定稿（{last_issue}），交给下游兜底\n"),
            )
        return row, usage_total, picked if settled else {}

    # ── plan 驱动：块表确定性展开成条目，批次与并发由 plan 的语义决定 ──
    #
    # 依赖来自块表（**物理约束**，不由模型产出）；并发来自块表的 ``parallel_group``
    # （``shell`` 组 = 结构 / 立面 / 屋顶三块）。这样设计期也是"批次 + 有界重试 +
    # 计划态推导"，而不是另一段写死的串行 for 循环 —— 后者会让 plan 完全碰不到图纸。
    plan = build_design_plan(blocks, level="standard", max_attempts=max_attempts if max_attempts is not None else _BLOCK_MAX_ATTEMPTS)
    batches: list[dict[str, Any]] = []
    while True:
        batch = next_batch(plan)
        if not batch:
            break
        plan = start_batch(plan, batch)
        if on_reasoning_delta is not None and len(batch) > 1:
            await on_reasoning_delta(
                "architecture:progress",
                f"\n### 设计期计划\n本轮并发 {len(batch)} 块（并发组 "
                f"{batch[0].params.get('parallel_group') or '-'}）："
                + "、".join(item.kind for item in batch)
                + "……\n",
            )
        context = deepcopy({**baseline, **draft})
        results = await asyncio.gather(
            *(_draft_one(BLOCK_BY_NAME[item.kind], item, context) for item in batch)
        )
        batches.append(
            {
                "items": [item.id for item in batch],
                "parallel_group": str(batch[0].params.get("parallel_group") or ""),
                "settled": [row["block"] for row, _usage, _patch in results if row["settled"]],
            }
        )
        for _item, (_row, item_usage, picked) in zip(batch, results):
            draft.update(picked)
            total_usage = merge_token_usage(total_usage, item_usage)
        plan = apply_batch_outcomes(
            plan,
            [
                (
                    item.id,
                    bool(row["settled"]),
                    int(row["attempts"]),
                    str(row["last_issue"] or "已定稿"),
                )
                for item, (row, _usage, _patch) in zip(batch, results)
            ],
        )

    # 诊断行按**块表序**回填：执行序会随并发调度变化，而"哪几块未定稿"是给人
    # 与审计看的，顺序必须稳定可复现。
    order = {block.name: index for index, block in enumerate(blocks)}
    ordered_rows = sorted(
        diag_blocks, key=lambda row: order.get(str(row["block"]), len(order))
    )
    unsettled = [row["block"] for row in ordered_rows if not row["settled"]]
    # 块级检索总账：多少次块真的带了知识进提示词、共注入多少字。没有这一行，
    # "知识到底用没被用上"只能去翻每块的嵌套诊断。
    knowledge_totals = {
        "knowledge_retrievals": sum(
            1 for row in diag_blocks if (row.get("knowledge") or {}).get("queries")
        ),
        "knowledge_chars": sum(
            int((row.get("knowledge") or {}).get("chars") or 0) for row in diag_blocks
        ),
    }
    diag = {
        "blocks": ordered_rows,
        "unsettled_blocks": unsettled,
        "token_usage": total_usage,
        "requested_blocks": [block.name for block in blocks],
        **knowledge_totals,
        # 设计期也跑在 plan 的调度语义上；这两项是**审计证据** —— 它们证明批次与
        # 并发是 plan 决定的，而不是另一段写死的 for 循环。
        "plan": plan.model_dump(mode="json"),
        "batches": batches,
        **probe_note,
    }
    if probe_specs:
        logger.info(f"[architecture] 试算工具本轮被调用 {probe_note['probe_tool_calls']} 次")
    if unsettled:
        logger.warning(f"[architecture] 未定稿的设计块: {unsettled}（交下游归一化兜底）")
    return draft, diag
