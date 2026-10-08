"""体量形状枚举：一处定义、每个成员有归类、与 KB 对得上。

为什么要单独立一个文件：`massing.shape` 曾经有**四套口径互不相认**——
枚举在 `profile._ARCHITECTURE_PROFILES`、几何行为散在 `_fallback_volumes` 的
if-else 与 `facade.py` 里、越界值被 `planning.normalize_architecture_plan`
静默改成 `rectangle`、而 KB 在教模型写第四个名字（`circle`，见
`cone-roof-system.md` / `spherical-shell-massing.md`）。

2026-10-08 实测（真实语料，282 条用户消息 / 85 份设计档）暴露的三件事：
正则命中率 5%，"在庭院里的凉亭"被正则从 `pavilion` 改写成 `courtyard`，
以及 `circle` 这类 KB 教的值会被代码无声吞掉。这个文件把修复后的口径钉住。
"""

from __future__ import annotations

import re
from pathlib import Path

from app.agent.generation.architecture.planning import normalize_architecture_plan
from app.agent.generation.architecture.profile import (
    _ARCHITECTURE_PROFILES,
    _SHAPE_ENUM,
    _SHAPE_LABEL_MAX,
    _fallback_volumes,
    _requested_shape,
)
from app.design.contracts import MassingDecision

#: 兜底函数拿到的"表外标签"参照值（用来证明某个成员真的走了专属分支）。
_UNKNOWN_LABEL = "__not_a_shape__"


def _volume_ids(shape: str, *, width: float = 20.0, depth: float = 14.0, floors: int = 3):
    return [item["id"] for item in _fallback_volumes(width, depth, floors, {"min_volumes": 1}, shape)]


class TestShapeEnumTable:
    """表本身的自洽性。"""

    def test_profile_shapes_is_derived_from_the_table(self):
        assert set(_ARCHITECTURE_PROFILES["custom"]["shapes"]) == set(_SHAPE_ENUM)

    def test_every_member_is_classified(self):
        assert set(_SHAPE_ENUM.values()) <= {"volumes", "plain", "label"}, (
            "形状成员只有三种归类：有专属体量分支 / 无特殊形态 / 仅标签语义"
        )

    def test_members_marked_volumes_really_have_a_branch(self):
        """🔴 标了 `volumes` 就必须真有分支 —— 这是"加了成员忘了加行为"的唯一防线。

        没有它，新成员会被当成"有几何行为"写进文档，实际却静默落回通用体量。
        """

        baseline = _volume_ids(_UNKNOWN_LABEL)
        for shape, kind in sorted(_SHAPE_ENUM.items()):
            produced = _volume_ids(shape)
            if kind == "volumes":
                assert produced != baseline, f"{shape} 标了 volumes 但落回通用体量"
            else:
                assert produced == baseline, (
                    f"{shape} 标了 {kind}（无专属几何行为），却产出了不同的体量：{produced}"
                )

    def test_branches_guarded_by_floor_count_keep_their_single_storey_answer(self):
        # 两个成员的分支都带 `modeled_floors` 前置条件，但含义不同：
        # - `stepped` 要求 >=2 层（单层没有"退台"可言）⇒ 单层落回通用体量；
        # - `u_shape` 有**专门的单层分支**（三段围合）⇒ 单层也有自己的体量。
        # 两条都钉住，免得有人"顺手"把某一边的前置条件删掉而没人发现。
        assert _volume_ids("stepped", floors=1) == _volume_ids(_UNKNOWN_LABEL, floors=1)
        assert _volume_ids("u_shape", floors=1) != _volume_ids(_UNKNOWN_LABEL, floors=1)

    def test_shape_label_bound_matches_the_design_contract(self):
        """标签截断上限必须与契约的 `max_length` 同值 —— 越界会走硬失败。"""

        metadata = MassingDecision.model_fields["shape"].metadata
        bound = next(
            getattr(item, "max_length") for item in metadata if hasattr(item, "max_length")
        )
        assert _SHAPE_LABEL_MAX == bound


class TestShapeNotAFilter:
    """🔴 枚举是**提示词词表**，不是输出闸（项目宪法：禁设"模型能做什么"的允许列表）。"""

    def test_out_of_enum_shape_survives_and_is_recorded(self):
        notes: list[str] = []
        plan = normalize_architecture_plan(
            {"massing": {"shape": "hexagon"}},
            user_message="生成一个六边形平面的茶室",
            normalize_notes=notes,
        )

        assert plan["massing"]["shape"] == "hexagon", "表外形状不得被静默改写成 rectangle"
        assert any("hexagon" in item for item in notes), "表外值必须记账"

    def test_out_of_enum_shape_still_gets_a_generic_massing(self):
        plan = normalize_architecture_plan(
            {"massing": {"shape": "hexagon"}},
            user_message="生成一个六边形平面的茶室",
        )

        assert plan["volumes"], "表外形状仍要有可用体量（按仅标签语义给的通用体量）"

    def test_recorded_notes_are_optional(self):
        # 不传出参 ⇒ 行为与从前一致（6 处生产调用点里只有一处关心记账）。
        plan = normalize_architecture_plan({"massing": {"shape": "hexagon"}}, user_message="x")

        assert plan["massing"]["shape"] == "hexagon"

    def test_long_label_is_trimmed_to_the_contract_bound(self):
        plan = normalize_architecture_plan(
            {"massing": {"shape": "x" * 200}},
            user_message="生成一栋楼",
        )

        assert len(plan["massing"]["shape"]) == _SHAPE_LABEL_MAX


