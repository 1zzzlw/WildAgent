"""P7-B：视觉评价 —— 只看**可见**问题，且不假装模型能看图。

P7 第 1 条："模型没有图像输入能力时先使用人工评价，不假装做视觉判断"。
本仓库的 LLM 调用链（``invoke_llm`` → LangChain ``ainvoke``）只走纯文本消息，
**没有图像通道** —— 所以这里明确分两层：

``proxy_metrics``（程序可判，本模块负责）
    从蓝图几何/材质算出来的**可见问题代理指标**：入口可识别度、立面开窗节奏、
    体量层次、材质协调度。每一项都必须能从实体字段算出来，不许"看起来如何"。

``human_review``（人工，本模块只产出**待填模板**）
    真正的视觉判断（构图气质、材质质感、整体观感）留给人。模板里带截图路径与
    设计摘要，人填完才算数 —— 空模板不算评价通过。

🔴 **不做的推断**（P7 第 3 条）：不凭图猜精确尺寸、不猜不可见关系、不猜室内。
    那些以几何校验与履约为准，本模块的输出不参与阻断。

🔴 **事实源纪律**（本模块踩过的坑，见 ``PITFALLS.md``）：
  - 字段名一律现查 ``storage/knowledge_base/schema.json``，不凭印象写。
    本模块初版就读错了两处：``textureSet`` 根本不存在（真名是 ``textures.*``），
    体量不在蓝图里（在**设计文档** ``decisions.volumes``）。
  - 材质引用**不只在 ``material``**：门是 ``frameMaterial``/``leafMaterial``，
    窗是 ``frameMaterial``/``glassMaterial``。只读 ``material`` 会整扇门窗的材质被漏掉。
"""

from __future__ import annotations

from typing import Any

#: 评价项闭集。P7 第 2 条限定为"可见问题"，这张表就是那个限定 ——
#: 新增评价项要显式改这里，别让"能算什么就评什么"。
VISIBLE_CRITERIA = (
    "massing_hierarchy",   # 体量层次
    "entrance_legibility",  # 入口识别
    "facade_rhythm",       # 立面节奏
    "material_harmony",    # 材质协调
)

#: 置信度闭集。低置信的意见只记录，不自动改（P7 第 4 条）。
CONFIDENCE_LEVELS = ("high", "medium", "low")

#: 状态闭集。``missing`` 与 ``needs_review`` **不同义**：
#: ``missing`` = 数据不足以判断（该记的没记，如设计层没有体量信息）；
#: ``needs_review`` = 算出来了且确实有问题。前者别当成问题，后者才进修订队列。
STATUSES = ("ok", "needs_review", "missing")

#: 材质引用字段全集（现查 schema ``$defs`` 得出，见模块 docstring）。
#: 漏一个字段 = 那一类构件的材质在统计里凭空消失。
_MATERIAL_REF_FIELDS = (
    "material", "materialOverride",
    "frameMaterial", "leafMaterial", "glassMaterial",
    "railingMaterial", "infillMaterial", "supportMaterial",
    "capMaterial", "baseMaterial", "shadeMaterial",
)

#: 贴图绑定字段（``materialDef.properties.textures`` 的子字段，schema 真名）。
#: 🔴 不是 ``textureSet`` —— 那个字段不存在，初版写它导致贴图数恒为 0。
_TEXTURE_SLOTS = ("baseColor", "normal", "roughness", "metalness", "ambientOcclusion")

#: 单面墙内开口**间距**的相对离散度阈值。超过即认为这面墙节奏不均。
#: 实测基线（14×10 两层）：长边间距 4.7/4.7、短边 3.4/3.3 ⇒ 相对差0.03 以内，ok。
#: 反例（开口挤在一端）：间距 0.6/8.1 ⇒ 相对差 0.86 ⇒ needs_review。
_RHYTHM_GAP_RATIO = 0.45

#: 窗间距**绝对下限**（米）。低于它即判不均。
#: 🔴 这条不是冗余：只有 2 扇窗时间距列表长度为 1，``max - min == 0``，
#:    相对差恒为 0 —— "两扇窗挤在 0.2m 内"这种明显问题**判不出来**。
#:    实测真实基线就踩到：``wall_front_1`` 只有 2 扇窗，把它们挪到 0.2m 间距，
#:    相对差仍是 0.00，判据报 ok。加这条绝对下限才盖住这个盲区。
#: 取 0.6m：低于这个距离两扇窗在立面上已经贴成一片，看得出是"一扇"。
_RHYTHM_MIN_GAP = 0.6

