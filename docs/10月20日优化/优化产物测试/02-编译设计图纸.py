"""把本目录的最终模型图纸编译成 WILD；针对本次矩形双层、平屋面、U 形楼梯方案。

运行：python 02-编译设计图纸.py
仅用 Python 标准库，只写本目录；不导入 Agent，不调用模型，不改变源图纸。
"""
import hashlib
import json
import math
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = HERE / "01-设计图纸.json"
DESIGN = json.loads(SOURCE.read_text(encoding="utf-8"))
LEVELS = DESIGN["levels"]
T = DESIGN["slab_thickness"]
elements, components, materials = [], [], {}
hosts, opening_records, stair_records, warnings = {}, [], [], []


def floor(eid, rect, top, thickness, material):
    x0, x1, z0, z1 = rect
    elements.append(dict(type="floor", id=eid, **{
        "from": [x0, top-thickness, z0], "to": [x1, top-thickness, z1]},
        thickness=thickness, material=material))


def box(eid, rect, bottom, height, material):
    x0, x1, z0, z1 = rect
    elements.append(dict(type="primitive", id=eid, shape="box",
        position=[(x0+x1)/2, bottom+height/2, (z0+z1)/2],
        dimensions=[x1-x0, height, z1-z0], material=material))


def wall(eid, start, end, bottom, top, thickness, material):
    row = dict(type="wall", id=eid, **{
        "from": [start[0], bottom, start[1]], "to": [end[0], top, end[1]]},
        thickness=thickness, material=material)
    elements.append(row)
    hosts[eid] = row


def partition(regions, cuts):
    """按矩形边界网格切片，扣洞后合并同行；与当前图纸推导采用同一算法。"""
    xs = sorted({x for r in regions+cuts for x in r[:2]})
    zs = sorted({z for r in regions+cuts for z in r[2:]})
    def inside(cell, rect):
        return rect[0]-1e-8 <= cell[0] and cell[1] <= rect[1]+1e-8 and rect[2]-1e-8 <= cell[2] and cell[3] <= rect[3]+1e-8
    result = []
    for z0, z1 in zip(zs, zs[1:]):
        row = []
        for x0, x1 in zip(xs, xs[1:]):
            cell = [x0, x1, z0, z1]
            if not any(inside(cell, r) for r in regions) or any(inside(cell, r) for r in cuts):
                continue
            if row and abs(row[-1][1]-x0) < 1e-8:
                row[-1][1] = x1
            else:
                row.append(cell)
        result.extend(row)
    return result


def guard(eid, path, material):
    components.append(dict(type="railing", id=eid, path=path, height=0.95,
        postSpacing=0.9, postRadius=0.018, railRadius=0.022, railLevels=[0.5, 1],
        material=material))


def mat(role, color, roughness, metallic=0, **extra):
    materials[role] = dict(baseColor=color, roughness=roughness, metallic=metallic,
        albedo=1, lightingCondition="D65_noon", **extra)


def rounded(value):
    if isinstance(value, float):
        return round(value, 6)
    if isinstance(value, list):
        return [rounded(item) for item in value]
    if isinstance(value, dict):
        return {key: rounded(item) for key, item in value.items()}
    return value


# 图纸提供材料意图，PBR 数值是本次作者脚本的显式实现选择，不冒充模型输出。
mat("exterior_wall", [0.91, 0.90, 0.87], 0.88)
mat("interior_wall", [0.94, 0.93, 0.90], 0.90)
mat("roof", [0.22, 0.23, 0.24], 0.94)
mat("timber", [0.64, 0.46, 0.27], 0.72)
mat("door_frame", [0.16, 0.17, 0.18], 0.35, 0.72)
mat("window_frame", [0.17, 0.18, 0.19], 0.35, 0.72)
mat("interior_door", [0.88, 0.87, 0.83], 0.65)
mat("front_door", [0.24, 0.13, 0.075], 0.66)
mat("steel", [0.15, 0.17, 0.18], 0.40, 0.76)
mat("concrete", [0.64, 0.63, 0.60], 0.91)
for role in ("glass", "glass_canopy"):
    mat(role, [0.88, 0.94, 0.96], 0.07, materialClass="glass",
        transmission=0.92, ior=1.5, thickness=0.012, opacity=1, side="double")
if set(materials) != set(DESIGN["material_roles"]):
    raise ValueError("此专用脚本的材料表与源图纸不同；请明确更新材料实现")

ordered = sorted(LEVELS, key=LEVELS.get)
next_level = dict(zip(ordered, ordered[1:]))
volume_by_id = {v["id"]: v for v in DESIGN["volumes"]}
voids = list(DESIGN.get("voids", []))
for stair in DESIGN["stairs"]:
    if stair["shape"] != "U" or stair["direction"] != "+z":
        raise ValueError("本次专用脚本只实现图纸中的 +z U 形双跑")
    voids.extend(dict(id=f"{stair['id']}_{level}_void", level=level,
        rect=stair["rect"], volume=stair["volume"]) for level in ordered
        if LEVELS[stair["from_level"]] < LEVELS[level] <= LEVELS[stair["to_level"]])

