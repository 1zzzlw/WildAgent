"""从最终 WILD 生成检查副本；保留原件，移除屋面、三段墙及其依附件。"""
import json
from pathlib import Path

out=Path(__file__).resolve().parent
blueprint=json.loads((out/"栖庭-新中式别墅.wild").read_text(encoding="utf-8"))
report=json.loads((out/"05-编译与验收报告.json").read_text(encoding="utf-8"))
removed={i for k,r in report["implementations"].items() if k.startswith("roof_") for i in r["entity_ids"]}
removed.update(["wall_main_front_L2","wall_main_right_L2","partition_2_east"])
entities=[e for bucket in ("elements","components") for e in blueprint["geometry"][bucket]]
while True:
    dependents={e["id"] for e in entities
                if any(k.startswith("parent") and v in removed for k,v in e.items() if isinstance(v,str))}
    if dependents<=removed:
        break
    removed.update(dependents)
for bucket in ("elements","components"):
    blueprint["geometry"][bucket]=[e for e in blueprint["geometry"][bucket] if e["id"] not in removed]
blueprint["meta"]["name"]="栖庭别墅-剖切复核（移除屋面、三段二层墙及依附件）"
for name,value in [("07-剖切复核.json",blueprint),("07-剖切移除清单.json",sorted(removed))]:
    (out/name).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding="utf-8")
print(f"剖切副本移除 {len(removed)} 个实体；正式WILD保持不变")
