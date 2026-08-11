"""PBR 资产最短链路的独立 LangGraph 编排。"""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, StateGraph

from app.services.asset_storage import AssetStorageError, LocalAssetStorage, asset_storage


class AssetWorkflowState(TypedDict, total=False):
    request: dict[str, Any]
    maps: dict[str, dict[str, Any]]
    storage: LocalAssetStorage
    intent: dict[str, Any]
    prepared: dict[str, Any]
    asset: dict[str, Any]
    patch: dict[str, Any]
    error: str
    trace: Annotated[list[dict[str, Any]], operator.add]


def extract_material_intent(state: AssetWorkflowState) -> dict[str, Any]:
    request = state["request"]
    try:
        roughness = float(request.get("roughness", 0.8))
        metallic = float(request.get("metallic", 0.0))
        normal_scale = float(request.get("normalScale", 1.0))
        uv_scale = [float(value) for value in request.get("uvScale", [1, 1])]
        real_world_size = [float(value) for value in request.get("realWorldSizeMeters", [1, 1])]
        if not 0 <= roughness <= 1 or not 0 <= metallic <= 1:
            raise AssetStorageError("roughness/metallic 必须在 0–1 范围")
        if not 0 <= normal_scale <= 4:
            raise AssetStorageError("normalScale 必须在 0–4 范围")
        if len(uv_scale) != 2 or any(value <= 0 for value in uv_scale):
            raise AssetStorageError("uvScale 必须是两个正数")
        if len(real_world_size) != 2 or any(value <= 0 for value in real_world_size):
            raise AssetStorageError("realWorldSizeMeters 必须是两个正数")
        material_name = str(request.get("materialName") or request.get("name") or "pbr_material").strip()
        if not material_name:
            raise AssetStorageError("materialName 不能为空")
        intent = {
            "name": str(request.get("name", "PBR Material")),
            "materialName": material_name,
            "license": str(request.get("license", "User supplied")),
            "sourceType": str(request.get("sourceType", "local_upload")),
            "sourceUri": request.get("sourceUri"),
            "roughness": roughness,
            "metallic": metallic,
            "normalScale": normal_scale,
            "uvScale": uv_scale,
            "realWorldSizeMeters": real_world_size,
            "materialClass": str(request.get("materialClass", "other")),
            "tags": list(request.get("tags") or []),
            "recommendedRoles": list(request.get("recommendedRoles") or []),
            "baseRevision": int(request.get("baseRevision", 1)),
        }
        return {
            "intent": intent,
            "trace": [{"node": "extract_material_intent", "status": "done"}],
        }
    except (TypeError, ValueError, AssetStorageError) as exc:
        return {
            "error": str(exc),
            "trace": [{"node": "extract_material_intent", "status": "error", "detail": str(exc)}],
        }


def validate_asset(state: AssetWorkflowState) -> dict[str, Any]:
    if state.get("error"):
        return {}
    intent = state["intent"]
    storage = state.get("storage", asset_storage)
    try:
        prepared = storage.prepare_pbr(
            state["maps"],
            name=intent["name"],
            license_name=intent["license"],
            source_type=intent["sourceType"],
            source_uri=intent.get("sourceUri"),
            material_class=intent["materialClass"],
            tags=intent["tags"],
            recommended_roles=intent["recommendedRoles"],
            real_world_size_meters=intent["realWorldSizeMeters"],
            roughness=intent["roughness"],
            metallic=intent["metallic"],
            normal_scale=intent["normalScale"],
            uv_scale=intent["uvScale"],
        )
        return {
            "prepared": prepared,
            "trace": [{
                "node": "validate_asset",
                "status": "done",
                "detail": f"{len(prepared['maps'])} 个纹理通道",
            }],
        }
    except AssetStorageError as exc:
        return {
            "error": str(exc),
            "trace": [{"node": "validate_asset", "status": "error", "detail": str(exc)}],
        }


def register_asset(state: AssetWorkflowState) -> dict[str, Any]:
    storage = state.get("storage", asset_storage)
    try:
        asset = storage.register_prepared(state["prepared"])
        return {
            "asset": asset,
            "trace": [{"node": "register_asset", "status": "done", "detail": asset["assetId"]}],
        }
    except (AssetStorageError, OSError, ValueError) as exc:
        return {
            "error": str(exc),
            "trace": [{"node": "register_asset", "status": "error", "detail": str(exc)}],
        }


def propose_wild_patch(state: AssetWorkflowState) -> dict[str, Any]:
    intent = state["intent"]
    asset = state["asset"]
    patch = {
        "type": "scene_patch",
        "patch_id": f"asset_{asset['assetId']}",
        "base_revision": intent["baseRevision"],
        "source": "user",
        "mode": "apply",
        "requires_confirmation": False,
        "summary": f"入库并注册 PBR 材质 {intent['materialName']}",
        "operations": [
            {"op": "upsert_asset", "asset_id": asset["assetId"], "asset": asset},
            {
                "op": "upsert_material",
                "name": intent["materialName"],
                "material": {
                    "baseColor": [1, 1, 1],
                    "roughness": intent["roughness"],
                    "metallic": intent["metallic"],
                    "albedo": 1,
                    "lightingCondition": "D65_noon",
                    "textureSet": asset["assetId"],
                    "normalScale": intent["normalScale"],
                    "uvScale": intent["uvScale"],
                },
            },
        ],
    }
    return {
        "patch": patch,
        "trace": [{"node": "propose_wild_patch", "status": "done", "detail": "2 个操作"}],
    }


def _next_after_validation(state: AssetWorkflowState) -> str:
    return "end" if state.get("error") else "register_asset"


def _next_after_registration(state: AssetWorkflowState) -> str:
    return "end" if state.get("error") else "propose_wild_patch"


def _build_asset_graph():
    graph = StateGraph(AssetWorkflowState)
    graph.add_node("extract_material_intent", extract_material_intent)
    graph.add_node("validate_asset", validate_asset)
    graph.add_node("register_asset", register_asset)
    graph.add_node("propose_wild_patch", propose_wild_patch)
    graph.set_entry_point("extract_material_intent")
    graph.add_edge("extract_material_intent", "validate_asset")
    graph.add_conditional_edges(
        "validate_asset",
        _next_after_validation,
        {"register_asset": "register_asset", "end": END},
    )
    graph.add_conditional_edges(
        "register_asset",
        _next_after_registration,
        {"propose_wild_patch": "propose_wild_patch", "end": END},
    )
    graph.add_edge("propose_wild_patch", END)
    return graph.compile()


asset_workflow = _build_asset_graph()


async def run_asset_workflow(
    request: dict[str, Any],
    maps: dict[str, dict[str, Any]],
    storage: LocalAssetStorage | None = None,
) -> AssetWorkflowState:
    return await asset_workflow.ainvoke({
        "request": request,
        "maps": maps,
        "storage": storage or asset_storage,
        "trace": [],
    })