# 场地和首层同标高，但扣掉建筑覆盖，避免两张顶面重合。
for i, rect in enumerate(partition([DESIGN["site"]], [v["rect"] for v in DESIGN["volumes"]])):
    floor(f"site_{i}", rect, min(LEVELS.values()), 0.12, "concrete")
slab_records = {}
for level in ordered:
    regions = [v["rect"] for v in DESIGN["volumes"]
        if LEVELS[v["bottom"]] <= LEVELS[level] < LEVELS[v["top"]]]
    cuts = [v["rect"] for v in voids if v["level"] == level]
    rectangles = partition(regions, cuts)
    slab_records[level] = rectangles
    for i, rect in enumerate(rectangles):
        floor(f"slab_{level}_{i}", rect, LEVELS[level], T, "concrete")

# 原生墙以体量边界为中线；每层拆分宿主，offset 正向与设计提示词一致。
for volume in DESIGN["volumes"]:
    x0, x1, z0, z1 = volume["rect"]
    faces = {"front": ([x0, z0], [x1, z0]), "back": ([x1, z1], [x0, z1]),
             "left": ([x0, z1], [x0, z0]), "right": ([x1, z0], [x1, z1])}
    for level in ordered:
        if not LEVELS[volume["bottom"]] <= LEVELS[level] < LEVELS[volume["top"]]:
            continue
        top = min(LEVELS[next_level[level]], LEVELS[volume["top"]])-T
        for face, (start, end) in faces.items():
            wall(f"{volume['id']}_{face}_{level}", start, end,
                LEVELS[level], top, volume.get("wall_thickness", 0.24), volume["material_role"])
for row in DESIGN["walls"]:
    wall(row["id"], row["start"], row["end"], LEVELS[row["level"]],
        LEVELS[row.get("top") or next_level[row["level"]]]-T,
        row.get("thickness", 0.18), row["material_role"])

# 门窗使用真实宿主，from=[沿墙距离,世界底标高,法向偏移]。
for opening in DESIGN["openings"]:
    oid = opening["id"]
    host_id = (f"{opening['host']}_{opening['face']}_{opening['level']}"
               if opening["host"] in volume_by_id else opening["host"])
    host = hosts[host_id]
    along, bottom = opening["offset"], LEVELS[opening["level"]]+opening.get("sill", 0)
    width, height = opening["width"], opening["height"]
    length = math.hypot(host["to"][0]-host["from"][0], host["to"][2]-host["from"][2])
    if along < 0 or along+width > length+1e-7 or bottom < host["from"][1]-1e-7 or bottom+height > host["to"][1]+1e-7:
        raise ValueError(f"{oid} 超出宿主，不能静默挪动门窗")
    component = dict(type=opening["type"], id=oid, parentWall=host_id,
        **{"from": [along, bottom, 0]}, width=width, height=height,
        frameWidth=0.05, frameDepth=host["thickness"], frameMaterial=opening["frame_role"])
    if opening["type"] == "window":
        vm, hm = opening.get("divisions", [0, 0])
        component.update(glassDepth=0.012, verticalMullions=vm, horizontalMullions=hm,
            mullionWidth=0.025, glassMaterial=opening["panel_role"])
    elif opening["type"] == "door":
        component.update(leafDepth=0.035, leafMaterial=opening["panel_role"],
            openingStyle="rectangular", doorStyle="double" if width > 1.3 else "single")
    else:
        raise ValueError("此源图纸没有无框洞口，专用脚本未实现该类型")
    if opening["style"] != "fixed":
        component["interaction"] = dict(mode=opening["style"], hingeSide="left")
    components.append(component)
    dx, dz = host["to"][0]-host["from"][0], host["to"][2]-host["from"][2]
    opening_records.append(dict(id=oid, host=host_id, interval=[along, along+width],
        bottom=bottom, top=bottom+height,
        world_center=[host["from"][0]+dx*(along+width/2)/length,
                      bottom+height/2, host["from"][2]+dz*(along+width/2)/length]))