#: 一面墙至少要有这么多个开口才谈得上"节奏"（1 个开口没有节奏可言）。
_MIN_RHYTHM_OPENINGS = 2


def _elements(blueprint: dict[str, Any], kind: str | None = None) -> list[dict[str, Any]]:
    geometry = blueprint.get("geometry") or {}
    items = [item for item in geometry.get("elements") or [] if isinstance(item, dict)]
    return [item for item in items if kind is None or item.get("type") == kind]


def _components(blueprint: dict[str, Any], kind: str | None = None) -> list[dict[str, Any]]:
    geometry = blueprint.get("geometry") or {}
    items = [item for item in geometry.get("components") or [] if isinstance(item, dict)]
    return [item for item in items if kind is None or item.get("type") == kind]


def _wall_axis(wall: dict[str, Any]) -> tuple[str, float, float, float] | None:
    """墙的轴线：返回 ``(轴, 常量坐标, 起点, 终点)``。

    轴为 ``"x"`` 表示墙沿 z 延伸（法向朝 x），常量坐标是它的 x。
    判定内墙要用："四面外墙之外的墙"就是内墙。
    """

    frm, to = wall.get("from"), wall.get("to")
    try:
        x0, z0 = float(frm[0]), float(frm[2])
        x1, z1 = float(to[0]), float(to[2])
    except (TypeError, ValueError, IndexError):
        return None
    if abs(x0 - x1) <= 1e-6:
        return ("x", x0, min(z0, z1), max(z0, z1))
    if abs(z0 - z1) <= 1e-6:
        return ("z", z0, min(x0, x1), max(x0, x1))
    return None  # 斜墙：不参与内墙判定（保守，宁可算外墙也不误判）


def _exterior_wall_ids(blueprint: dict[str, Any]) -> set[str]:
    """外墙 id 集合。

    🔴 判据用**自身平面 footprint 的极值**，不是"离原点最近/最远"——
    建筑可以建在任意坐标上，"离原点远的那面"和"临街的那面"没有任何关系。

    一面墙是外墙，当且仅当它所在轴的常量坐标落在 footprint 极值上
    （容差 0.05m，防浮点与墙厚偏移）。斜墙判不了 ⇒ 不算外墙（宁可漏算，
    也不把内墙当外墙混进节奏统计）。
    """

    walls = _elements(blueprint, "wall")
    axes: dict[str, list[tuple[float, float, float]]] = {}
    for wall in walls:
        axis = _wall_axis(wall)
        if axis is None:
            continue
        name, const, lo, hi = axis
        axes.setdefault(name, []).append((const, lo, hi))
    ids: set[str] = set()
    for wall in walls:
        axis = _wall_axis(wall)
        if axis is None:
            continue
        name, const, _lo, _hi = axis
        same = axes.get(name) or []
        consts = [c for c, _a, _b in same]
        if not consts:
            continue
        low, high = min(consts), max(consts)
        if abs(const - low) <= 0.05 or abs(const - high) <= 0.05:
            ids.add(str(wall.get("id")))
    return ids