class TestRequestedShapeVocabulary:
    """正则（`_requested_shape`）的唯一职责：**用户显式形状词 > 模型推断**。"""

    def test_explicit_shape_words_are_recognised(self):
        cases = {
            "生成一个U形的住宅": "u_shape",
            "生成一个l型住宅": "l_shape",
            "生成一个回字形平面的合院": "courtyard",
            "生成一个四合院": "courtyard",
            "生成一个矩形的厂房": "rectangle",
        }
        for message, expected in cases.items():
            assert _requested_shape(message) == expected, message

    def test_scene_and_part_words_are_not_shape_statements(self):
        """🔴 回归：场地词/部位词不得被当成形状表态。

        「在庭院里设计一个四角凉亭」在旧实现下被判成 `courtyard`，把模型的
        `pavilion`（与 KB 一致）顶掉了 —— 而两例的 `volumes` 完全相同。
        """

        for message in (
            "在庭院里设计一个四角凉亭，单层，面宽4米",
            "中庭通高的办公楼",
            "生成一栋有退台表现的别墅",
            "围合院落式的住宅",
        ):
            assert _requested_shape(message) is None, f"{message!r} 不该被判成形状表态"

    def test_explicit_shape_word_overrides_the_model_and_is_recorded(self):
        notes: list[str] = []
        plan = normalize_architecture_plan(
            {"massing": {"shape": "pavilion"}},
            user_message="把体量改成 U 形的两层楼",
            normalize_notes=notes,
        )

        assert plan["massing"]["shape"] == "u_shape"
        assert any("覆盖" in item and "pavilion" in item for item in notes), notes

    def test_no_note_when_the_user_shape_agrees_with_the_model(self):
        notes: list[str] = []
        plan = normalize_architecture_plan(
            {"massing": {"shape": "u_shape"}},
            user_message="把体量改成 U 形的两层楼",
            normalize_notes=notes,
        )

        assert plan["massing"]["shape"] == "u_shape"
        assert notes == [], "一致时不该记成'覆盖'"


class TestShapeVocabularyReachesTheDraftingPrompt:
    """词表必须出现在**写 `massing.shape` 的那一轮**的提示词里。

    以前枚举只藏在整份 profile 的 JSON 里（`build_architecture_plan_prompt` 的
    "当前引擎物理边界是：{…}"），与"你要写的那个字段"隔了一层；而 `material_role`
    的教训就是"词表只活在另一个节点的提示词里 ⇒ 模型只能从别处借名词"。
    """

    def test_massing_block_contract_renders_the_shape_vocabulary(self):
        from app.agent.generation.architecture.design_blocks import BLOCK_BY_NAME
        from app.agent.generation.architecture.design_workflow import render_block_contract

        text = render_block_contract(BLOCK_BY_NAME["massing"])

        assert "{shape_enum}" not in text, "占位符没被渲染，模型看到的是花括号"
        assert "{shape_volume_members}" not in text
        missing = [name for name in _SHAPE_ENUM if name not in text]
        assert missing == [], f"枚举里这些成员没进提示词：{missing}"
        volume_members = "、".join(
            name for name, kind in _SHAPE_ENUM.items() if kind == "volumes"
        )
        assert volume_members in text, "必须告诉模型哪几个成员才有体量派生，别让它以为表外的也有"


class TestKnowledgeBaseShapeVocabulary:
    """🔴 KB 是"什么算合法"的第二实现：它教的取值必须是枚举成员。

    这条守卫是 `circle` 的发现机制：`cone-roof-system.md` 与
    `spherical-shell-massing.md` 都教模型写 `massing.shape: "circle"`，
    而它当时不在枚举里 ⇒ 被静默改成 `rectangle`。
    """

    _KB_ROOT = Path(__file__).resolve().parents[2] / "storage" / "knowledge_base" / "knowledge"
    #: 只取 `massing.shape` 之后到句末之间的双引号小写取值。
    #: 桌子/屋顶/图元各自也写 `shape`，那些**不是**设计层形状词，所以不收。
    _QUOTED = re.compile(r'"([a-z_]+)"')

    def _taught_values(self) -> dict[str, set[str]]:
        taught: dict[str, set[str]] = {}
        for path in self._KB_ROOT.rglob("*.md"):
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if "massing.shape" not in line:
                    continue
                segment = line.split("massing.shape")[-1]
                for cut in ("；", ";", "。"):
                    segment = segment.split(cut)[0]
                values = {match.lower() for match in self._QUOTED.findall(segment)}
                if values:
                    taught[f"{path.name}:{number}"] = values
        return taught

    def test_kb_taught_shape_values_are_in_the_enum(self):
        taught = self._taught_values()

        assert taught, "KB 里找不到 massing.shape 的取值示例，这条守卫已经失效"
        unknown = {
            where: sorted(values - set(_SHAPE_ENUM))
            for where, values in taught.items()
            if values - set(_SHAPE_ENUM)
        }
        assert unknown == {}, f"KB 教了枚举外的形状名（会被下游当表外标签处理）：{unknown}"
