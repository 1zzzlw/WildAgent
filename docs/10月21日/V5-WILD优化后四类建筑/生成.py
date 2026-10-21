"""Codex 独立设计 → 项目 DesignDocument/投影 → 确定性 WILD；无 plan、无模型 API。"""
from copy import deepcopy
from collections import Counter
from hashlib import sha256
import json
from math import hypot, pi
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "wild-server"))
import jsonschema
from app.design.contracts import DesignDocument, VolumeDecision
from app.design.compilation import project_drawing
from app.design.coordinates import exterior_facade_intervals
from app.design.realization import realize_marker
from app.design.relations import opening_target
from app.utils.blueprint_normalizer import get_schema
from app.utils.staircase import expand_staircases

OUT = Path(__file__).resolve().parent


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def mat(color, roughness=0.75, metallic=0, **kwargs):
    return dict(baseColor=color, roughness=roughness, metallic=metallic, albedo=1,
                lightingCondition="D65_noon", **kwargs)


class Drawing:
    def __init__(self, folder, name, concept, floors, height, base, volumes, palette, roof):
        self.folder, self.name = folder, name
        self.base, self.floor_height = base, height
        self.parts = []
        self.d = dict(kind="architecture", concept=concept,
            massing=dict(shape="custom", floors=floors, modeled_floors=floors,
                         representation_mode="full", floor_height=height),
            complexity=dict(level="detailed", reason="以构造层次和材质表达区分建筑，不以门窗数量定义精细度"),
            volumes=volumes, structural_grid=dict(system="frame", x_bays=4, z_bays=3),
            envelope=dict(system="solid_wall"), construction=dict(slab_thickness=0.22, wall_thickness=0.26),
            facades={face: self.facade() for face in ("front", "back", "left", "right")},
            roof=roof, circulation=dict(vertical_strategy="stair" if floors > 1 else "single_level"),
            floor_layouts=[dict(floor=i, level=base+(i-1)*height) for i in range(1, floors+1)],
            materials=dict(definitions=palette, resolved_plan=dict(concept=concept[:150], roles=[
                dict(role=role, materialId=role, material=palette[role]) for role in (
                    "facade_primary", "structure", "floor", "frame", "door", "glass", "roof", "ground", "accent")])),
            components=self.parts, detail_packages=["结构层次", "檐口与收边", "入口与场地", "立面构造"])

    @staticmethod
    def facade(opened=False):
        return dict(bays=1, ground_pattern=["open" if opened else "empty"],
                    upper_pattern=["open" if opened else "empty"])

    def add(self, kind, id, position=None, size=None, form=None, material="accent", **kwargs):
        row = dict(type=kind, id=id.replace(".", "p"), description=id.replace("_", " "),
                   form=form or {}, material_bindings={"material": material}, **kwargs)
        if position is not None: row["placement"] = dict(position=list(position))
        if size: row["size"] = dict(zip(("width", "height", "depth"), size))
        self.parts.append(row)
        return row

    def box(self, id, center, dims, material="accent", rotation=None):
        return self.add("primitive", id, center, dims,
                        dict(shape="box", **({"rotation": rotation} if rotation else {})), material)

    def beam(self, id, a, b, width, height, material="structure"):
        return self.add("beam", id, form=dict(**{"from": a, "to": b}, width=width, height=height,
                                             crossSection="rect"), material=material)

    def column(self, id, x, z, bottom, top, radius, style="modern", material="structure"):
        return self.add("column", id, [x, (bottom+top)/2, z],
                        form=dict(base=[x, bottom, z], height=top-bottom, bottomRadius=radius,
                                  topRadius=radius*0.88, style=style, flutes=16 if style == "ionic" else 0),
                        material=material)

    def repeat(self, id, center, member, axis, count, spacing, material="accent"):
        dims = list(member)
        dims["xyz".index(axis)] += (count-1)*spacing
        return self.add("primitive", id, center, dims, dict(shape="box"), material,
                        repetition=dict(axis=axis, count=count, spacing=spacing, member_size=member))

    def ring(self, id, x0, z0, x1, z1, y, width, height, material="accent"):
        for i, (a,b) in enumerate((([x0,y,z0],[x1,y,z0]), ([x1,y,z0],[x1,y,z1]),
                                  ([x1,y,z1],[x0,y,z1]), ([x0,y,z1],[x0,y,z0]))):
            self.beam(f"{id}_{i}", a, b, width, height, material)

    def railing(self, id, path, glass=False):
        return self.add("railing", id, form=dict(path=path, height=1.05, postSpacing=1.15,
            postRadius=0.026, railRadius=0.025, railLevels=[1],
            **(dict(infillType="glass", infillMaterial="glass", infillThickness=0.014) if glass else {})),
            material="frame")

    def stair(self, id, x, z, floor, direction="+z", width=2.9, depth=5):
        row = self.add("stair", id, size=[width, self.floor_height, depth], material="structure",
            form=dict(shape="U", flights=2, span_direction=direction, flight_width=1.25,
                      landing_depth=1.25, max_riser_height=0.18, landing_thickness=0.22),
            floor_connections=[dict(from_floor=floor, to_floor=floor+1)])
        row["placement"] = dict(plan_position=[x,z])

    def facade_windows(self, volume, face, floor, bays, width, height, sill, classical=False, entrance=False):
        v = next(v for v in self.d["volumes"] if v["id"] == volume)
        length = v["width"] if face in {"front","back"} else v["depth"]
        level = self.base+(floor-1)*self.floor_height
        exposed = exterior_facade_intervals(VolumeDecision.model_validate(v), face, floor,
                    [VolumeDecision.model_validate(item) for item in self.d["volumes"]])
        x0,z0,x1,z1 = v["x"],v["z"],v["x"]+v["width"],v["z"]+v["depth"]
        origin, axis, sign = {"front":([x0,z0],0,1), "right":([x1,z0],1,1),
                             "back":([x1,z1],0,-1), "left":([x0,z1],1,-1)}[face]
        for i in range(bays):
            along = (i+0.5)*length/bays
            if not any(a+0.1 <= along-width/2 and along+width/2 <= b-0.1 for a,b in exposed): continue
            isdoor = entrance and i == bays//2
            w,h = (2.2,2.8) if isdoor else (width,height)
            bottom = level if isdoor else level+sill
            id = f"{'door' if isdoor else 'window'}_{volume}_{face}_{floor}_{i}"
            self.parts.append(dict(type="door" if isdoor else "window", id=id,
                host=f"wall_{volume}_{face}_L{floor}", size=dict(width=w,height=h),
                placement=dict(offset=along-w/2, sill_height=bottom-level),
                form=(dict(openingStyle="arched" if classical else "rectangular", doorStyle="double",
                           frameWidth=0.09, frameDepth=0.24, leafDepth=0.065, frameMaterial="frame", leafMaterial="door")
                      if isdoor else dict(frameWidth=0.065, frameDepth=0.16, glassDepth=0.022,
                          verticalMullions=1 if classical else 0, horizontalMullions=1 if classical else 0,
                          mullionWidth=0.035, frameMaterial="frame", glassMaterial="glass"))))
            if classical and not isdoor:
                p = list(origin); p[axis] += sign*along
                for label,y,t in (("sill",bottom-0.10,0.16),("head",bottom+h+0.10,0.18)):
                    center = [p[0],y,p[1]]
                    center[2 if axis == 0 else 0] += -0.18 if face in {"front","left"} else 0.18
                    dims = [w+0.38,t,0.24] if axis == 0 else [0.24,t,w+0.38]
                    self.box(id+"_"+label, center, dims, "accent")

    def document(self):
        return DesignDocument.model_validate(dict(design_id=self.folder+"_v5", session_id="codex_v5_20261021",
            revision=1, status="compiled", requirements=dict(source_request=f"独立设计并生成{self.folder} WILD：{self.name}",
                building_type=self.folder, profile="custom", style_intent=[self.d["concept"][:180]]), decisions=self.d))


