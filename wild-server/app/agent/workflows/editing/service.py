"""ScenePatch 模型用例，复用统一运行时和领域校验。"""
from dataclasses import dataclass, field
from collections.abc import Awaitable, Callable
from loguru import logger
from app.infrastructure.llm.invocation import invoke_llm
from app.infrastructure.llm.invocation import stream_llm
from app.infrastructure.retrieval.rag.gate import RAGRetrievalRejected
from app.agent.prompts import build_material_optimization_prompt
from app.agent.prompts import build_patch_recovery_prompt
from app.agent.prompts import build_patch_system_prompt
from app.infrastructure.retrieval.loader import SpecQuery
from app.domain.blueprint.parser import extract_patch_from_text
from app.domain.blueprint.parser import normalize_blueprint_input
from app.domain.blueprint.parser import validate_blueprint_schema
from app.domain.validation.pipeline import PipelineStepResult
from app.domain.blueprint.editing import _apply_patch_to_blueprint
from app.domain.blueprint.editing import _build_scene_summary
from app.domain.blueprint.editing import _enrich_material_tuning_operations
from app.domain.blueprint.editing import _is_material_optimization_request
from app.domain.blueprint.editing import _normalized_selection
from app.domain.blueprint.editing import _validate_material_optimization_patch
from app.domain.blueprint.editing import _validate_scene_patch_operations
from app.domain.validation.pipeline import run_validation_pipeline
from app.agent.runtime import agent_runtime

@dataclass
class PatchResult:
    """增量修改的提案、回复与校验证据。"""
    text: str
    patch: dict | None = None
    error: str | None = None
    pipeline_results: list[PipelineStepResult] = field(default_factory=list)
    structured_source: str | None = None
    structured_recovery_used: bool = False


def _extract_patch_artifact(content: str, reasoning: str) -> tuple[dict | None, str | None]:
    for source, text in (("content", content), ("reasoning", reasoning)):
        patch = extract_patch_from_text(text) if text else None
        if patch is not None:
            return patch, source
    return None, None


