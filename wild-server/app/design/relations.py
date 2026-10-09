"""有限的柱—雨棚几何支撑判据；编译、计划对账和履约共用，不证明荷载安全。"""
from math import hypot, isfinite

TOLERANCE = 0.001  # 米，与批准实体比较相同，1mm。


def entity_index(blueprint: dict) -> dict:
    geometry = blueprint.get("geometry") or {}
    return {e["id"]: e for bucket in ("elements", "components")
            for e in geometry.get(bucket, []) if isinstance(e, dict) and e.get("id")}


def canopy_support_point(blueprint: dict, relation: dict) -> tuple[list, float]:
    """沿墙比例、出挑比例 → 世界柱顶；与 core canopy 的墙外表面及板底一致。"""
    entities = entity_index(blueprint)
    canopy = entities.get(relation.get("target"))
    if not canopy or canopy.get("type") != "canopy":
        raise ValueError("支撑目标不存在或不是 canopy")
    wall = entities.get(canopy.get("parentWall"))
    if not wall or wall.get("type") != "wall" or wall.get("curve"):
        raise ValueError("支撑目标需要真实直墙宿主；曲墙支撑尚不支持")
    a, b = wall["from"], wall["to"]
    length = hypot(b[0]-a[0], b[2]-a[2])
    if length <= TOLERANCE:
        raise ValueError("宿主墙长度无效")
    ux, uz = (b[0]-a[0])/length, (b[2]-a[2])/length
    nx, nz = -uz, ux
    points = [p for e in entities.values() if e.get("type") == "wall" for p in (e["from"], e["to"])]
    cx = (min(p[0] for p in points)+max(p[0] for p in points))/2
    cz = (min(p[2] for p in points)+max(p[2] for p in points))/2
    along, mount, offset = canopy["from"]
    midpoint = along+canopy["width"]/2
    dot = (a[0]+ux*midpoint-cx)*nx+(a[2]+uz*midpoint-cz)*nz
    sign = 1 if dot > 1e-6 else -1
    along += canopy["width"]*relation["along_ratio"]
    offset += sign*(wall["thickness"]/2+canopy["depth"]*relation["depth_ratio"])
    top = mount-canopy["thickness"]/2
    bottom = min(a[1], b[1])
    if top <= bottom:
        raise ValueError("雨棚板底不高于宿主底标高")
    point = [a[0]+ux*along+nx*offset, top, a[2]+uz*along+nz*offset]
    if not all(isfinite(v) for v in point):
        raise ValueError("关系坐标不是有限数")
    return point, bottom


def evaluate_support(blueprint: dict, entity_id: str, relation: dict) -> dict:
    entities = entity_index(blueprint)
    column = entities.get(entity_id)
    base = {"entity_id": entity_id, "target": relation.get("target"), "tolerance_m": TOLERANCE}
    if not column or column.get("type") != "column":
        return {**base, "status": "open", "reason": "对应柱实体缺失或类型错误"}
    try:
        point, bottom = canopy_support_point(blueprint, relation)
        start = column["base"]
        end = [start[0], start[1]+column["height"], start[2]]
        values = start+end
        if len(start) != 3 or len(end) != 3 or not all(isinstance(v, (float, int)) and not isinstance(v, bool) and isfinite(v) for v in values):
            raise ValueError("柱端点无效")
        valid = (abs(start[0]-point[0]) <= TOLERANCE and abs(start[2]-point[2]) <= TOLERANCE
                 and abs(end[0]-point[0]) <= TOLERANCE and abs(end[2]-point[2]) <= TOLERANCE
                 and abs(min(start[1], end[1])-bottom) <= TOLERANCE
                 and abs(max(start[1], end[1])-point[1]) <= TOLERANCE)
        return {**base, "status": "satisfied" if valid else "open", "expected_top": point,
                "actual_from": start, "actual_to": end, "reason": "核对局部支撑位置、柱底与雨棚板底；仅证明几何关系"}
    except (ValueError, KeyError, TypeError, IndexError) as exc:
        return {**base, "status": "open", "reason": str(exc)}