def palette(wall, structure, roof, accent, wood=(0.24,0.14,0.075), glass=(0.37,0.58,0.66)):
    return dict(facade_primary=mat(wall), structure=mat(structure), floor=mat([0.67,0.65,0.60]),
        frame=mat([0.13,0.14,0.14],0.35,0.65), door=mat(wood,0.57),
        glass=mat(glass,0.14,0.18,opacity=0.36), roof=mat(roof,0.68), ground=mat([0.34,0.38,0.30]),
        accent=mat(accent), wood=mat(wood,0.58), greenery=mat([0.18,0.29,0.15]),
        water=mat([0.15,0.34,0.37],0.10,0.25,opacity=0.78), paving=mat([0.48,0.47,0.43]))


def volume(id,x,z,w,d,end,start=1,opened=False):
    v = dict(id=id,x=x,z=z,width=w,depth=d,start_floor=start,end_floor=end)
    if opened: v["facades"] = {f:Drawing.facade(True) for f in ("front","back","left","right")}
    return v


def european():
    b = Drawing("欧式别墅","橡庭庄园","法式古典比例、轴线柱廊、暖石线脚、深灰四坡屋面与前庭",2,3.7,0.6,
        [volume("main",-6,-4,12,12,2),volume("west",-10.5,-3,4.5,10,2),
         volume("east",6,-3,4.5,10,2),volume("portico",-3.2,-7.2,6.4,3.2,1,opened=True)],
        palette([0.87,0.82,0.71],[0.78,0.73,0.63],[0.16,0.18,0.21],[0.96,0.91,0.80]),
        dict(type="hip",height=2.0,thickness=0.18,overhang=0.55,
             volumes=[dict(volume="portico",type="gable",height=1.4,ridge_axis="z",overhang=0.4)]))
    for v in b.d["volumes"][:3]:
        for floor in (1,2):
            for face in ("front","back","left","right"):
                b.facade_windows(v["id"],face,floor,3 if v["id"] == "main" else 2,1.25,2.05,0.8,
                                 classical=True,entrance=v["id"] == "main" and floor == 1 and face == "front")
        for i,(y,h,extension) in enumerate(((0.72,.3,.16),(4.25,.22,.20),(7.72,.26,.27),(7.96,.16,.38))):
            b.ring(v["id"]+f"_moulding_{i}",v["x"]-extension,v["z"]-extension,
                   v["x"]+v["width"]+extension,v["z"]+v["depth"]+extension,y,.22,h)
        for x in (v["x"],v["x"]+v["width"]):
            for z in (v["z"],v["z"]+v["depth"]):
                b.repeat(f"quoin_{x}_{z}",[x,4.12,z],[.48,.3,.48],"y",20,.35)
    for i,x in enumerate((-2.65,-.9,.9,2.65)):
        b.column(f"ionic_{i}",x,-6.65,.6,4.22,.22,"ionic","accent")
        b.box(f"column_plinth_{i}",[x,.73,-6.65],[.62,.26,.62])
    b.ring("portico_entablature",-3.25,-7.1,3.25,-4.05,4.18,.38,.28)
    b.add("stair","entry_steps",form=dict(**{"from":[0,0,-9.4],"to":[0,.6,-7.2]},width=5.5,stepCount=4),material="floor")
    b.stair("hall_stair",-2.3,4.6,1,width=2.9,depth=5.1)
    # 门廊上方中央三角山花由真实屋顶表达，屋面上另设两个烟囱实体。
    for i,x in enumerate((-4.6,4.6)):
        b.box(f"chimney_shaft_{i}",[x,9.15,5.8],[.68,2.0,.78],"facade_primary")
        b.box(f"chimney_cap_{i}",[x,10.15,5.8],[.92,.18,1.0])
    b.box("estate_ground",[0,-.18,0],[31,.3,30],"ground")
    b.box("front_court",[0,-.015,-10.0],[18,.06,6.6],"paving")
    b.box("axial_walk",[0,.03,-12],[4,.12,7.0],"floor")
    for i,x in enumerate((-7.4,7.4)):
        b.box(f"parterre_border_{i}",[x,.18,-10],[4.2,.35,4.0],"accent")
        b.box(f"parterre_{i}",[x,.40,-10],[3.8,.28,3.6],"greenery")
    return b


