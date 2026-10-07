"""设计节点试算工具（§2.7）的单测。

三条要钉住的东西：

1. **只回诊断、不回蓝图**：工具对外的返回永远是文本，且调用编译器时 mode 恒为 ``probe``；
2. **工具是全函数**：非法 JSON / 非对象 / 归一化抛错 / 编译器抛错，全部转成可读文本，
   **不许**抛出去（工具边界上抛异常＝掐掉整轮生成）；
3. **接线**：``draft_design_blocks`` 在所有通道上真的把工具交出去了，并如实记账；
   思考模式**不再**在"思考过程"与"试算工具"之间二选一（2026-09-28 起）。
"""

from __future__ import annotations

import asyncio
import json

import pytest

from app.agent.compiler import CompileDefect, CompileDefault, CompileResult, MODE_PROBE
from app.agent.generation.architecture import design_workflow
from app.agent.generation.architecture.design_workflow import draft_design_blocks
from app.agent.generation.architecture.probe_tool import (
    PROBE_TOOL_NAME,
    build_probe_tool,
    probe_design_text,
)

_MESSAGE = "生成一个三层别墅"


def _run(coro):
    return asyncio.run(coro)


# ── 一、全函数（任何输入都变成文本）──


def test_invalid_json_returns_readable_text_not_an_exception() -> None:
    text = probe_design_text("这不是 JSON", user_message=_MESSAGE)

    assert text.startswith("❌")
    assert "JSON" in text


def test_non_object_payload_is_refused() -> None:
    assert probe_design_text([1, 2, 3], user_message=_MESSAGE).startswith("❌")
    assert probe_design_text("123", user_message=_MESSAGE).startswith("❌")
    assert probe_design_text(None, user_message=_MESSAGE).startswith("❌")


def test_normalize_failure_becomes_text(monkeypatch) -> None:
    """归一化抛错必须被接住 —— 这是**模型最容易撞到**的一类（它写的就是图纸）。

    实测 ``normalize_architecture_plan`` 有一条 ``ground[entrance_bay - 1]`` 越界会抛
    ``IndexError``；在工具边界上放它出去，客户看到的就是"意图分类之后直接报错"。
    """

    def boom(*_args, **_kwargs):
        raise IndexError("list assignment index out of range")

    monkeypatch.setattr(
        "app.agent.generation.architecture.normalize_architecture_plan", boom
    )
    text = probe_design_text({"massing": {"floors": 3}}, user_message=_MESSAGE)

    assert text.startswith("❌")
    assert "IndexError" in text


