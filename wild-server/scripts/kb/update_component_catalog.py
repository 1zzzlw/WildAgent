"""从活动知识元数据刷新参考目录；--check 用于检查目录是否过期。"""
from pathlib import Path
import argparse
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from app.agent.knowledge.component_names import component_catalog_document


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    path = ROOT / "storage/knowledge_base/knowledge/components/component-catalog.md"
    expected = component_catalog_document()
    if args.check:
        if not path.exists() or path.read_text(encoding="utf-8") != expected:
            raise SystemExit("构件目录已过期，请运行 scripts/kb/update_component_catalog.py")
    else:
        path.write_text(expected, encoding="utf-8")
    print("构件目录与活动知识元数据一致")