def chinese():
    b = Drawing("新中式别墅","云汀合院","南低北高的围合庭院，白墙黛瓦、木格栅、深檐与镜水",2,3.35,.45,
        [volume("north",-9,6,18,6,2),volume("west",-9,-4,4.5,10,1),volume("east",4.5,-4,4.5,10,1),
         volume("gate",-2.2,-6.2,4.4,2.2,1,opened=True)],
        palette([.91,.89,.83],[.34,.30,.25],[.16,.18,.17],[.32,.30,.26],wood=(.29,.17,.095)),
        dict(type="chinese_curved",height=1.25,thickness=.16,overhang=.68,eaveCurveHeight=.28,
             volumes=[dict(volume="west",type="gable",ridge_axis="z",height=1.0),
                      dict(volume="east",type="gable",ridge_axis="z",height=1.0),
                      dict(volume="gate",height=.8,eaveCurveHeight=.22)]))
    for v in b.d["volumes"][:3]:
        for floor in range(1,v["end_floor"]+1):
            for face in ("front","back","left","right"):
                b.facade_windows(v["id"],face,floor,5 if v["id"] == "north" and face in {"front","back"} else 2,
                    1.45,2.25,.5,entrance=v["id"] == "north" and floor == 1 and face == "front")
        b.ring(v["id"]+"_stone_base",v["x"],v["z"],v["x"]+v["width"],v["z"]+v["depth"],.68,.26,.42)
        top=.45+v["end_floor"]*3.35
        b.ring(v["id"]+"_timber_fascia",v["x"]-.2,v["z"]-.2,v["x"]+v["width"]+.2,
               v["z"]+v["depth"]+.2,top-.18,.25,.28,"wood")
    for side,x in (("west",-4.38),("east",4.38)):
        b.repeat(side+"_courtyard_screen",[x,2.0,.3],[.09,2.65,.09],"z",16,.32,"wood")
        b.box(side+"_screen_top",[x,3.34,.3],[.17,.16,5.0],"wood")
    b.stair("north_stair",-5.8,8.65,1,direction="+x",width=4.8,depth=2.9)
    for x in (-1.9,1.9):
        b.column(f"gate_post_{x}",x,-5.85,.45,3.8,.13,"chinese_wooden","wood")
        b.column(f"gate_rear_{x}",x,-4.25,.45,3.8,.13,"chinese_wooden","wood")
    b.box("site",[0,-.17,3],[27,.28,29],"ground")
    b.box("courtyard_stone",[0,.23,1],[8.8,.18,9.5],"paving")
    b.box("reflecting_pool_rim",[-2.0,.37,1.2],[3.4,.22,5.6],"accent")
    b.box("reflecting_pool",[-2.0,.49,1.2],[3.05,.05,5.25],"water")
    b.repeat("stepping_stones",[.4,.45,.4],[1.1,.16,.65],"z",7,1.15,"floor")
    b.box("east_garden",[3.1,.4,1.7],[1.5,.24,5.0],"greenery")
    b.box("entrance_walk",[0,.2,-7.1],[2.6,.32,4.0],"floor")
    b.add("stair","gate_steps",form=dict(**{"from":[0,0,-9.1],"to":[0,.45,-7.1]},width=2.6,stepCount=3),material="floor")
    return b