def test_compiler_crash_is_reported_not_raised(monkeypatch) -> None:
    """编译器崩溃是我们自己的 bug，但也**不许**从这里穿出去（工具边界）。"""

    def boom(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(
        "app.agent.generation.architecture.probe_tool.compile_design", boom
    )
    text = probe_design_text({"massing": {"floors": 3}}, user_message=_MESSAGE)

    assert text.startswith("❌")
    assert "RuntimeError" in text


# ── 二、只回诊断、不回蓝图 ──


def test_tool_always_compiles_in_probe_mode(monkeypatch) -> None:
    """mode 恒为 ``probe``：该模式 ``blueprint`` / ``design_brief`` 都是 ``None``，
    所以模型再怎么调也拿不到产物（§2.7 的硬边界）。"""

    seen: dict = {}
    real = CompileResult

    def spy(plan, **kwargs):
        seen.update(kwargs)
        seen["plan"] = plan
        return real(mode=kwargs.get("mode", ""), defects=[], defaulted=[])

    monkeypatch.setattr("app.agent.generation.architecture.probe_tool.compile_design", spy)
    text = probe_design_text({"massing": {"floors": 3, "width": 12, "depth": 9}}, user_message=_MESSAGE)

    assert seen["mode"] == MODE_PROBE
    assert isinstance(seen["plan"], dict), "传进编译器的必须是归一化后的图纸"
    # 返回里不许出现蓝图结构。
    assert "geometry" not in text


def test_defects_are_formatted_with_their_design_field(monkeypatch) -> None:
    """缺陷行要带"图纸项"，否则模型只知道错了、不知道改哪一格。"""

    result = CompileResult(
        mode=MODE_PROBE,
        defects=[
            CompileDefect(
                code="opening_out_of_wall",
                severity="error",
                target="door_01",
                evidence="门底标高 3.20 超出宿主墙范围",
                design_field="decisions.facades.front.ground_pattern",
            ),
            CompileDefect(code="noise", severity="warn", target="x", evidence="仅告警"),
        ],
        defaulted=[CompileDefault(target="door_01", field="frameDepth")],
        uncompiled=["elevator"],
    )
    monkeypatch.setattr(
        "app.agent.generation.architecture.probe_tool.compile_design", lambda *_a, **_k: result
    )
    text = probe_design_text({"massing": {"floors": 3}}, user_message=_MESSAGE)

    assert "编不出来" in text
    assert "1 条 error" in text
    assert "decisions.facades.front.ground_pattern" in text
    assert "door_01" in text
    # warn 不进阻断分支，但计数要如实。
    assert "warn 1 条" in text
    assert "elevator" in text  # uncompiled 必须告诉模型"这些不用你写"


def test_partial_draft_reports_what_is_unstated() -> None:
    """只给了体量的草稿：能编译，但"未表态"计数必须如实报出来。

    这是工具最主要的用法——模型在写 facade 之前先问"现在这份图纸还缺什么"。
    """

    text = probe_design_text(
        {"massing": {"floors": 3, "width": 12, "depth": 9}}, user_message=_MESSAGE
    )

    assert "可以被编译" in text
    assert "未表态" in text


# ── 三、工具声明的可调用性（这个仓库栽过的坑）──


def test_built_tool_is_directly_callable() -> None:
    """声明的 ``tool`` 必须能**直接调用**（同 `furniture` 存成 `StructuredTool` 那次事故）。"""

    spec = build_probe_tool(user_message=_MESSAGE)

    assert spec.name == PROBE_TOOL_NAME
    assert spec.max_calls >= 1
    assert callable(spec.tool.func), "工具必须提供可调用的 func，而不是只有装饰器外壳"
    out = spec.tool.func(json.dumps({"massing": {"floors": 3}}))
    assert isinstance(out, str) and out


# ── 四、接线 ──


class _FakeLoopResult:
    def __init__(self, text: str, trace: list | None = None, usage=None):
        self.text = text
        self.trace = trace or []
        self.diag = {"token_usage": usage} if usage else {}


def _patch_run_tool_loop(monkeypatch, result):
    calls: list[dict] = []

    async def fake(**kwargs):
        calls.append(kwargs)
        return result

    # `draft_design_blocks` 里是延迟导入，patch 模块属性即可生效。
    monkeypatch.setattr("app.agent.plan.tool_loop.run_tool_loop", fake)
    return calls


def test_probe_tool_is_handed_to_the_model_on_the_plain_channel(monkeypatch) -> None:
    calls = _patch_run_tool_loop(
        monkeypatch,
        _FakeLoopResult(
            json.dumps({"concept": "试算方案", "massing": {"floors": 3, "width": 12, "depth": 9}, "volumes": []}),
            trace=[{"tool": PROBE_TOOL_NAME}],
            usage={"input": 10, "output": 2, "total": 12},
        ),
    )

    draft, diag = _run(
        draft_design_blocks(
            base_prompt="BASE",
            user_request=_MESSAGE,
            thinking_mode=False,
            only_blocks=["massing"],
        )
    )

    assert calls, "非流式通道上必须真的走工具循环"
    assert [spec.name for spec in calls[0]["tool_specs"]] == [PROBE_TOOL_NAME]
    assert draft["massing"]["floors"] == 3
    assert diag["probe_tool"] is True
    assert diag["probe_tool_calls"] == 1
    # 工具循环的 token 用量必须进总账（否则"这一轮花了多少"会少算）。
    assert diag["token_usage"] == {"input": 10, "output": 2, "total": 12}
    assert diag["unsettled_blocks"] == []


def test_thinking_mode_keeps_both_the_tool_and_the_reasoning_stream(monkeypatch) -> None:
    """思考模式**不再**在"思考过程"与"试算工具"之间二选一（2026-09-28 起）。

    旧实现把这两者做成了互斥，理由是"工具循环经由 `create_agent`，转发不了 reasoning
    delta"。事实是**回调是模型级的**（挂在 `config["callbacks"]` 上），跟图级流无关——
    `agent_service` 的最终回答 agent 早就这么用了。既然不用二选一，就该两个都要。

    🔴 这条断言是"反面判据"：把互斥改回来（比如又让 `probe_specs` 在思考模式下为空），
    它会红。所以别把它当成"顺手的实现细节"改掉。
    """

    calls = _patch_run_tool_loop(monkeypatch, _FakeLoopResult("{}"))
    emitted: list[str] = []

    async def emit(channel: str, delta: str) -> None:
        emitted.append(f"{channel}:{delta}")

    stream_calls: list[dict] = []

    async def fake_stream(*_args, **kwargs):
        stream_calls.append(kwargs)
        raise AssertionError("思考模式+有工具时不该再走纯流式通道")

    monkeypatch.setattr(design_workflow, "stream_llm", fake_stream)
    monkeypatch.setattr(design_workflow, "create_llm", lambda **_kwargs: object())

    _draft, diag = _run(
        draft_design_blocks(
            base_prompt="BASE",
            user_request=_MESSAGE,
            thinking_mode=True,
            on_reasoning_delta=emit,
            only_blocks=["massing"],
        )
    )

    assert calls, "思考模式也必须走工具循环（工具不再被流式通道吃掉）"
    assert calls[0]["thinking_mode"] is True
    assert calls[0]["on_reasoning_delta"] is not None, "思考过程必须交给工具循环转发"
    assert not stream_calls, "同一个块不该既走流式又走工具循环（会调两次模型）"
    assert diag["probe_tool"] is True
    assert diag["probe_tool_disabled_reason"] == ""


def test_tool_loop_reasoning_deltas_are_routed_to_the_architecture_channel(monkeypatch) -> None:
    """工具循环转发的 delta 要带对通道名——前端按通道分流，写错会串到别的阶段。"""

    calls = _patch_run_tool_loop(monkeypatch, _FakeLoopResult("{}"))
    emitted: list[str] = []

    async def emit(channel: str, delta: str) -> None:
        emitted.append(f"{channel}:{delta}")

    monkeypatch.setattr(design_workflow, "create_llm", lambda **_kwargs: object())

    _draft, _diag = _run(
        draft_design_blocks(
            base_prompt="BASE",
            user_request=_MESSAGE,
            thinking_mode=True,
            on_reasoning_delta=emit,
            only_blocks=["massing"],
        )
    )

    forwarder = calls[0]["on_reasoning_delta"]
    assert forwarder is not None
    _run(forwarder("正在试算体量…"))
    # ⚠️ 用 `in` 而不是 `==`：`design_workflow` 自己还会发进度 delta（"设计块 … 未通过…"），
    # 断言集合相等只会钉住与本条无关的文案。
    assert "architecture:正在试算体量…" in emitted


def test_streaming_fallback_when_the_tool_is_turned_off(monkeypatch) -> None:
    """关掉试算 + 思考模式 → 退回纯流式通道，思考过程照样有。

    这是 ``use_streaming`` 现在**唯一**该成立的场合：没有工具可用时，
    不退回流式就既没有工具、也没有思考文本。
    """

    calls = _patch_run_tool_loop(monkeypatch, _FakeLoopResult("{}"))
    emitted: list[str] = []

    async def emit(channel: str, delta: str) -> None:
        emitted.append(f"{channel}:{delta}")

    class _Reply:
        content = json.dumps({"concept": "试算方案", "massing": {"floors": 3, "width": 12, "depth": 9}, "volumes": []})
        token_usage = None

    async def fake_stream(*_args, **kwargs):
        callback = kwargs.get("on_reasoning_delta")
        assert callback is not None, "纯流式通道必须拿到 reasoning 转发器"
        await callback("思考中")
        return _Reply()

    monkeypatch.setattr(design_workflow, "stream_llm", fake_stream)
    monkeypatch.setattr(design_workflow, "create_llm", lambda **_kwargs: object())

    draft, diag = _run(
        draft_design_blocks(
            base_prompt="BASE",
            user_request=_MESSAGE,
            thinking_mode=True,
            on_reasoning_delta=emit,
            only_blocks=["massing"],
            allow_probe=False,
        )
    )

    assert not calls, "关掉试算后不该起工具循环"
    assert "architecture:思考中" in emitted, "纯流式通道的思考过程必须转发出去"
    assert draft["massing"]["floors"] == 3
    assert diag["probe_tool"] is False
    assert "关闭" in diag["probe_tool_disabled_reason"]


def test_caller_can_turn_the_tool_off(monkeypatch) -> None:
    """关掉试算后退回纯 invoke 通道 —— 那条通道也要打桩，否则测试会真的连模型。"""

    calls = _patch_run_tool_loop(monkeypatch, _FakeLoopResult("{}"))

    class _Reply:
        content = json.dumps({"concept": "试算方案", "massing": {"floors": 3, "width": 12, "depth": 9}, "volumes": []})
        token_usage = None

    async def fake_invoke(*_args, **_kwargs):
        return _Reply()

    monkeypatch.setattr(design_workflow, "invoke_llm", fake_invoke)
    monkeypatch.setattr(design_workflow, "create_llm", lambda **_kwargs: object())

    draft, diag = _run(
        draft_design_blocks(
            base_prompt="BASE",
            user_request=_MESSAGE,
            thinking_mode=False,
            only_blocks=["massing"],
            allow_probe=False,
        )
    )

    assert not calls
    assert draft["massing"]["floors"] == 3
    assert diag["probe_tool"] is False
    assert "关闭" in diag["probe_tool_disabled_reason"]


def test_tool_loop_error_is_reraised_as_a_model_failure(monkeypatch) -> None:
    """工具循环**吞掉**模型异常（那是 plan 条目的语义），设计块路径必须把它翻回异常。

    否则"模型服务坏了"会被伪装成"模型不会写这块"，白重试 3 次、最后拿一份默认图纸交付，
    而调用方**再也没有机会**走 `model_failure_result` 终止本轮。
    """

    failing_result = _FakeLoopResult("", trace=[], usage=None)
    failing_result.diag = {"error": "AllocationQuota.FreeTierOnly: Free quota exhausted"}

    async def fake(**_kwargs):
        return failing_result

    monkeypatch.setattr("app.agent.plan.tool_loop.run_tool_loop", fake)

    with pytest.raises(RuntimeError) as excinfo:
        _run(
            draft_design_blocks(
                base_prompt="BASE",
                user_request=_MESSAGE,
                thinking_mode=False,
                only_blocks=["massing"],
            )
        )

    assert "FreeTierOnly" in str(excinfo.value)


def test_empty_block_set_still_reports_probe_state(monkeypatch) -> None:
    """一块都不用写时（`only_blocks` 与块表无交集），诊断字段也必须齐——
    否则前端读 ``diag["probe_tool"]`` 会 KeyError。

    档位粒度已下线（2026-09-30）：`draft_design_blocks` 不再接受 `level`，
    块表恒为全量，所以这里不再按档位参数化。
    """

    _draft, diag = _run(
        draft_design_blocks(
            base_prompt="BASE",
            user_request=_MESSAGE,
            thinking_mode=False,
            only_blocks=["nonexistent"],
        )
    )

    assert diag["blocks"] == []
    assert diag["probe_tool"] is True
    assert diag["probe_tool_calls"] == 0