def entrance_legibility(blueprint: dict[str, Any]) -> dict[str, Any]:
    """入口识别：门的位置与"是否唯一/是否被雨棚强化"。

    判据全部来自实体字段：门落在哪面墙、有几樘、正上方有没有雨棚。
    🔴 不用"截图里看不看得见"当判据 —— 那需要人看（见 ``human_review``）。
    🔴 "主立面"按**门所在墙是不是外墙**判定，不按 ``wall_front`` 前缀 ——
       墙 id 的命名是编译器内部约定，不是契约。
    """

    doors = _components(blueprint, "door")
    if not doors:
        return {
            "criterion": "entrance_legibility",
            "status": "missing",
            "detail": "没有任何门：入口未表达",
            "confidence": "high",
            "evidence": {"doorCount": 0},
        }
    exterior = _exterior_wall_ids(blueprint)
    canopies = _components(blueprint, "canopy")
    front_doors = [
        door for door in doors
        if not exterior or str(door.get("parentWall") or "") in exterior
    ]
    canopy_walls = {str(c.get("parentWall") or "") for c in canopies}
    has_canopy = any(str(d.get("parentWall") or "") in canopy_walls for d in front_doors)

    notes: list[str] = []
    if len(doors) > 1:
        notes.append(f"共 {len(doors)} 樘门，入口唯一性需要人工确认")
    if not front_doors:
        notes.append("所有门都在内墙上：入口未落在临街面")
    # 🔴 雨棚是**正面**信息，只进 detail/evidence，不参与 needs_review 判定 ——
    #    装了雨棚反而变成"待复查"是判据写反了。
    positives: list[str] = []
    if front_doors:
        positives.append(f"临街面 {len(front_doors)} 樘门")
    if has_canopy:
        positives.append("入口上方有雨棚")
    if len(front_doors) == 1 and len(doors) == 1:
        positives.append("唯一入口")
    return {
        "criterion": "entrance_legibility",
        "status": "needs_review" if notes else "ok",
        "detail": "；".join(notes + positives),
        "confidence": "high" if len(front_doors) == len(doors) else "medium",
        "evidence": {
            "doorCount": len(doors),
            "exteriorDoorCount": len(front_doors),
            "entranceCanopy": has_canopy,
        },
    }


def facade_rhythm(blueprint: dict[str, Any]) -> dict[str, Any]:
    """立面节奏：同一面墙上开口的**间距**是否均匀。

    🔴 判据是"同一面墙内的间距离散度"，不是"跨墙密度比"：
       - 跨墙密度比会把"长墙 3 洞 / 短墙 3 洞"这种完全正常的房子判成不均
         （14m 与 10m 的墙同样 3 个洞，密度必然 0.21 vs 0.30，差0.086）；
       - 而真正的节奏问题 —— 开口全挤在一端 —— 恰恰是**同一面墙内**的事，
         跨墙比值根本看不见。
       实测基线：长边间距 4.7/4.7、短边 3.4/3.3 ⇒ 均匀；反面：0.6/8.1 ⇒ 不均。

    🔴 **门不参与窗的节奏统计**：门宽（1.0m）与窗宽（1.5m）不同，中心间距
       天然对不齐，把门算进去会让"门+两窗"的正常立面被判成间距 0.75/4.0
       （相对差 0.81）—— 实测这就是初版夹具一直红的真实原因。
       门的位置另由``entrance_legibility`` 管，两项各管一件事，不重复计。
       没有窗的墙（只挂门）不参与节奏统计。

    🔴 **两条判据取或**：相对离散度（看疏密不均）+ 绝对下限
       （:data:`_RHYTHM_MIN_GAP`，看"贴成一片"）。只有 2 扇窗时相对差恒为 0，
       光靠相对差判不出"两扇窗挤在 0.2m 内"—— 这是真实基线实测出来的盲区。

    🔴 只统计**外墙**：内墙 0 开口是正常的（有门通向房间），混进来没有意义。
    """

    walls = [w for w in _elements(blueprint, "wall")]
    if not walls:
        return {"criterion": "facade_rhythm", "status": "missing",
                "detail": "没有墙，无法判断立面节奏", "confidence": "high"}
    exterior = _exterior_wall_ids(blueprint)
    candidates = [w for w in walls if str(w.get("id")) in exterior]
    if not candidates:
        # 没有轴向墙（全是斜墙）：退化为全部墙，但如实说明口径变了。
        candidates = walls
        scope = "全部墙（没有可判定的轴向外墙，口径已退化）"
    else:
        scope = f"{len(candidates)} 面外墙"

    # 按墙收集**窗/阳台**的沿墙中心。门窗 from[0] 是沿墙距离（蓝图坐标语义）。
    # 🔴 只收 window/balcony：门宽与窗宽不同，混算必然对不齐（见 docstring）。
    offsets: dict[str, list[float]] = {}
    for item in _components(blueprint):
        wall_id = str(item.get("parentWall") or "")
        if item.get("type") not in {"window", "balcony"} or not wall_id:
            continue
        try:
            start = float((item.get("from") or [])[0])
            width = float(item.get("width") or 0.0)
        except (TypeError, ValueError, IndexError):
            continue
        offsets.setdefault(wall_id, []).append(start + width / 2.0)

    gaps_by_wall: dict[str, list[float]] = {}
    for wall in candidates:
        wall_id = str(wall.get("id"))
        centers = sorted(offsets.get(wall_id) or [])
        if len(centers) < _MIN_RHYTHM_OPENINGS:
            continue
        gaps_by_wall[wall_id] = [
            round(centers[i + 1] - centers[i], 3) for i in range(len(centers) - 1)
        ]
    if not gaps_by_wall:
        return {
            "criterion": "facade_rhythm",
            "status": "missing",
            "detail": (
                f"{scope}中没有任何一面外墙有 ≥{_MIN_RHYTHM_OPENINGS} 扇窗/阳台，"
                f"无从谈节奏（门不计入）"
            ),
            "confidence": "medium",
            "evidence": {"scope": scope, "walls": len(candidates)},
        }

    ratios: dict[str, float] = {}
    offenders: list[str] = []
    for wall_id, gaps in gaps_by_wall.items():
        low, high = min(gaps), max(gaps)
        # 🔴 分母不能是 0：两扇窗完全重合时 low=0，用 max(low, 0.1) 兜底，
        #    否则 ZeroDivisionError 把整个评价打断。
        ratio = (high - low) / max(low, 0.1)
        ratios[wall_id] = round(ratio, 4)
        # 🔴 两条判据取或：相对离散度看"疏密不均"，绝对下限看"贴成一片"。
        #    只有 2 扇窗时相对差恒为 0（只有一个间距），只有绝对下限能判出来。
        if ratio > _RHYTHM_GAP_RATIO or low < _RHYTHM_MIN_GAP:
            offenders.append(wall_id)
    detail = "；".join(
        f"{wall_id} 窗距 {gaps_by_wall[wall_id]}（相对差 {ratios[wall_id]:.2f}"
        + (f"、最小间距 {min(gaps_by_wall[wall_id]):.2f}m 过窄" if min(gaps_by_wall[wall_id]) < _RHYTHM_MIN_GAP else "")
        + "）"
        for wall_id in sorted(ratios)
    )
    return {
        "criterion": "facade_rhythm",
        "status": "needs_review" if offenders else "ok",
        "detail": (
            f"{scope}：{detail}；{len(offenders)} 面墙开窗间距不均"
            if offenders else f"{scope}：{detail}；通过当前间距规则，视觉节奏待截图评价"
        ),
        "confidence": "high",
        "evidence": {
            "gaps": gaps_by_wall,
            "gapRatios": ratios,
            "limit": _RHYTHM_GAP_RATIO,
            "minGap": _RHYTHM_MIN_GAP,
            "offenders": sorted(offenders),
            "scope": scope,
            "note": "只统计 window/balcony，门由entrance_legibility 单独管",
        },
    }