def pavilion():
    b = Drawing("凉亭","听雨亭","八柱通透木构，双层重檐、檐下格栅、石台与水边坐凳",1,3.2,.6,
        [volume("pavilion",-3.5,-3.5,7,7,1,opened=True)],
        palette([.77,.72,.61],[.32,.16,.08],[.18,.22,.21],[.60,.54,.42],wood=(.34,.17,.075)),
        dict(type="chinese_pagoda",height=2.4,thickness=.16,overhang=1.0,tiers=2,
             tierHeight=1.3,shrinkFactor=.64,eaveOutset=.45))
    for side in (-1,1):
        for i,x in enumerate((-3.15,-1.65,1.65,3.15)):
            b.column(f"timber_post_{side}_{i}",x,side*3.15,.6,3.8,.16,"chinese_wooden","wood")
            b.box(f"stone_shoe_{side}_{i}",[x,.72,side*3.15],[.5,.24,.5],"accent")
    for i,y in enumerate((3.35,3.68)):
        b.ring(f"ring_beam_{i}",-3.25,-3.25,3.25,3.25,y,.24,.24,"wood")
    b.beam("ridge_cross_x",[-3.2,3.7,0],[3.2,3.7,0],.18,.24,"wood")
    b.beam("ridge_cross_z",[0,3.7,-3.2],[0,3.7,3.2],.18,.24,"wood")
    for side in (-1,1):
        b.railing(f"side_balustrade_{side}",[[side*3.2,.6,-2.7],[side*3.2,.6,3.2]])
        b.box(f"side_bench_{side}",[side*2.8,1.08,.5],[.45,.16,4.7],"wood")
        b.repeat(f"side_lattice_{side}",[side*3.22,3.05,0],[.07,.58,.07],"z",20,.29,"wood")
    b.railing("rear_balustrade",[[-3.2,.6,3.2],[3.2,.6,3.2]])
    b.repeat("rear_lattice",[0,3.05,3.22],[.07,.58,.07],"x",22,.28,"wood")
    b.box("stone_dais",[0,.22,0],[8.2,.44,8.2],"accent")
    b.box("dais_upper",[0,.48,0],[7.7,.16,7.7],"floor")
    b.add("stair","front_steps",form=dict(**{"from":[0,0,-5.8],"to":[0,.6,-3.85]},width=3.0,stepCount=4),material="floor")
    b.box("site",[0,-.17,0],[19,.3,19],"ground")
    b.box("water_edge",[0,-.005,6.2],[15,.05,3.8],"water")
    b.box("approach",[0,-.01,-6.5],[2.8,.08,5.3],"paving")
    b.add("light","pendant",[0,2.65,0],form=dict(body=[dict(shape="cylinder",radius=.28,height=.45)],
        color=[1,.77,.42],initiallyOn=True,lowIntensity=.5,highIntensity=1.3,distance=8),material="accent")
    return b


