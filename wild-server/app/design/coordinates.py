"""体量起点坐标与总体尺寸控制；不把世界原点当场地边界。"""
import json


class DesignCoordinateConflict(ValueError):
    def __init__(self, conflicts: list[dict]):
        self.conflicts = conflicts
        super().__init__(json.dumps({"code": "design_coordinate_conflict", "conflicts": conflicts}, ensure_ascii=False))


def volume_conflicts(volumes: list[dict], massing: dict) -> list[dict]:
    """massing 宽深是总体包络控制上限；差值比较对整体平移不变。"""
    if not volumes:
        return []
    conflicts = []
    for axis, extent in (("x", "width"), ("z", "depth")):
        low = min(v[axis] for v in volumes)
        high = max(v[axis] + v[extent] for v in volumes)
        if high - low > massing[extent] + 0.001:
            conflicts.append({"path": "/decisions/volumes", "value": volumes,
                "conflict_path": "/decisions/massing/" + extent,
                "conflict_value": massing[extent], "actual_extent": high - low,
                "reason": "体量并集包围盒超出总体尺寸控制；必须显式修订，不能裁剪体量"})
    for index, v in enumerate(volumes):
        if v["end_floor"] > massing["modeled_floors"]:
            conflicts.append({"path": f"/decisions/volumes/{index}/end_floor", "value": v["end_floor"],
                "conflict_path": "/decisions/massing/modeled_floors",
                "conflict_value": massing["modeled_floors"], "reason": "体量楼层超出建模层数"})
    return conflicts
