"""从 eval_retrieval.py 的 JSON 结果校准 Retrieval Gate 距离阈值。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SERVER_ROOT = Path(__file__).resolve().parents[2]
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))

from app.agent.rag_calibration import calibrate_distance_threshold


def main() -> int:
    parser = argparse.ArgumentParser(description="使用正负样本校准 RAG distance 阈值")
    parser.add_argument("eval_json", type=Path, help="eval_retrieval.py --json-output 产物")
    parser.add_argument("--output", type=Path, help="校准结果 JSON；默认打印到控制台")
    args = parser.parse_args()

    payload = json.loads(args.eval_json.read_text(encoding="utf-8"))
    samples = []
    for result in payload.get("results", []):
        expected_action = str(result.get("expectedAction") or "answer").lower()
        hits = result.get("hits") or []
        top_distance = hits[0].get("distance") if hits else None
        samples.append({
            "id": result.get("id"),
            "should_answer": expected_action != "reject",
            "distance": top_distance,
        })
    calibration = calibrate_distance_threshold(samples)
    calibration["embedding"] = payload.get("run", {}).get("embedding")
    calibration["index_signature"] = payload.get("run", {}).get("index_signature")
    calibration["config_example"] = {
        "RAG__RETRIEVAL_GATE__MODE": "observe",
        "RAG__RETRIEVAL_GATE__MAX_DISTANCE": round(calibration["threshold"], 6),
    }
    text = json.dumps(calibration, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
        print(f"阈值校准报告已生成: {args.output}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
