"""验证本批活动知识片段，并按当前配置同步索引、使用 plan 工具查询。"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

from convert_references import GROUPS, KB, OUT, PLAN_TERMS, ROOT, ROWS

sys.path.insert(0, str(ROOT / "wild-server"))
if "--sync" in sys.argv:
    os.environ["RAG__AUTO_SYNC"] = "false"
from app.spec.loader import MarkdownChunker, RAGSpecLoader


def main():
    import jsonschema
    import yaml
    schema = json.loads((KB / "schema.json").read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(schema)
    chunker = MarkdownChunker(metadata_config_path=KB / "config.yaml")
    summary = {"sample_count": len(ROWS), "plan_terms": len(PLAN_TERMS), "fragments": [], "chunks": []}
    for group, (filename, _) in GROUPS.items():
        path = KB / "knowledge/components" / filename
        fragments = [json.loads(code) for code in re.findall(r"```json\s*\n(.*?)\n```", path.read_text(encoding="utf-8"), re.S)]
        expected = [row for row in ROWS if row["group"] == group]
        assert len(fragments) == len(expected)
        for fragment, row in zip(fragments, expected):
            bp = {"meta": row["blueprint"]["meta"], "geometry": {"elements": fragment["elements"], "components": fragment["components"]}, "materials": fragment["materials"]}
            validator.validate(bp)
            assert bp == row["blueprint"], row["slug"]
            summary["fragments"].append({"slug": row["slug"], "schema_valid": True, "same_as_compiled_sample": True})
        chunks = chunker.split_file(path, namespace="component_ingestion_check")
        for row in expected:
            entity_name = row["slug"].replace("-", "_")
            matching = [chunk for chunk in chunks if chunk.metadata.get("entity_name") == entity_name]
            assert matching, entity_name
            assert any("```json" in chunk.document for chunk in matching), entity_name
            for chunk in matching:
                assert chunk.metadata["entity_type"] == row["entity_type"], entity_name
                assert chunk.metadata["doc_type"] == "component"
                assert chunk.metadata["knowledge_role"] == "capability"
                assert chunk.metadata["knowledge_revision"] == "rules-v3"
            summary["chunks"].append({"slug": row["slug"], "parts": len(matching), "chars": [len(chunk.document) for chunk in matching]})
    config = yaml.safe_load((KB / "config.yaml").read_text(encoding="utf-8"))
    actual = {path.relative_to(KB).as_posix() for path in KB.rglob("*.md")}
    assert set(config["required_documents"]) == actual
    summary["manifest_documents"] = len(actual)
    (OUT / "ingestion-validation.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print("FRAGMENTS_OK", len(summary["fragments"]), flush=True)
    print("CHUNKS_OK", len(summary["chunks"]), flush=True)
    if "--sync" not in sys.argv:
        return
    from app.services.agent_service import agent_service
    from app.agent.plan.knowledge_tool import search_knowledge_impl
    loader = agent_service.spec_loader
    if not isinstance(loader, RAGSpecLoader):
        raise RuntimeError("当前是文件兜底模式，无法验证真实向量索引")
    if loader._embedding_function.__class__.__name__ == "HashEmbeddingFunction":
        raise RuntimeError("当前是离线 HashEmbedding，不能代替真实索引验收")
    lock = loader._try_process_lock()
    if lock is None:
        raise RuntimeError("已有进程正在同步索引，暂不并发写入")
    try:
        updated = loader.sync_index()
    finally:
        loader._release_process_lock(lock)
    if loader.last_sync_pending:
        raise RuntimeError(f"仍有 {loader.last_sync_pending} 个分片待同步")
    summary["sync"] = {"updated": updated, "stats": loader.last_sync_stats, "pending": loader.last_sync_pending}
    print("SYNC_OK", json.dumps(summary["sync"], ensure_ascii=False), flush=True)
    summary["queries"] = []
    for term in PLAN_TERMS:
        row = next(row for row in ROWS if term in [row["name"], *row["aliases"]])
        query = f"{term} WILD JSON 构件示例 安装 坐标"
        context = search_knowledge_impl(query, kind=term)
        hits = [{"source": hit.metadata.get("source"), "heading": hit.metadata.get("heading"), "entity_name": hit.metadata.get("entity_name"), "entity_type": hit.metadata.get("entity_type")} for hit in loader.last_results]
        expected_entity = row["slug"].replace("-", "_")
        found = any(hit["entity_name"] == expected_entity for hit in hits)
        expected_fragment = {"elements": row["blueprint"]["geometry"]["elements"], "components": row["blueprint"]["geometry"]["components"], "materials": row["blueprint"]["materials"]}
        returned_fragments = []
        for code in re.findall(r"```json\s*\n(.*?)\n```", context, re.S):
            try:
                returned_fragments.append(json.loads(code))
            except json.JSONDecodeError:
                pass
        intact = expected_fragment in returned_fragments
        summary["queries"].append({"term": term, "query": query, "expected_entity": expected_entity, "example_recalled": found, "expected_json_intact": intact, "hits": hits, "context": context})
        print("QUERY", term, "FOUND" if found and intact else "REVIEW", flush=True)
        (OUT / "ingestion-validation.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print("RECALL", sum(row["example_recalled"] for row in summary["queries"]), "/", len(PLAN_TERMS), flush=True)
    print("INTACT_JSON", sum(row["expected_json_intact"] for row in summary["queries"]), "/", len(PLAN_TERMS), flush=True)
    assert all(row["example_recalled"] and row["expected_json_intact"] for row in summary["queries"]), "仍有构件未返回完整示例"


if __name__ == "__main__":
    main()