# 本图所有屋面均为平屋面；原生 roof 自身就是顶部板，不再铺第二张重合楼板。
for roof in DESIGN["roofs"]:
    if roof["type"] != "flat":
        raise ValueError("本次专用脚本只实现本图的平屋面")
    volume = volume_by_id[roof["volume"]]
    x0, x1, z0, z1 = volume["rect"]
    west, east, south, north = roof.get("overhang", [0, 0, 0, 0])
    rect = [x0-west, x1+east, z0-south, z1+north]
    top = LEVELS[volume["top"]]
    elements.append(dict(type="roof", id=roof["id"], roofType="flat", ridgeAxis="x",
        span=rect[1]-rect[0], depth=rect[3]-rect[2], height=T, thickness=T,
        position=[(rect[0]+rect[1])/2, top-T, (rect[2]+rect[3])/2], material=roof["material_role"]))
    h = roof.get("parapet_height", 0)
    if h:
        a, b, c, d = rect
        for i, edge in enumerate([[a,b,c,c+0.12],[a,b,d-0.12,d],[a,a+0.12,c+0.12,d-0.12],[b-0.12,b,c+0.12,d-0.12]]):
            box(f"{roof['id']}_parapet_{i}", edge, top, h, volume["material_role"])

for stair in DESIGN["stairs"]:
    sid = stair["id"]
    x0, x1, z0, z1 = stair["rect"]
    bottom, top = LEVELS[stair["from_level"]], LEVELS[stair["to_level"]]
    count = stair.get("steps_each") or math.ceil((top-bottom)/(2*stair["max_riser_height"]))
    riser, run = (top-bottom)/(2*count), count*stair["tread_depth"]
    width, landing = stair["flight_width"], stair["landing_depth"]
    if riser > stair["max_riser_height"]+1e-7 or run+landing > z1-z0+1e-7 or 2*width > x1-x0+1e-7:
        raise ValueError(f"{sid} 的梯段与平台无法放入源图占地")
    mid = (bottom+top)/2
    first_x, second_x, back = x0+width/2, x1-width/2, z0+run
    for flight, x, a, b, za, zb in [
        ("first", first_x, bottom, mid, z0, back),
        ("second", second_x, mid, top, back, z0)]:
        elements.append(dict(type="stair", id=f"{sid}_{flight}",
            **{"from": [x,a,za], "to": [x,b,zb]}, width=width,
            stepCount=count, stepDepth=stair["tread_depth"], stepHeight=riser, material=stair["material_role"]))
    floor(f"{sid}_half_landing", [x0,x1,back,back+landing], mid, 0.18, stair["material_role"])
    # 原材料说明明确写了“踏步与扶手”；扶手截面和高度为本次实现细节。
    guard(f"{sid}_first_guard", [[x0,bottom,z0],[x0,mid,back]], stair["material_role"])
    guard(f"{sid}_second_guard", [[x1,mid,back],[x1,top,z0]], stair["material_role"])
    guard(f"{sid}_landing_guard", [[x0,mid,back+landing],[x1,mid,back+landing]], stair["material_role"])
    stair_records.append(dict(id=sid, rise=top-bottom, steps_each=count, riser_height=riser,
        flight_run=run, landing_elevation=mid, upper_exit=[second_x,top,z0],
        slab_void=stair["rect"], unused_depth=z1-z0-run-landing))

for row in DESIGN["components"]:
    x0, x1, z0, z1 = row["rect"]
    bottom = LEVELS[row["level"]]+row.get("elevation_offset", 0)
    if row.get("anchor", "bottom") == "top":
        bottom -= row["height"]
    role = row["material_roles"]
    if row["recipe"] == "entrance_canopy":
        top, steel_width, steel_height, glass = bottom+row["height"], 0.06, 0.10, 0.012
        box(row["id"]+"_glass", row["rect"], top-glass, glass, role["cladding"])
        for i, edge in enumerate([[x0,x0+steel_width,z0,z1],[x1-steel_width,x1,z0,z1],
                                  [x0+steel_width,x1-steel_width,z0,z0+steel_width],
                                  [x0+steel_width,x1-steel_width,z1-steel_width,z1]]):
            box(row["id"]+f"_frame_{i}", edge, top-glass-steel_height, steel_height, role["structure"])
        # 两块贴墙安装板占满声明的 0.15m 高度，边框和玻璃均位于声明包络内。
        for i, x in enumerate([x0+0.12, x1-0.12]):
            box(row["id"]+f"_mount_{i}", [x-0.05,x+0.05,z1-0.03,z1], bottom, row["height"], role["structure"])
    elif row["recipe"] == "entrance_steps":
        count = int(row["parameters"]["count"])
        rise, tread = row["parameters"]["rise"], row["parameters"]["tread"]
        if abs(count*rise-row["height"]) > 1e-7 or count*tread > z1-z0+1e-7:
            raise ValueError("入口台阶参数与声明包络矛盾")
        elements.append(dict(type="stair", id=row["id"],
            **{"from": [(x0+x1)/2,bottom,z1-count*tread], "to": [(x0+x1)/2,bottom+row["height"],z1]},
            width=x1-x0, stepCount=count, stepDepth=tread, stepHeight=rise, material=role["surface"]))
    else:
        raise ValueError(f"未实现的配方 {row['recipe']}，不能悄悄遗漏")

