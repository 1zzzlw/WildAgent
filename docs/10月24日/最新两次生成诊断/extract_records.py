"""只读提取指定两次真实运行，不调用模型、不修改生产记录。"""
import json
from pathlib import Path
import sqlite3
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
storage = ROOT / "wild-server/storage/sessions"
connection = sqlite3.connect((storage / "langgraph_checkpoints.sqlite3").as_uri()+"?mode=ro", uri=True)
serializer = JsonPlusSerializer()
for sid, rid in [("session_1792828902444", "req_1792828910741_tfntshsit"),
                 ("session_1792838578836", "req_1792838583260_l77fp34wy")]:
    checkpoint_id, kind, blob = connection.execute(
        "select checkpoint_id,type,checkpoint from checkpoints where thread_id=? order by checkpoint_id desc limit 1",
        ("generation:"+rid,)).fetchone()
    state = serializer.loads_typed((kind, blob))["channel_values"]
    output = HERE / sid
    output.mkdir(exist_ok=True)
    (output / "state.json").write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    source = {"session_id": sid, "request_id": rid, "checkpoint_id": checkpoint_id,
              "session_file": str(storage / (sid+".json")),
              "trace_file": str(storage / "rag_traces" / sid / (rid+".json")),
              "read_only": True, "new_model_calls": 0}
    (output / "source.json").write_text(json.dumps(source, ensure_ascii=False, indent=2), encoding="utf-8")
    print(sid, checkpoint_id, state.get("status"))
connection.close()
