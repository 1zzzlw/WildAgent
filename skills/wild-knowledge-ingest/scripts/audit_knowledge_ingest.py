from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


BASE_EXCLUDE = "BLUEPRINT-SPEC-MINIMAL.md"

CATEGORY_KEYWORDS = {
    "building_types/catalog": [
        "别墅", "凉亭", "亭子", "小屋", "木屋", "庭院", "院落", "塔楼", "默认", "最少可行",
        "villa", "pavilion", "cabin", "courtyard", "tower",
    ],
    "building_types/residential": [
        "住宅", "宿舍", "酒店", "宾馆", "公寓", "四合院", "house", "hotel",
    ],
    "building_types/public": [
        "学校", "教育", "办公", "写字楼", "博物馆", "剧院", "商业", "体育", "医院", "医疗", "交通", "航站楼", "车站", "图书馆",
    ],
    "building_types/industrial": [
        "厂房", "工业", "仓储", "仓库", "车间", "factory", "warehouse",
    ],
    "building_types/agricultural": [
        "农业", "温室", "养殖", "粮仓", "农机", "greenhouse",
    ],
    "components": [
        "构件", "墙", "门", "窗", "屋顶", "屋檐", "檐口", "柱", "梁", "楼板", "桁架", "楼梯", "坡道", "栏杆", "家具", "材料",
        "wall", "door", "window", "roof", "column", "beam", "floor", "truss", "stair", "furniture",
    ],
    "recipes": [
        "组装", "模板", "矩阵", "速查", "规则总表", "配方", "assembly", "recipe", "matrix",
    ],
    "patterns": [
        "案例", "偏好", "项目", "用户确认", "模式", "pattern",
    ],
}


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def markdown_files(root: Path) -> list[Path]:
    return sorted(
        [p for p in root.rglob("*.md") if p.is_file()],
        key=lambda p: p.relative_to(root).as_posix().casefold(),
    )


def headings(text: str) -> list[dict[str, str | int]]:
    result = []
    for index, line in enumerate(text.splitlines(), start=1):
        match = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
        if match:
            result.append({"line": index, "level": len(match.group(1)), "title": match.group(2)})
    return result


def normalize_title(title: str) -> str:
    title = re.sub(r"^第?[一二三四五六七八九十百零\d]+[、.．]\s*", "", title)
    title = re.sub(r"^[A-Z]\.\d+(?:\.\d+)*\s*", "", title, flags=re.I)
    title = re.sub(r"[`*_#（）()\\[\\]【】:：,，\\s/-]+", "", title)
    replacements = {
        "window": "窗",
        "door": "门",
        "wall": "墙",
        "roof": "屋顶",
        "column": "柱",
        "beam": "梁",
        "floor": "楼板",
        "furniture": "家具",
    }
    folded = title.casefold()
    for src, dst in replacements.items():
        folded = folded.replace(src, dst)
    return folded


def score_categories(text: str) -> list[dict[str, object]]:
    folded = text.casefold()
    scored = []
    for category, keywords in CATEGORY_KEYWORDS.items():
        hits = [kw for kw in keywords if kw.casefold() in folded]
        if hits:
            scored.append({"category": category, "score": len(hits), "keywords": hits[:20]})
    return sorted(scored, key=lambda item: (-int(item["score"]), str(item["category"])))


def duplicate_headings(source_headings: list[dict[str, str | int]], kb_root: Path) -> list[dict[str, object]]:
    source_norm = {
        normalize_title(str(item["title"])): item
        for item in source_headings
        if normalize_title(str(item["title"]))
    }
    duplicates = []
    for file in markdown_files(kb_root):
        if file.name == BASE_EXCLUDE:
            continue
        text = read_text(file)
        for item in headings(text):
            norm = normalize_title(str(item["title"]))
            if norm and norm in source_norm:
                duplicates.append({
                    "source_heading": source_norm[norm],
                    "existing_file": str(file),
                    "existing_heading": item,
                })
    return duplicates[:100]


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit a source document before WildAgent knowledge-base ingest.")
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--kb-root", required=True, type=Path)
    args = parser.parse_args()

    source = args.source.resolve()
    kb_root = args.kb_root.resolve()
    source_text = read_text(source)
    source_headings = headings(source_text)
    md_files = markdown_files(kb_root)
    rag_files = [p for p in md_files if p.name != BASE_EXCLUDE]

    report = {
        "source": str(source),
        "kb_root": str(kb_root),
        "source_chars": len(source_text),
        "source_headings": source_headings[:120],
        "recommended_categories": score_categories(source_text),
        "knowledge_base_markdown_count": len(md_files),
        "rag_candidate_count": len(rag_files),
        "rag_candidates": [str(p.relative_to(kb_root)) for p in rag_files],
        "duplicate_heading_candidates": duplicate_headings(source_headings, kb_root),
        "warnings": [],
    }

    if not source_headings:
        report["warnings"].append("source_has_no_markdown_headings")
    if not report["recommended_categories"]:
        report["warnings"].append("no_category_keyword_match")

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