class PatchService:
    """使用运行时模型与知识库生成修改提案，确定性预检由领域层承担。"""

    def __init__(self, runtime):
        self.runtime = runtime

    @property
    def llm(self):
        return self.runtime.llm

    @property
    def thinking_llm(self):
        return self.runtime.thinking_llm

    @property
    def spec_loader(self):
        return self.runtime.spec_loader

    def _patch_rag_queries(self, message: str, current_blueprint: dict) -> list[SpecQuery]:
        geometry = current_blueprint.get("geometry") or {}
        types = sorted({str(item["type"]) for item in [
            *geometry.get("elements", []), *geometry.get("components", []),
        ] if isinstance(item, dict) and item.get("type")})
        primary_query = f"{message}\n当前构件类型: {', '.join(types)}"
        return [
            SpecQuery(
                f"{primary_query}\nScenePatch 修改坐标、字段与引用协议",
                {"doc_type": "blueprint_spec", "knowledge_role": "protocol"},
            ),
            SpecQuery(
                f"{primary_query}\n目标构件的当前字段与能力边界",
                {"doc_type": "component", "knowledge_role": "capability"},
            ),
            SpecQuery(
                f"{primary_query}\n修改后需要保持的宿主、组装与校验关系",
                {"doc_type": "recipe", "knowledge_role": "relation"},
            ),
        ]

    async def _recover_scene_patch(
        self,
        message: str,
        current_blueprint: dict,
        previous_reply: str,
        selection: list[str] | None = None,
        material_optimization: bool = False,
    ) -> tuple[dict | None, str, str | None]:
        """用一次非思考调用把错误格式恢复为单一 ScenePatch。"""
        recovery_prompt = build_patch_recovery_prompt(
            message,
            _build_scene_summary(current_blueprint, selection),
            previous_reply,
        )
        if material_optimization:
            recovery_prompt += build_material_optimization_prompt(selection or [])
        llm_result = await invoke_llm(
            self.llm,
            [
                {
                    "role": "system",
                    "content": "你是 ScenePatch 格式恢复器，只返回请求指定的 JSON。",
                },
                {"role": "user", "content": recovery_prompt},
            ],
        )
        content, reasoning = llm_result.content, llm_result.reasoning
        for source, text in (
            ("recovery_content", content),
            ("recovery_reasoning", reasoning),
        ):
            patch = extract_patch_from_text(text)
            if patch is not None:
                return patch, content or reasoning, source
        return None, content or reasoning, None

    async def query_patch(
        self,
        message: str,
        current_blueprint: dict,
        *,
        selection: list[str] | None = None,
        thinking_mode: bool = False,
        on_reasoning_delta: Callable[[str], Awaitable[None]] | None = None,
    ) -> PatchResult:
        """生成 ScenePatch，并在只读场景副本上完成预检与校验。"""
        selected_ids = _normalized_selection(selection)
        material_optimization = _is_material_optimization_request(message)
        if material_optimization and not selected_ids:
            return PatchResult(
                text="请先在场景中选中需要优化材质的构件，再重新发送请求。",
                error="材质优化前必须先选中一个构件",
            )
        try:
            spec_text = self.spec_loader.load_many(
                self._patch_rag_queries(message, current_blueprint),
                per_query=1,
                purpose="generation",
            )
        except RAGRetrievalRejected as exc:
            return PatchResult(text=str(exc), error=str(exc))
        user_message = (
            f"# 当前场景（只读参考）\n\n{_build_scene_summary(current_blueprint, selected_ids)}"
            f"\n\n# 用户请求\n\n{message}"
        )
        if material_optimization:
            user_message += build_material_optimization_prompt(selected_ids)
        messages = [
            {"role": "system", "content": build_patch_system_prompt(spec_text)},
            {"role": "user", "content": user_message},
        ]
        llm = self.thinking_llm if thinking_mode else self.llm
        if thinking_mode and on_reasoning_delta is not None:
            response = await stream_llm(llm, messages, on_reasoning_delta=on_reasoning_delta)
        else:
            response = await invoke_llm(llm, messages)
        reply = response.content
        patch_data, structured_source = _extract_patch_artifact(reply, response.reasoning)
        recovery_used = False
        if patch_data is None:
            logger.warning("[patch] 首次回复未提取到 ScenePatch，执行一次定向格式恢复")
            recovered_patch, recovered_text, recovery_source = await self._recover_scene_patch(
                message, current_blueprint, reply or response.reasoning,
                selected_ids, material_optimization,
            )
            recovery_used = True
            if recovered_patch is not None:
                patch_data = recovered_patch
                structured_source = recovery_source
                if recovered_text:
                    reply = recovered_text
        if patch_data is not None:
            operation_issues = _validate_scene_patch_operations(
                current_blueprint,
                patch_data,
            )
            if material_optimization:
                operation_issues.extend(_validate_material_optimization_patch(
                    patch_data,
                    selected_ids,
                ))
            if operation_issues:
                return PatchResult(
                    text=reply,
                    patch=patch_data,
                    error="ScenePatch 操作预检未通过: " + "; ".join(operation_issues),
                    structured_source=structured_source,
                    structured_recovery_used=recovery_used,
                )

            _enrich_material_tuning_operations(current_blueprint, patch_data)

            modified_bp = _apply_patch_to_blueprint(current_blueprint, patch_data)
            if modified_bp == current_blueprint:
                return PatchResult(
                    text=reply,
                    patch=patch_data,
                    error="ScenePatch 未产生任何实际修改",
                    structured_source=structured_source,
                    structured_recovery_used=recovery_used,
                )
            modified_bp = normalize_blueprint_input(modified_bp)
            pipeline_results = []
            try:
                pre_issues = validate_blueprint_schema(modified_bp)
                if pre_issues:
                    pipeline_results.append(PipelineStepResult("patch", "validate_blueprint_schema",
                        "; ".join(pre_issues), True, False))
                pipeline_results.extend(run_validation_pipeline(modified_bp))
            except Exception as exc:
                pipeline_results.append(PipelineStepResult("patch", "validate_patch_blueprint",
                    f"修改后草稿的校验执行失败：{exc}", True, False))
            return PatchResult(
                text=reply,
                patch=patch_data,
                pipeline_results=pipeline_results,
                structured_source=structured_source,
                structured_recovery_used=recovery_used,
            )

        return PatchResult(
            text=reply,
            error="模型两次回复均未返回可解析的 ScenePatch",
            structured_recovery_used=recovery_used,
        )


patch_service = PatchService(agent_runtime)
