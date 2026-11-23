"""离线视觉审核的人工意见模板及截图版本校验。"""

from __future__ import annotations

from typing import Any

from app.agent.tools.vision import STATUSES, VISIBLE_CRITERIA

#: 置信度闭集。低置信的意见只记录，不自动改（P7 第 4 条）。
CONFIDENCE_LEVELS = ("high", "medium", "low")


def human_review_template(
    render_manifest: dict[str, Any],
    design_summary: dict[str, Any],
) -> dict[str, Any]:
    """人工视觉评价的**待填模板**。

     空模板**不算**评价通过（``complete=False``）。P7 明确要求"模型没有图像输入
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

     ``human.complete`` 为假时**合并结果不算完成** —— 空模板不许冒充人工已确认。
    需要"看起来完成"的场景（报告、门禁）必须自己钉这一条。
    """

    rows = (human or {}).get("items") or (human or {}).get("template") or []
    human_done = bool(
        human
        and human.get("complete") is True
        and len(rows) == len(VISIBLE_CRITERIA)
        and {row.get("criterion") for row in rows} == set(VISIBLE_CRITERIA)
        and all(
            row.get("status") in STATUSES
            and row.get("confidence") in CONFIDENCE_LEVELS
            and (row.get("status") == "missing" or row.get("viewEvidence"))
            for row in rows
        )
    )
    return {
        "proxy": proxy,
        "human": human,
        "complete": human_done,
        "blockedBy": [] if human_done else ["human_review"],
        "note": (
            "proxy 指标可自动计算；视觉判断需人工填完 human_review 才算完成。"
            if not human_done
            else "proxy + 人工评价均已完成。"
        ),
    }


def validated_review(review: dict | None, manifest: dict) -> dict:
    """人工评价必须绑定完整、成功渲染的同一蓝图与四视图。"""
    pending = {
        "source": "human",
        "complete": False,
        "items": [],
        "reason": "等待有效的截图评价",
    }
    if (
        not isinstance(review, dict)
        or review.get("source") not in {"human", "vision"}
        or review.get("complete") is not True
    ):
        return pending
    shots = manifest.get("shots") or []
    views = {s.get("view") for s in shots if s.get("file") and s.get("bytes", 0) > 0}
    reference = review.get("render") or {}
    if (
        views != {"front", "side", "top", "perspective"}
        or manifest.get("compileErrors") != 0
        or manifest.get("reconstructErrors") != 0
        or manifest.get("unmappedMaterials") != 0
        or not manifest.get("contextSha256")
        or reference.get("contextSha256") != manifest.get("contextSha256")
        or not manifest.get("sourceDigest")
        or reference.get("sourceDigest") != manifest.get("sourceDigest")
        or not manifest.get("inputSha256")
        or reference.get("inputSha256") != manifest["inputSha256"]
        or reference.get("baselineVersion") != manifest.get("baselineVersion")
    ):
        return pending
    items = review.get("items") or review.get("template") or []
    if len(items) != len(VISIBLE_CRITERIA) or {
        i.get("criterion") for i in items
    } != set(VISIBLE_CRITERIA):
        return pending
    normalized = []
    for item in items:
        if (
            item.get("status") not in STATUSES
            or item.get("confidence") not in CONFIDENCE_LEVELS
        ):
            return pending
        evidence = item.get("viewEvidence") or []
        if item["status"] != "missing" and (
            not evidence or not set(evidence).issubset(views)
        ):
            return pending
        if item["status"] == "needs_review" and not item.get("issues"):
            return pending
        normalized.append(
            {
                **item,
                "detail": str(item.get("issues") or ""),
                "evidence": {
                    "views": evidence,
                    "suggestion": item.get("suggestion"),
                    "relatedFields": item.get("relatedFields") or [],
                },
            }
        )
    return {**review, "complete": True, "items": normalized}