def office():
    b = Drawing("写字楼","澄光办公楼","十二层退台办公楼，双层通透基座、竖向幕墙格栅、空中露台与轻薄冠部",12,3.8,.3,
        [volume("podium",-14,-9,28,18,2),volume("tower",-10,-6,20,12,9,start=3),
         volume("crown",-8,-5,16,10,12,start=10)],
        palette([.76,.78,.77],[.50,.54,.55],[.36,.40,.41],[.64,.66,.64],glass=(.27,.46,.54)),
        dict(type="flat",height=0,thickness=.2,overhang=.2,
             volumes=[dict(volume="podium",type="none"),dict(volume="tower",type="none")]))
    b.d["envelope"] = dict(system="curtain_wall",curtain_wall=dict(grid_strategy="floor_and_bay_aligned"))
    for v in b.d["volumes"]:
        for floor in range(v["start_floor"],v["end_floor"]+1):
            y=.3+(floor-1)*3.8
            for face in ("front","back","left","right"):
                n = round((v["width"] if face in {"front","back"} else v["depth"])/2.6)
                if v["id"] == "podium" and face == "front": n=11
                b.facade_windows(v["id"],face,floor,n,(v["width"] if face in {"front","back"} else v["depth"])/n-.18,
                                 3.12,.3,entrance=floor == 1 and face == "front")
            b.ring(f"slab_edge_{floor}",v["x"]-.04,v["z"]-.04,v["x"]+v["width"]+.04,
                   v["z"]+v["depth"]+.04,y+3.63,.22,.24,"accent")
        bottom=.3+(v["start_floor"]-1)*3.8
        top=.3+v["end_floor"]*3.8
        for face,z in (("front",v["z"]-.22),("back",v["z"]+v["depth"]+.22)):
            n=round(v["width"]/2.5)+1
            b.repeat(f"{v['id']}_{face}_fins",[v["x"]+v["width"]/2,(bottom+top)/2,z],
                     [.11,top-bottom,.28],"x",n,v["width"]/(n-1),"frame")
    for floor in range(1,12): b.stair(f"core_stair_{floor}",-3.8,2.2,floor,width=3.0,depth=5.4)
    # 露台按体量差集分片，保留上层建筑占地，避免整块平台穿过上层空间。
    for label,y,outer,inner in (("podium",7.9,[-14,-9,14,9],[-10,-6,10,6]),
                               ("tower",34.5,[-10,-6,10,6],[-8,-5,8,5])):
        x0,z0,x1,z1=outer; a,c,d,e=inner
        for i,(l,f,r,k) in enumerate(((x0,z0,x1,c),(x0,e,x1,z1),(x0,c,a,e),(d,c,x1,e))):
            b.box(f"{label}_terrace_{i}",[(l+r)/2,y-.11,(f+k)/2],[r-l,.22,k-f],"floor")
        b.railing(label+"_terrace_rail",[[x0+.12,y,z0+.12],[x1-.12,y,z0+.12],
                  [x1-.12,y,z1-.12],[x0+.12,y,z1-.12],[x0+.12,y,z0+.12]],glass=True)
    # 电梯井是逐层显式挑空；轿厢/导轨由现有 elevator 构件生成。
    for layout in b.d["floor_layouts"]:
        layout["rooms"]=[dict(id=f"lift_void_{layout['floor']}",name="电梯井",void=True,
                             bounds=dict(x=1.0,z=1.0,width=2.5,depth=2.8))]
    b.add("elevator","passenger_lift",[2.25,.3,2.4],form=dict(dimensions=dict(width=2.25,depth=2.5,height=2.7),
          floorHeight=3.8,floorCount=12,frameMaterial="frame"),material="structure")
    b.box("entry_canopy",[0,3.4,-10.7],[9,.16,3.8],"frame")
    for x in (-4.2,4.2): b.column(f"canopy_post_{x}",x,-12,.05,3.4,.08,"modern","frame")
    b.box("forecourt",[0,-.12,0],[41,.22,32],"paving")
    b.box("entry_approach",[0,.1,-11],[7,.2,5.5],"floor")
    for i,x in enumerate((-11,11)):
        b.box(f"planter_{i}",[x,.27,-12],[6,.6,2.2],"accent")
        b.box(f"planting_{i}",[x,.61,-12],[5.7,.22,1.9],"greenery")
    b.ring("roof_parapet",-8.1,-5.1,8.1,5.1,46.25,.2,.65,"accent")
    return b


