"""导出或核对 DesignDocument 的正式 JSON Schema。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


SERVER_ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_ROOT = SERVER_ROOT.parent
DEFAULT_OUTPUT = REPOSITORY_ROOT / "docs" / "9月9日优化" / "design-document.schema.json"
sys.path.insert(0, str(SERVER_ROOT))

from app.design.contracts import DesignDocument  # noqa: E402


def schema_text() -> str:
    return json.dumps(
        DesignDocument.model_json_schema(),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    expected = schema_text()
    if args.check:
        if not args.output.exists() or args.output.read_text(encoding="utf-8") != expected:
            print(f"DesignDocument Schema 已过期: {args.output}")
            return 1
        print(f"DesignDocument Schema 一致: {args.output}")
        return 0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(expected, encoding="utf-8")
    print(f"已导出 DesignDocument Schema: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