def massing_hierarchy(
    blueprint: dict[str, Any],
    design_document: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """体量层次：屋面块数与体量数是否匹配。

    一块屋顶盖住多个体量 ⇒ 体量层次在**渲染上**就消失了（内院也被盖住）。

    🔴 **体量数的唯一事实源是设计文档** ``decisions.volumes``，不在蓝图里 ——
       初版读 ``blueprint["volumes"]``，永远读不到 ⇒ 这一项恒为 ``missing``。
       没有设计文档时如实说"数据不足"，不拿别的东西凑数。
    """

    roofs = _elements(blueprint, "roof")
    volumes = None
    if isinstance(design_document, dict):
        decisions = design_document.get("decisions")
        if isinstance(decisions, dict):
            volumes = decisions.get("volumes")
    if not isinstance(volumes, list) or not volumes:
        return {
            "criterion": "massing_hierarchy",
            "status": "missing",
            "detail": (
                f"没有设计文档的 decisions.volumes，体量数不可知；"
                f"蓝图里有 {len(roofs)} 块屋面可作参考"
            ),
            "confidence": "medium",
            "evidence": {"roofs": len(roofs)},
        }
    volume_count = len(volumes)
    roof_count = len(roofs)
    single_volume = volume_count == 1
    ok = single_volume or roof_count >= volume_count
    return {
        "criterion": "massing_hierarchy",
        "status": "ok" if ok else "needs_review",
        "detail": (
            f"{volume_count} 个体量 / {roof_count} 块屋面"
            + ("" if ok else "：屋面数少于体量数，体量层次在渲染上会消失")
        ),
        "confidence": "high",
        "evidence": {"volumes": volume_count, "roofs": roof_count},
    }


def material_harmony(blueprint: dict[str, Any]) -> dict[str, Any]:
    """材质协调：材质引用种类数与分配是否集中。

    同一种材质铺满全部构件 ⇒ 没有层次；种类过多 ⇒ 拼贴感。两者都记为需人工看。

    🔴 统计**所有材质引用位**（``_MATERIAL_REF_FIELDS``），不是只读 ``material``：
       门是 ``frameMaterial``/``leafMaterial``、窗是 ``frameMaterial``/``glassMaterial``，
       只读 ``material`` 会把整扇门窗的材质算没了 —— 实测基线就是这样把
       wood/metal/glass 三个材质漏成 3 种的。
    """

    materials = blueprint.get("materials") or {}
    refs: set[str] = set()
    for item in _elements(blueprint) + _components(blueprint):
        for field in _MATERIAL_REF_FIELDS:
            value = item.get(field)
            if isinstance(value, str) and value:
                refs.add(value)
            elif isinstance(value, list):  # instanceRef.materialOverride 可为数组
                refs.update(str(v) for v in value if v)
    textured = sorted(
        name for name, params in (materials.items() if isinstance(materials, dict) else [])
        if isinstance(params, dict) and isinstance(params.get("textures"), dict)
        and any(params["textures"].get(slot) for slot in _TEXTURE_SLOTS)
    )
    if not refs:
        return {"criterion": "material_harmony", "status": "missing",
                "detail": "没有任何材质引用", "confidence": "high",
                "evidence": {"materialCount": 0, "textured": []}}
    notes: list[str] = []
    if len(refs) <= 2:
        notes.append(f"只用了 {len(refs)} 种材质，层次可能过弱")
    if len(refs) > 8:
        notes.append(f"用了 {len(refs)} 种材质，易显拼贴")
    return {
        "criterion": "material_harmony",
        "status": "needs_review" if notes else "ok",
        "detail": "；".join(notes) or (
            f"{len(refs)} 种材质、{len(textured)} 种带贴图；仅为数量统计，协调程度待截图评价"
        ),
        "confidence": "medium",
        "evidence": {
            "materialCount": len(refs),
            "materials": sorted(refs),
            "textured": textured,
        },
    }


_PROXY_FUNCTIONS = {
    "entrance_legibility": entrance_legibility,
    "facade_rhythm": facade_rhythm,
    "massing_hierarchy": massing_hierarchy,
    "material_harmony": material_harmony,
}


def proxy_evaluate(
    blueprint: dict[str, Any],
    design_document: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """程序可判的可见问题代理指标。全部来自实体字段，不含"看起来如何"。

    ``design_document`` 只有 ``massing_hierarchy`` 用得到（体量数的唯一事实源），
    缺它时那一项是 ``missing``，其余三项照常。
    """

    items = [
        massing_hierarchy(blueprint, design_document),
        entrance_legibility(blueprint),
        facade_rhythm(blueprint),
        material_harmony(blueprint),
    ]
    return {
        "source": "proxy",
        "complete": False,
        "okMeaning": "仅当前实体测量规则通过，未进行审美或截图验收",
        "note": (
            "从蓝图实体字段计算的可量化指标，不等于视觉判断；"
            "构图气质、材质质感等仍需人工看图（见 human_review）。"
        ),
        "criteria": list(VISIBLE_CRITERIA),
        "statuses": list(STATUSES),
        "items": items,
        "needsReview": [i["criterion"] for i in items if i["status"] == "needs_review"],
        "missing": [i["criterion"] for i in items if i["status"] == "missing"],
        "ok": [i["criterion"] for i in items if i["status"] == "ok"],
    }


def human_review_template(
    render_manifest: dict[str, Any],
    design_summary: dict[str, Any],
) -> dict[str, Any]:
    """人工视觉评价的**待填模板**。

    🔴 空模板**不算**评价通过（``complete=False``）。P7 明确要求"模型没有图像输入
    能力时先使用人工评价，不假装做视觉判断"—— 所以这里只准备材料，不产出结论。
    """

    shots = render_manifest.get("shots") or []
    return {
        "source": "human",
        "complete": False,
        "reason": "当前 LLM 调用链只支持纯文本，没有图像输入通道，视觉判断必须由人做。",
        "criteria": list(VISIBLE_CRITERIA),
        "statuses": list(STATUSES),
        "confidenceLevels": list(CONFIDENCE_LEVELS),
        "render": {
            "baselineVersion": render_manifest.get("baselineVersion"),
            "inputSha256": render_manifest.get("inputSha256"),
            "sourceDigest": render_manifest.get("sourceDigest"),
            "contextSha256": render_manifest.get("contextSha256"),
            "views": [shot.get("view") for shot in shots],
            "files": [shot.get("file") for shot in shots],
            "glRenderer": render_manifest.get("glRenderer"),
            "unmappedMaterials": render_manifest.get("unmappedMaterials"),
        },
        "designSummary": design_summary,
        "template": [
            {
                "criterion": criterion,
                "status": "",
                "issues": [],
                "viewEvidence": [],
                "relatedFields": [],
                "confidence": "",
                "suggestion": "",
            }
            for criterion in VISIBLE_CRITERIA
        ],
        "instruction": (
            "逐项填写：status（ok|needs_review|missing）/ issues（看到的可见问题）/ "
            "viewEvidence（哪个视角能看出来）/ "
            "relatedFields（关联的设计字段或实体 id，找不到映射就留空并只记录）/ "
            "confidence（high|medium|low）/ suggestion。"
            "不要凭截图推断精确尺寸或不可见关系 —— 那些以几何校验为准。"
        ),
    }


def merge_evaluation(
    proxy: dict[str, Any],
    human: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """合并两层评价。

    🔴 ``human.complete`` 为假时**合并结果不算完成** —— 空模板不许冒充人工已确认。
    需要"看起来完成"的场景（报告、门禁）必须自己钉这一条。
    """

    rows = (human or {}).get("items") or (human or {}).get("template") or []
    human_done = bool(human and human.get("complete") is True
                      and len(rows) == len(VISIBLE_CRITERIA)
                      and {row.get("criterion") for row in rows} == set(VISIBLE_CRITERIA)
                      and all(row.get("status") in STATUSES and row.get("confidence") in CONFIDENCE_LEVELS
                              and (row.get("status") == "missing" or row.get("viewEvidence")) for row in rows))
    return {
        "proxy": proxy,
        "human": human,
        "complete": human_done,
        "blockedBy": [] if human_done else ["human_review"],
        "note": (
            "proxy 指标可自动计算；视觉判断需人工填完 human_review 才算完成。"
            if not human_done else "proxy + 人工评价均已完成。"
        ),
    }


def validated_review(review: dict | None, manifest: dict) -> dict:
    """人工评价必须绑定完整、成功渲染的同一蓝图与四视图。"""
    pending = {"source": "human", "complete": False, "items": [], "reason": "等待有效的截图评价"}
    if not isinstance(review, dict) or review.get("source") not in {"human", "vision"} or review.get("complete") is not True:
        return pending
    shots = manifest.get("shots") or []
    views = {s.get("view") for s in shots if s.get("file") and s.get("bytes", 0) > 0}
    reference = review.get("render") or {}
    if (views != {"front", "side", "top", "perspective"}
            or manifest.get("compileErrors") != 0 or manifest.get("reconstructErrors") != 0
            or manifest.get("unmappedMaterials") != 0
            or not manifest.get("contextSha256")
            or reference.get("contextSha256") != manifest.get("contextSha256")
            or not manifest.get("sourceDigest")
            or reference.get("sourceDigest") != manifest.get("sourceDigest")
            or not manifest.get("inputSha256")
            or reference.get("inputSha256") != manifest["inputSha256"]
            or reference.get("baselineVersion") != manifest.get("baselineVersion")):
        return pending
    items = review.get("items") or review.get("template") or []
    if len(items) != len(VISIBLE_CRITERIA) or {i.get("criterion") for i in items} != set(VISIBLE_CRITERIA):
        return pending
    normalized = []
    for item in items:
        if item.get("status") not in STATUSES or item.get("confidence") not in CONFIDENCE_LEVELS:
            return pending
        evidence = item.get("viewEvidence") or []
        if item["status"] != "missing" and (not evidence or not set(evidence).issubset(views)):
            return pending
        if item["status"] == "needs_review" and not item.get("issues"):
            return pending
        normalized.append({**item, "detail": str(item.get("issues") or ""),
                           "evidence": {"views": evidence, "suggestion": item.get("suggestion"),
                                        "relatedFields": item.get("relatedFields") or []}})
    return {**review, "complete": True, "items": normalized}
