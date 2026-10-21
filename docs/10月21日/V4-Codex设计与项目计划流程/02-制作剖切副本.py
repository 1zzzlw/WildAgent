"""直接筛选本轮最终 WILD 制作查看梯井的副本；不重建或修改任何保留实体。"""
import json
from hashlib import sha256
from pathlib import Path

out=Path(__file__).resolve().parent
source=out/"栖庭V4-新中式别墅.wild"
blueprint=json.loads(source.read_text(encoding="utf-8"))
report=json.loads((out/"07-final_validate节点输出.json").read_text(encoding="utf-8"))
records=report["design_brief"]["implementation"]["records"] if "design_brief" in report else json.loads(
    (out/"06-compile节点输出.json").read_text(encoding="utf-8"))["design_brief"]["implementation"]["records"]
removed=set()
for marker,record in records.items():
    if marker.startswith("roof_") or marker=="trim_main":
        removed.update(record["entity_ids"])
for entity in blueprint["geometry"]["elements"]:
    name=entity["id"]
    if (name.startswith("wall_") and name.endswith("_L2")) or name.startswith("partition_2_"):
        removed.add(name)
for entity in blueprint["geometry"]["components"]:
    if entity.get("parentWall") in removed:
        removed.add(entity["id"])
for bucket in ("elements","components"):
    blueprint["geometry"][bucket]=[e for e in blueprint["geometry"][bucket] if e["id"] not in removed]
target=out/"10-剖切查看副本.wild"
target.write_text(json.dumps(blueprint,ensure_ascii=False,indent=2),encoding="utf-8")
(out/"10-剖切来源.json").write_text(json.dumps({
    "source":source.name,"source_sha256":sha256(source.read_bytes()).hexdigest(),
    "copy":target.name,"copy_sha256":sha256(target.read_bytes()).hexdigest(),
    "removed_entity_ids":sorted(removed),"preserved_entities_unchanged":True,
    "purpose":"显露二层楼板、完整梯井、双跑楼梯与半平台；剖切副本不是最终交付文件"
},ensure_ascii=False,indent=2),encoding="utf-8")
print(f"剖切仅移除 {len(removed)} 个实体，最终 WILD 保留原样")