def compile_drawing(building):
    directory=OUT/building.folder
    directory.mkdir(parents=True,exist_ok=True)
    document=building.document()
    save(directory/"设计图纸.json",document.model_dump(mode="json",exclude_none=True))
    projection=project_drawing(document)
    d=document.decisions.model_dump(mode="json",exclude_none=True)
    geometry=projection.geometry_context
    bp=dict(meta=dict(version="1.0",type="building",name=building.name,author="Codex",
                     style=d["concept"]),materials=deepcopy(d["materials"]["definitions"]),
            geometry=dict(elements=[],components=[]))
    elements,components=bp["geometry"]["elements"],bp["geometry"]["components"]
    for wall in projection.projection_elements:
        elements.append({**{k:deepcopy(wall[k]) for k in ("type","id","from","to","thickness")},"material":"facade_primary"})
    for level in geometry["levels"]:
        for i,(x0,z0,x1,z1) in enumerate(level["floor_rectangles"]):
            elements.append(dict(type="floor",id=f"floor_L{level['index']}_{i}",
                **{"from":[x0,level["slab_bottom_y"],z0],"to":[x1,level["slab_bottom_y"],z1]},
                thickness=geometry["construction"]["slab_thickness"],material="floor"))
    hosts={wall["id"]:wall for wall in projection.projection_elements}
    context=dict(existing_blueprint=bp,drawing=d,construction=geometry["construction"],connection_targets={},
        stair_route_targets=geometry["stair_routes"],opening_hosts={})
    mappings={"building_body":[e["id"] for e in elements]}
    for marker in projection.component_markers:
        if marker["id"] == "building_body": continue
        design=marker["design"]
        if marker["type"] in {"door","window"}:
            context["opening_hosts"][marker["id"]]=dict(parentWall=marker["host"],
                **{"from":opening_target(marker,hosts[marker["host"]],design["size"]["width"],design["size"]["height"])})
        if design.get("repetition"):
            repeated=geometry["repetitions"][marker["id"]]
            row=dict(geometry=dict(elements=[dict(type="primitive",id=f"{marker['id']}_{i}",shape="box",
                position=p,dimensions=repeated["member_size"],**design["material_bindings"])
                for i,p in enumerate(repeated["positions"])],components=[]))
        else:
            row=realize_marker(marker,context)
        if row is None:
            kind=marker["type"]; form=deepcopy(design["form"])
            native=next((definition for definition in get_schema()["$defs"].values()
                         if definition.get("properties",{}).get("type",{}).get("const")==kind),None)
            if not native: raise ValueError(f"未实现的设计标记：{marker['id']} {kind}")
            entity=dict(type=kind,id=marker["id"],**form)
            if design.get("placement",{}).get("position") is not None and "position" in native["properties"]:
                entity["position"]=deepcopy(design["placement"]["position"])
            if kind == "primitive" and form.get("shape") == "box":
                entity["dimensions"]=[design["size"][k] for k in ("width","height","depth")]
            entity.update(design.get("material_bindings") or {})
            bucket=native["x-wild"]["target"]
            row=dict(geometry=dict(elements=[entity] if bucket == "elements" else [],
                                   components=[entity] if bucket == "components" else []))
        for bucket in ("elements","components"): bp["geometry"][bucket].extend(row["geometry"][bucket])
        mappings[marker["id"]]=[e["id"] for b in row["geometry"].values() for e in b]
    errors=sorted(jsonschema.Draft202012Validator(get_schema()).iter_errors(bp),key=lambda e:str(e.path))
    if errors: raise ValueError("\n".join(f"/{'/'.join(map(str,e.path))}: {e.message}" for e in errors[:12]))
    ids=[e["id"] for b in bp["geometry"].values() for e in b]
    if len(ids) != len(set(ids)): raise ValueError("产物 ID 重复")
    physical=expand_staircases(bp)
    for entity in [e for b in bp["geometry"].values() for e in b]:
        for key,value in entity.items():
            if (key == "material" or key.endswith("Material")) and value not in bp["materials"]:
                raise ValueError(f"{entity['id']}.{key} 引用不存在材质 {value}")
            if key.startswith("parent") and value not in {e["id"] for e in physical["geometry"]["elements"]}:
                raise ValueError(f"{entity['id']}.{key} 引用不存在宿主 {value}")
    filename=directory/(building.name+".wild")
    save(filename,bp)
    save(directory/"生成记录.json",dict(route=["Codex独立设计","项目DesignDocument契约","project_drawing",
        "程序实现设计标记/realize_marker","WILD装配及Schema校验"],plan_node=False,model_api_calls=0,
        compiler=Path(__file__).name,source_sha256=sha256((directory/"设计图纸.json").read_bytes()).hexdigest(),
        wild_sha256=sha256(filename.read_bytes()).hexdigest(),
        schema_errors=0,staircase_physical_expansion="completed",rendered=False,
        regression_tests_run=False,types=dict(Counter(e["type"] for b in bp["geometry"].values() for e in b)),
        counts={b:len(rows) for b,rows in bp["geometry"].items()},marker_entities=mappings,
        scope="按图纸确定性编译；未调用完整LangGraph，未运行回归测试或浏览器渲染"))
    print(json.dumps(dict(folder=building.folder,file=str(filename),counts={b:len(rows) for b,rows in bp["geometry"].items()}),ensure_ascii=False))


if __name__ == "__main__":
    for create in (european,chinese,pavilion,office): compile_drawing(create())