# 记录输入中残留的关系问题，保留原图坐标，不伪造为“已修复”。
for i, a in enumerate(opening_records):
    for b in opening_records[i+1:]:
        if a["host"] == b["host"] and min(a["interval"][1], b["interval"][1]) > max(a["interval"][0], b["interval"][0])+1e-7 and min(a["top"],b["top"]) > max(a["bottom"],b["bottom"])+1e-7:
            warnings.append(dict(code="overlapping_openings", ids=[a["id"], b["id"]], host=a["host"],
                overlap=min(a["interval"][1],b["interval"][1])-max(a["interval"][0],b["interval"][0]),
                note="两扇门仍按源图重叠保留，参数校验通过不代表布局正确"))
warnings.extend([
    dict(code="stair_room_mismatch", ids=["r_stair_area","s1"], note="楼梯间 [9.5,12,0,3] 未包含楼梯预留区 [9,11.5,0,4.3]"),
    dict(code="stair_wall_conflict", ids=["s1_first","w14","w2"], note="w14 沿第一跑中线，w2 穿过中间平台；未移动内墙或楼梯"),
    dict(code="upper_exit_not_resolved", ids=["s1","main_front_level1"], note="U 梯上层出口回到 Z=0 外墙边，且整组预留区已扣板；原图未明确可用到达板"),
    dict(code="entrance_level_conflict", ids=["c_steps","o_main_entry"], note="台阶顶为 +0.15，门底为 0；保留原锚点，未调整地面或门底"),
    dict(code="room_opening_intent_unverified", ids=["o_north_kitchen","o_door_dining_hall1"], note="北窗按 back 正向落在 X=7..11.2，并不位于厨房 X=0..6；修改后的 dining_hall1 门位于 w6 卫生间/过渡间界面"),
    dict(code="route_connectivity_unverified", note="路线作为审阅数据保留，宽度一致不等于穿墙处均有门或二层出口可达"),
])

blueprint = rounded(dict(meta=dict(version="1.0", type="building", name=DESIGN["name"],
    author="Codex", style="modern-villa"), geometry=dict(elements=elements, components=components),
    materials=materials, assets={}))
ids = [row["id"] for row in elements+components]
if len(set(ids)) != len(ids):
    raise ValueError("编译产物存在重复 ID")
for row in elements+components:
    for key, value in row.items():
        if (key == "material" or key.endswith("Material")) and isinstance(value,str) and value not in materials:
            raise ValueError(f"{row['id']}.{key} 引用了未定义材质")
    if row["type"] == "primitive" and any(x <= 0 for x in row["dimensions"]):
        raise ValueError(f"{row['id']} 存在非正实体尺寸")

target = HERE / "两层现代别墅.wild"
target.write_text(json.dumps(blueprint, ensure_ascii=False, indent=2, allow_nan=False)+"\n", encoding="utf-8")
record = dict(source=SOURCE.name, source_sha256=hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
    target=target.name, target_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
    elements=len(elements), components=len(components), materials=len(materials),
    element_types=dict(Counter(e["type"] for e in elements)),
    component_types=dict(Counter(c["type"] for c in components)),
    stairs=stair_records, voids=voids, slabs=slab_records, openings=opening_records,
    material_implementation=materials,
    assumptions=["场地顶面取首层标高，扣除建筑占地；未给定的楼板与场地材料采用图中 concrete",
        "外墙中心线取体量 rect 边界；每层单独生成门窗宿主",
        "门窗框宽 0.05m，门扇厚 0.035m，玻璃厚 0.012m；宽于 1.3m 的门使用双扇",
        "U 形梯段靠预留区左右边界布置，中间平台从计算的梯段末端向后延伸；剩余 0.3m 不冒充上层出口",
        "楼梯扶手高 0.95m、柱距 0.9m；对应材料说明中的扶手，不证明防护合规",
        "雨棚按 100x60 型材、12mm玻璃及贴墙安装板表达；女儿墙厚度取 0.12m",
        "未增加家具、功能房间、照明或景观；routes/room_zones 保留在源图和记录，不当成实体自动建墙"],
    source_relationship_issues=warnings,
    validation_scope="脚本内检查 ID、材质引用、开口宿主边界与梯级算式；未运行 Agent 测试、真实模型、渲染或完整空间验收")
(HERE/"03-编译记录.json").write_text(json.dumps(rounded(record), ensure_ascii=False, indent=2, allow_nan=False)+"\n", encoding="utf-8")
print(json.dumps(dict(file=str(target), elements=len(elements), components=len(components),
    materials=len(materials), source_relationship_issues=len(warnings), sha256=record["target_sha256"]), ensure_ascii=False))
