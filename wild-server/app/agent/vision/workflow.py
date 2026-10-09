"""离线视觉审核入口：只输出版本化证据与草稿，不覆盖会话或已批准设计。"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import subprocess

from app.design.contracts import DesignDocument
from app.design.compilation import compile_document
from .evaluation import human_review_template, proxy_evaluate, validated_review


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("document", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--review", type=Path, help="填写过的 human_review.json；提供后生成修订候选")
    parser.add_argument("--chromium", help="Chromium 可执行文件；也可设置 CHROMIUM_PATH")
    args = parser.parse_args()
    document = DesignDocument.model_validate(json.loads(args.document.read_text(encoding="utf-8-sig")))
    if document.decisions.kind != "architecture":
        parser.error("当前视觉修订仅支持建筑设计")
    # 一个命令一次运行，绝不覆盖上一轮截图、意见与候选。
    args.output.mkdir(parents=True, exist_ok=True)
    import tempfile
    run_dir = Path(tempfile.mkdtemp(prefix="review-", dir=args.output.resolve()))
    script = Path(__file__).resolve().parents[4] / "wild-web/scripts/render-baseline.mjs"
    compiled = compile_document(document)
    write_json(run_dir / "document.json", document.model_dump(mode="json"))
    write_json(run_dir / "compile_report.json", [d.to_dict() for d in compiled.defects])
    renders: dict[str, dict] = {}

    def render(blueprint: dict) -> dict:
        content = json.dumps(blueprint, ensure_ascii=False, indent=2)
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        if digest in renders:
            return renders[digest]
        target = run_dir / digest[:16]
        target.mkdir()
        blueprint_path = target / "blueprint.json"
        blueprint_path.write_text(content, encoding="utf-8", newline="\n")
        command = ["node", str(script), str(blueprint_path), str(target)]
        if args.chromium:
            command.append(args.chromium)
        result = subprocess.run(command, cwd=script.parent.parent, capture_output=True,
                                text=True, encoding="utf-8", errors="replace", timeout=90)
        (target / "render.log").write_text(result.stdout + result.stderr, encoding="utf-8")
        if result.returncode:
            raise RuntimeError(f"真实渲染失败，见 {target / 'render.log'}")
        manifest = json.loads((target / "render_manifest.json").read_text(encoding="utf-8"))
        renders[digest] = manifest
        write_json(target / "human_review.json", human_review_template(manifest, {
            "sourceRequest": document.requirements.source_request,
            "designId": document.design_id, "blueprintFile": str(blueprint_path),
        }))
        return manifest

    if not isinstance(compiled.blueprint, dict):
        raise RuntimeError(f"编译未产出蓝图，见 {run_dir / 'compile_report.json'}")
    manifest = render(compiled.blueprint)
    write_json(run_dir / "proxy.json", proxy_evaluate(compiled.blueprint, document.model_dump(mode="json")))
    if args.review:
        from .revision import revise_by_visibility
        from app.agent.validation.candidate import evaluate_candidate
        supplied = json.loads(args.review.read_text(encoding="utf-8-sig"))
        baseline = validated_review(supplied, manifest)
        if not baseline.get("complete"):
            raise ValueError("人工评价未完成或与当前蓝图/渲染版本不匹配；请填写本轮生成的模板")

        def validate(blueprint):
            return len(evaluate_candidate(blueprint, source="visual_revision")["errors"])

        outcome = asyncio.run(revise_by_visibility(
            document=document.model_dump(mode="json"),
            user_message=document.requirements.source_request,
            render=render, validate=validate,
            review=lambda _bp, current_manifest: validated_review(supplied, current_manifest),
            max_rounds=1,
        ))
        write_json(run_dir / "revision.json", {"diagnostics": outcome.diag, "ledger": outcome.ledger.to_dict()})
        # 新候选尚未人工看图，因此不会自动采纳。单独导出，下一轮继续审核。
        for entry in outcome.ledger.entries:
            if entry["label"] == "baseline":
                continue
            write_json(run_dir / f"{entry['label']}.document.json", entry["document"])
            write_json(run_dir / f"{entry['label']}.blueprint.json", entry["blueprint"])
    print(str(run_dir))


if __name__ == "__main__":
    main()
