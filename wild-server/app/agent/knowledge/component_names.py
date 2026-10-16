"""以现有构件注册信息和知识小节元数据统一任务命名。"""
from functools import lru_cache
from pathlib import Path
import re


def _name_key(value):
    value = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", str(value).strip())
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", value)
    return re.sub(r"[-\s]+", "_", value).casefold()


@lru_cache(maxsize=1)
def _catalog_for_files(signature):
    from app.agent.generation.component.registry import COMPONENT_REGISTRY
    from app.agent.knowledge.policy import KNOWLEDGE_REVISION
    from app.spec.loader import MarkdownChunker

    names = {kind: {"kind": kind, "label": config.label, "entity_type": config.entity_type,
                    "aliases": {kind, config.label}, "references": []}
             for kind, config in COMPONENT_REGISTRY.items()}
    names["door"]["aliases"].update({"入口门", "主入口门", "entrance door", "entrance"})
    names["window"]["aliases"].update({"厨房窗", "卧室窗", "glazing"})
    for kind, label in (("building_body", "建筑主体"), ("assembly", "组合构件"),
                        ("wall", "墙体"), ("floor", "楼板"), ("beam", "梁")):
        names[kind] = {"kind": kind, "label": label, "entity_type": kind if kind in {"wall", "floor", "beam"} else "",
                       "aliases": {kind, label}, "references": []}
    names["wall"]["aliases"].add("solid")
    native_keys = {_name_key(alias): kind for kind, row in names.items() for alias in row["aliases"]}
    chunker = MarkdownChunker(metadata_config_path=signature[0][0])
    for path, _mtime, _size in signature[1:]:
        for chunk in chunker.split_file(Path(path), namespace="component_names"):
            meta = chunk.metadata
            if (meta.get("topic") != "composition" or "```json" not in chunk.document
                    or meta.get("doc_scope") != "generation" or meta.get("knowledge_role") != "capability"
                    or meta.get("knowledge_revision") != KNOWLEDGE_REVISION
                    or meta.get("status") not in {"supported", "experimental"} or meta.get("authority") == "inferred"):
                continue
            primary = str(meta.get("primary_terms") or "").split(",")
            aliases = [term.strip() for term in primary + str(meta.get("synonyms") or "").split(",") if term.strip()]
            code = str(meta.get("entity_name") or "")
            if not code:
                continue
            kind = native_keys.get(_name_key(primary[0].strip()), code)
            label = next((term for term in aliases if re.search(r"[\u4e00-\u9fff]", term)), code)
            row = names.setdefault(kind, {"kind": kind, "label": label,
                                          "entity_type": str(meta.get("entity_type") or ""), "aliases": set(), "references": []})
            row["aliases"].update([code, *aliases])
            reference = {"file": Path(path).name, "heading": str(meta.get("heading") or ""),
                         "status": meta["status"], "applies_to": str(meta.get("applies_to") or "")}
            if reference not in row["references"]:
                row["references"].append(reference)
    matches = {}
    for row in names.values():
        for alias in row["aliases"]:
            matches.setdefault(_name_key(alias), set()).add(row["kind"])
    lookup = {key: names[next(iter(kinds))] for key, kinds in matches.items() if len(kinds) == 1}
    lookup.update({_name_key(kind): row for kind, row in names.items()})
    return names, lookup


def _catalog():
    root = Path(__file__).resolve().parents[3] / "storage/knowledge_base"
    files = [root / "config.yaml", *sorted(p for p in (root / "knowledge/components").glob("*.md")
                                         if p.name != "component-catalog.md")]
    return _catalog_for_files(tuple((str(path), path.stat().st_mtime_ns, path.stat().st_size) for path in files))


def resolve_component_name(value):
    key = _name_key(value)
    row = _catalog()[1].get(key)
    return {k: row[k] for k in ("kind", "label", "entity_type")} if row else {
        "kind": key, "label": str(value).strip(), "entity_type": ""}


def component_naming_prompt():
    names = _catalog()[0]
    return "；".join(f"{kind}={row['label']}" for kind, row in sorted(names.items()))


def component_reference_prompt(kinds=None):
    names = _catalog()[0]
    selected = {resolve_component_name(k)["kind"] for k in kinds} if kinds is not None else set(names)
    lines = ["构件参考目录（非白名单）：用于统一命名和查找已有资料；目录外的新构件仍可设计和实现。",
             "已有示例是实现起点，形态、尺寸和材料由当前图纸决定；experimental 示例需要核对能力限制。"]
    for kind, row in sorted(names.items()):
        if kind not in selected:
            continue
        sources = sorted({f"{r['file']} ({r['status']})" for r in row["references"]})
        availability = "、".join(sources) if sources else ("原生协议；无专用形态示例" if row["entity_type"] else "流程条目")
        conditions = sorted({r.get("applies_to", "") for r in row["references"] if r.get("applies_to")})
        if conditions:
            availability += "；适用：" + "、".join(conditions)
        lines.append(f"- {kind}={row['label']}：{availability}")
    return "\n".join(lines)


def component_catalog_document():
    return ("---\ndoc_type: index\nknowledge_role: navigation\ndoc_scope: index\n"
            "knowledge_layer: navigation\nentity_type: index\nentity_name: component_catalog\n"
            "topic: navigation\nstatus: supported\nauthority: engine\n"
            "primary_terms: [构件参考目录]\nsynonyms: [component_catalog]\n---\n\n"
            "# 构件参考目录\n\n由 scripts/kb/update_component_catalog.py 从构件注册表及知识小节元数据生成。\n"
            "修改示例后重新生成此文件；运行时提示词读取同一批元数据，目录不占用构件 RAG 的 top_k。\n\n"
            + component_reference_prompt() + "\n")
