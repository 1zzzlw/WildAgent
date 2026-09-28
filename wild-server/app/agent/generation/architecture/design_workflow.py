"""设计期"逐块起草"执行器（设计文档 §1.6 的首次成图那一半）。

**只替换"产出 raw_plan"这一段**：块全部落定后交给既有的
``normalize_architecture_plan`` → ``build_design_document_or_error``，下游一行不改。

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

import json
import time as _time
from typing import Any, Awaitable, Callable, Sequence

from loguru import logger

from app.agent.generation.architecture.design_blocks import (
    DesignBlock,
    ordered_blocks,
)
from app.design.openings import opening_kind
from app.llm.client import create_llm
from app.llm.invocation import invoke_llm, merge_token_usage, stream_llm
from app.utils.json_extractor import extract_json_object

#: 每块的尝试次数上限（含首次）。**有界**是硬要求：无界重试会在坏图上烧完预算。
_BLOCK_MAX_ATTEMPTS = 3

#: 上下限**由系统派生**的构件类型：`normalize_architecture_plan` 按立面逐层 pattern 与屋顶算出来，
#: 模型写什么都会被覆盖。⇒ 它们不能作为判块是否合格的依据（见 `check_block_contract`）。
_DERIVED_QUOTA_KINDS = frozenset({"door", "window", "roof"})

ReasoningEmitter = Callable[[str, str], Awaitable[None]]


def _pick_block_fields(raw: Any, block: DesignBlock) -> dict[str, Any]:
    """只取本块负责的字段。模型多写了别的块就丢掉——那些块有它们自己的调用。"""

    if not isinstance(raw, dict):
        return {}
    return {field: raw[field] for field in block.fields if field in raw}


def check_block_contract(
    block: DesignBlock,
    picked: dict[str, Any],
    draft: dict[str, Any],
) -> str:
    """块落定前的就地检查。返回**空串 = 通过**，否则返回给模型看的证据。

    🔴 只写**能精确定义**的不变量。含糊的检查（"体量好不好看""立面节奏对不对"）
    不在这里假装拦——它们不是可判定的。

    当前覆盖：

    - 必填字段必须在（`block.fields` 全到）；
    - `facade`：每面 `ground_pattern` / `upper_pattern` 的**长度必须等于 bays**
      （长度不齐会让下游按 bays 切槽位时静默错位）；
    - `components`：`component_quota` 必须非空，且**不能只写系统会派生的那三类**
      （door/window/roof）——那样这一块等于什么都没贡献。

    🔴 **一条反面教训**：不要拿"下游一定会覆盖的值"当门禁。`door`/`window` 的上下限由
    `normalize_architecture_plan` 按立面 pattern 派生，曾用"必须与实际总数完全相等"去判，
    真模型连错 3 次 ⇒ **整块被丢弃**，连带丢掉这几种真正会被用的配额。
    """

    missing = [field for field in block.fields if field not in picked]
    if missing:
        return f"缺少字段 {missing}"

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
        if not isinstance(quota, dict) or not quota:
            return "component_quota 必须是非空对象"
        # 🔴 **不能拿 door / window / roof 的上下限判块是否合格**：这三类由
        # `normalize_architecture_plan` 按立面逐层 pattern 与屋顶**派生**，模型写什么都会被
        # 原样覆盖（实测：写 min=5 也被改回 1）。
        #
        # 曾经的写法是"必须与 pattern 实际总数完全相等"。2026-09-28 真模型实测：
        # 模型连错 3 次（16/27 vs 实际 18）⇒ **整块 `components` 被判未定稿丢弃** ⇒
        # 连带丢掉 railing / canopy / cornice / chimney / light 这些**真正会被用**的配额，
        # 还白烧了 ~90s 模型时间。用"下游会覆盖的值"当门禁，代价全落在别处。
        contributed = sorted(kind for kind in quota if kind not in _DERIVED_QUOTA_KINDS)
        if not contributed:
            return (
                "component_quota 只写了 door/window/roof —— 这三类的上下限由系统按立面与屋顶派生，"
                "请改写**其他**构件类型（如 railing / canopy / cornice / chimney / light）的配额"
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


def build_block_prompt(
    base_prompt: str,
    block: DesignBlock,
    draft: dict[str, Any],
    defects: Sequence[Any] | None = None,
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
        f"## 本轮必须输出这些字段（且只输出这些）",
        "",
        block.contract,
        "",
        "其余字段**已定稿**，由系统提供；写它们会被忽略，且浪费你的注意力。",
    ]
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
    if block.depends_on:
        lines += [
            "",
            "## 已定稿的前序块（只许引用，不许改写）",
            "",
            "```json",
            json.dumps(settled or {}, ensure_ascii=False, indent=2)[:4000],
            "```",
            "",
            "本块只能引用上面出现过的 id 与尺寸，不得引入新的体量、新的面或新的构件类型。",
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
    level: str,
    thinking_mode: bool,
    on_reasoning_delta: ReasoningEmitter | None = None,
    only_blocks: Sequence[str] | None = None,
    defects: Sequence[Any] | None = None,
    complexity_profile: dict[str, Any] | None = None,
    architecture_profile: dict[str, Any] | None = None,
    allow_probe: bool = True,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """逐块起草，返回 ``(draft, diag)``。

    ``draft`` 只含成功落定的块字段；缺失的块**不阻断**，由下游归一化兜底。
    ``diag`` 记录每块的尝试次数、耗时与最后一条证据，供排查"哪一块最难写"。

    :param only_blocks: 只写这几块（收敛环"只重出受影响的块"用它）。
        ``None`` = 按档位全写。传进来的块名若不在该档位里会被忽略——档位是硬约束。
    :param defects: 上一版编译报出的缺陷。会作为**首轮证据**写进提示词，
        而不是让模型先白写一次再被驳。
    :param allow_probe: 是否把编译器作为**试算工具**交给模型（设计文档 §2.7）。
        工具只回诊断、不回蓝图，模型污染不了产物。
        ⚠️ **思考过程与试算工具不再二选一**（2026-09-28 起）：工具循环那条通道现在
        也能转发 ``reasoning_content``（回调是模型级的，挂在 ``config["callbacks"]`` 上），
        所以思考模式下**同时**有思考文本与工具。差别如实记进 ``diag.probe_tool``。
    """

    draft: dict[str, Any] = {}
    blocks = ordered_blocks(level)
    if only_blocks is not None:
        wanted = {str(name) for name in only_blocks}
        blocks = tuple(block for block in blocks if block.name in wanted)
    diag_blocks: list[dict[str, Any]] = []
    total_usage: dict[str, Any] | None = None
    #: 有没有工具循环可用。**与"要不要流式思考"正交**：`allow_probe` 决定有没有工具，
    #: 思考模式决定要不要转发 reasoning delta，两者可以同时成立（见下方 probe_tool 参数）。
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

    #: 只有"没有工具可用"时才退回纯流式通道（那时才需要单独起一个流式 LLM）。
    use_streaming = thinking_mode and on_reasoning_delta is not None and not probe_specs
    probe_note = {
        "probe_tool": bool(probe_specs),
        "probe_tool_disabled_reason": "" if probe_specs else "调用方关闭了试算工具",
        "probe_tool_calls": 0,
    }
    if not blocks:
        return {}, {
            "level": level,
            "blocks": [],
            "unsettled_blocks": [],
            "token_usage": None,
            "requested_blocks": [str(name) for name in only_blocks or ()],
            **probe_note,
        }

    for block in blocks:
        prompt = build_block_prompt(base_prompt, block, draft, defects)
        attempts = 0
        settled = False
        last_issue = ""
        llm_ms = 0
        llm_chars = 0

        while attempts < _BLOCK_MAX_ATTEMPTS and not settled:
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
                # 🔴 思考模式下 `on_reasoning_delta` 一并交给工具循环转发（回调是模型级的），
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
            total_usage = merge_token_usage(total_usage, usage)

            raw = extract_json_object(content)
            picked = _pick_block_fields(raw, block)
            last_issue = check_block_contract(block, picked, draft) if picked else "输出不是合法 JSON 对象"

            if not last_issue:
                draft.update(picked)
                settled = True
                break

            logger.warning(
                f"[architecture] 设计块 {block.name} 第 {attempts} 次未通过：{last_issue}"
            )
            if on_reasoning_delta is not None:
                await on_reasoning_delta(
                    "architecture",
                    f"\n设计块 {block.name} 未通过（{last_issue}），带证据重出...\n",
                )
            prompt = (
                f"{prompt}\n\n## 上一次输出未通过\n\n证据：{last_issue}\n"
                "请只修正上面指出的问题，重新输出**本轮该块的完整字段**。"
            )

        diag_blocks.append(
            {
                "block": block.name,
                "settled": settled,
                "attempts": attempts,
                "llm_ms": llm_ms,
                "llm_chars": llm_chars,
                "last_issue": last_issue if not settled else "",
            }
        )
        if on_reasoning_delta is not None:
            await on_reasoning_delta(
                "architecture",
                f"\n设计块 {block.name}："
                + ("已定稿\n" if settled else f"未定稿（{last_issue}），交给下游兜底\n"),
            )

    unsettled = [item["block"] for item in diag_blocks if not item["settled"]]
    diag = {
        "level": level,
        "blocks": diag_blocks,
        "unsettled_blocks": unsettled,
        "token_usage": total_usage,
        "requested_blocks": [block.name for block in blocks],
        **probe_note,
    }
    if probe_specs:
        logger.info(f"[architecture] 试算工具本轮被调用 {probe_note['probe_tool_calls']} 次")
    if unsettled:
        logger.warning(f"[architecture] 未定稿的设计块: {unsettled}（交下游归一化兜底）")
    return draft, diag
