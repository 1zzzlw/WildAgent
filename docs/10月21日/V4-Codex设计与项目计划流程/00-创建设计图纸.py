"""Codex 编写 V4 图纸；沿用本次 V1 栖庭布局以便比较，采用当前正式契约。"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent


def material(color, roughness=0.8, metallic=0, **extra):
    return dict(baseColor=color, roughness=roughness, metallic=metallic,
                albedo=0.8, lightingCondition="D65_noon", opacity=1, **extra)


def create():
    parts = []

    def component(kind, name, description, form, **kwargs):
        row = dict(type=kind, id=name, description=description, form=form, **kwargs)
        parts.append(row)
        return row

    def boxes(name, description, rows):
        # [中心X,Y,Z, 宽,高,深, 材料]；这是此图的明确构造分件选择。
        return component("assembly", name, description, dict(recipe="boxes", members=rows))

    def opening(kind, name, host, offset, width, height, sill=0, **form):
        details=dict(frameWidth=0.055,frameDepth=0.24,frameMaterial="frame",
                     interaction=dict(mode="slide" if kind=="window" else "swing",hingeSide="left"))
        if kind=="window":
            details.update(glassDepth=0.012,mullionWidth=0.028,glassMaterial="glass")
        else:
            details.update(leafDepth=0.045,leafMaterial="door",openingStyle="rectangular")
        return component(kind, name, "深木色细框真实洞口", {**details,**form},
                         host=host, placement=dict(offset=offset, sill_height=sill),
                         size=dict(width=width, height=height))

    blank = dict(bays=1, ground_pattern=["empty"], upper_pattern=["empty"])
    volumes = [
        dict(id="main", role="primary", x=0, z=5, width=16, depth=8, start_floor=1, end_floor=2),
        dict(id="west", role="elder_suite", x=0, z=0, width=5, depth=5, start_floor=1, end_floor=1,
             facades={"back": dict(bays=1, ground_pattern=["open"], upper_pattern=["empty"])}),
        dict(id="east", role="tea_studio", x=11, z=0, width=5, depth=5, start_floor=1, end_floor=1,
             facades={"back": dict(bays=1, ground_pattern=["open"], upper_pattern=["empty"])}),
    ]
    # 共用墙保留 main.front；两厢 back=open，不再重复造墙。
    for floor in (1, 2):
        front = f"wall_main_front_L{floor}"
        if floor == 1:
            for name, offset, width in [("elder_link", 1.8, 1.1), ("entry", 7.05, 1.9), ("tea_link", 13.1, 1.1)]:
                opening("door", name, front, offset, width, 2.6 if name == "entry" else 2.25,
                        doorStyle="double" if name == "entry" else "single")
            for i, x in enumerate((5.35, 9.25)):
                opening("window", f"hall_glass_{i}", front, x, 1.4, 2.5, 0.15,
                        verticalMullions=1, horizontalMullions=0)
        else:
            for i, x in enumerate((1.2, 5.4, 9.6, 13.2)):
                # 两端窗台高于厢房瓦屋脊，避免低窗被下层屋盖遮挡。
                opening("window", f"upper_south_{i}", front, x, 1.6 if i in (0, 3) else 2.6,
                        1.6 if i in (0, 3) else 2.1, 1.3 if i in (0, 3) else 0.7,
                        verticalMullions=2, horizontalMullions=1)
        for i, x in enumerate((1.3, 5.3, 9.3, 13.1)):
            opening("window", f"north_{floor}_{i}", f"wall_main_back_L{floor}", x, 2, 1.8, 0.85,
                    verticalMullions=2, horizontalMullions=1)
        for face in ("left", "right"):
            for i, along in enumerate((1.1, 5.1)):
                opening("window", f"side_{floor}_{face}_{i}", f"wall_main_{face}_L{floor}",
                        along, 1.8, 1.8, 0.85, verticalMullions=2, horizontalMullions=1)
    for wing in ("west", "east"):
        opening("window", wing+"_south", f"wall_{wing}_front_L1", 1, 3, 2.15, 0.55,
                verticalMullions=4, horizontalMullions=1)
        opening("window", wing+"_outer", f"wall_{wing}_{'left' if wing == 'west' else 'right'}_L1",
                1.1, 2.8, 1.8, 0.85, verticalMullions=3, horizontalMullions=1)
        opening("door", wing+"_court", f"wall_{wing}_{'right' if wing == 'west' else 'left'}_L1",
                1.5, 2, 2.5, doorStyle="double", leafMaterial="glass", leafRows=1)

    # 房间及隔墙均为设计输入；标高为楼面顶。
    layouts = []
    for f in (1, 2):
        walls = [dict(id=f"partition_{f}_west", **{"from": [5, 5], "to": [5, 13]}, thickness=0.16),
                 dict(id=f"partition_{f}_east", **{"from": [11, 5], "to": [11, 13]}, thickness=0.16)]
        rooms = [("west", "餐厨与备餐" if f == 1 else "西侧卧室套间", 0, 5, 5, 8),
                 ("center", "玄关、起居与餐厅" if f == 1 else "家庭厅与书房", 5, 5, 6, 8),
                 ("east", "客房与楼梯厅" if f == 1 else "东侧卧室与楼梯厅", 11, 5, 5, 8)]
        if f == 1:
            rooms += [("elder", "长辈房", 0, 0, 5, 5), ("tea", "茶室", 11, 0, 5, 5)]
        layouts.append(dict(floor=f, level=(f-1)*3.4, walls=walls,
                            rooms=[dict(id=f"room_{f}_{i}", name=n,
                                        bounds=dict(x=x, z=z, width=w, depth=d)) for i,n,x,z,w,d in rooms]))
        for side in ("west", "east"):
            opening("door", f"inside_{f}_{side}", f"partition_{f}_{side}", 1.05, 1.0, 2.25,
                    doorStyle="single")
    component("stair", "main_stair", "东侧U形双跑，10+10级；二层出口朝南接楼梯厅",
              dict(recipe="u_stair", shape="U", span_direction="+z", flights=2,
                   flight_width=1.2, landing_depth=1.2, rises=10, tread_depth=0.29,
                   landing_thickness=0.18, material="structure"),
              placement=dict(position=[12.65,1.7,10.05]), size=dict(width=2.6,depth=4.1,height=3.4),
              floor_connections=[dict(from_floor=1, to_floor=2)])
    component("railing", "stair_guard", "楼梯井二层三边防护与梯段扶手",
              dict(recipe="stair_guard", stair="main_stair",postSpacing=0.7,postRadius=0.022,
                   railRadius=0.025,railLevels=[0.1,0.5,1]), host="main_stair", size=dict(height=1.05))
    layouts[1]["rooms"][-1].update(name="东侧卧室前区",bounds=dict(x=11,z=5,width=5,depth=2.8))
    layouts[1]["rooms"].append(dict(id="stair_void",name="完整U形楼梯井（含两跑与半平台上空）",void=True,
                                     bounds=dict(x=11.35,z=8,width=2.6,depth=4.1)))
    for volume, rise, axis in [("main", 1.55, "x"), ("west", 1.0, "z"), ("east", 1.0, "z")]:
        component("roof", "roof_"+volume, "低坡灰瓦四坡屋面、深灰封檐、收敛屋脊",
                  dict(recipe="hip_roof", height=rise, thickness=0.16, ridgeAxis=axis,
                       overhang=0.5, ridge_width=0.14,ridge_height=0.12,fascia_height=0.16,fascia_depth=0.12), host=volume)

    # 白墙的石脚、细腰线、木檐底均由图纸中的分件尺寸控制。
    for v in volumes:
        x,z,w,d = (v[k] for k in ("x","z","width","depth"))
        cap = v["end_floor"]*3.4
        rows = []
        for face in ("front","back","left","right"):
            if v["id"] != "main" and face=="back":
                continue
            length=w if face in ("front","back") else d
            intervals=[(5,11)] if v["id"]=="main" and face=="front" else [(0,length)]
            for opening_row in parts:
                if (opening_row.get("host")==f"wall_{v['id']}_{face}_L1"
                        and opening_row.get("placement",{}).get("sill_height",0)<0.24):
                    a=opening_row["placement"]["offset"]-0.04
                    b=a+opening_row["size"]["width"]+0.08
                    intervals=[r for lo,hi in intervals for r in [(lo,min(hi,a)),(max(lo,b),hi)] if r[1]-r[0]>0.001]
            for a,b in intervals:
                c=(a+b)/2
                if face=="front": row=[x+c,0.12,z-0.15,b-a,0.24,0.08,"stone"]
                elif face=="back": row=[x+w-c,0.12,z+d+0.15,b-a,0.24,0.08,"stone"]
                elif face=="left": row=[x-0.15,0.12,z+d-c,0.08,0.24,b-a,"stone"]
                else: row=[x+w+0.15,0.12,z+c,0.08,0.24,b-a,"stone"]
                rows.append(row)
            if face=="front": row=[x+w/2,cap-0.16,z-0.15,w+0.3,0.18,0.16,"wood"]
            elif face=="back": row=[x+w/2,cap-0.16,z+d+0.15,w+0.3,0.18,0.16,"wood"]
            elif face=="left": row=[x-0.15,cap-0.16,z+d/2,0.16,0.18,d,"wood"]
            else: row=[x+w+0.15,cap-0.16,z+d/2,0.16,0.18,d,"wood"]
            rows.append(row)
        boxes("trim_"+v["id"], "石材勒脚与木色檐底线脚", rows)
    # 中央入口木门套；仅四边，保留真实洞口。
    boxes("entry_portal", "玄关深木门套与微挑檐", [
        [6.83,1.45,4.79,0.18,2.9,0.22,"wood"], [9.17,1.45,4.79,0.18,2.9,0.22,"wood"],
        [8,2.98,4.66,2.7,0.2,0.6,"wood"]])
    for x in (5.35, 10.65):
        screen=f"court_screen_{int(x)}"
        component("assembly", screen, "庭院等距竖向木格栅", dict(recipe="repeat"),
                  placement=dict(position=[x,1.45,0.55]),
                  repetition=dict(count=7,axis="x",spacing=0.12,member_size=[0.045,2.5,0.09]),
                  material_bindings=dict(material="wood"))
        boxes(screen+"_rails", "格栅上下横枨", [
            [x,0.2,0.55,0.9,0.12,0.12,"wood"], [x,2.75,0.55,0.9,0.12,0.12,"wood"]])
    # 场地铺装用 primitive，避免将景观面认作建筑主体楼板。
    boxes("site", "22×19米场地底盘与庭院铺装", [
        [8,-0.33,5.5,22,0.2,19,"ground"], [8,-0.11,2.5,6,0.2,5,"stone"],
        [8,-0.13,-1.5,2.2,0.18,3,"stone"]])
    rows = []
    for x in (6.0, 10.0):
        rows += [[x,0.16,2.55,0.9,0.32,2.7,"stone"], [x,0.34,2.55,0.72,0.08,2.5,"soil"]]
        rows += [[x,0.62,1.6+j*0.45,0.65,0.48,0.38,"green"] for j in range(5)]
    boxes("court_planters", "中轴两侧低矮绿植槽，中央通路净宽3.1米", rows)
    # 装饰水院、汀步、两侧简洁围墙；均无外部贴图依赖。
    boxes("front_garden", "浅水院、石汀步与低景墙", [
        [2.5,-0.1,-1.5,4.5,0.18,2.6,"stone"], [2.5,0.005,-1.5,4.2,0.03,2.3,"water"],
        [1.4,0.05,-1.5,0.65,0.1,0.65,"stone"], [2.5,0.05,-1.5,0.65,0.1,0.65,"stone"],
        [3.6,0.05,-1.5,0.65,0.1,0.65,"stone"],
        [-2,0.7,5.5,0.2,1.4,17,"facade_primary"], [18,0.7,5.5,0.2,1.4,17,"facade_primary"],
        [-2,1.45,5.5,0.34,0.1,17.2,"roof"], [18,1.45,5.5,0.34,0.1,17.2,"roof"]])

    colors = dict(
        facade_primary=material([0.92,0.90,0.84],0.9), structure=material([0.63,0.61,0.56]),
        floor=material([0.75,0.69,0.57]), frame=material([0.16,0.105,0.065],0.6),
        door=material([0.26,0.13,0.065],0.65), glass=material([0.53,0.69,0.71],0.12,
            transmission=0.86, ior=1.5, thickness=0.012, materialClass="glass", side="double"),
        roof=material([0.16,0.18,0.19],0.9), ground=material([0.44,0.48,0.39],0.98),
        accent=material([0.28,0.17,0.085],0.65))
    extra = dict(wood=colors["accent"], stone=material([0.57,0.56,0.51],0.9),
                 green=material([0.20,0.32,0.15],0.95), soil=material([0.16,0.12,0.08]),
                 water=material([0.20,0.38,0.39],0.1,0.15))
    decisions = dict(kind="architecture", concept="栖庭 V4 · 白墙灰瓦的两层新中式庭院别墅",
        massing=dict(shape="U",width=16,depth=13,floors=2,modeled_floors=2,
                     representation_mode="full",floor_height=3.4,symmetry=True),
        complexity=dict(level="detailed",min_volumes=3,min_detail_packages=0,
                        target_structural_elements=30,grid_bays=[4,2],reason="以庭院层次、屋檐、门窗构造与材质区分表达细节"),
        volumes=volumes, structural_grid=dict(system="wall_bearing",x_bays=4,z_bays=2),
        envelope=dict(system="solid_wall"), facades={f:dict(blank) for f in ("front","back","left","right")},
        roof=dict(type="hip",ridge_axis="x",overhang=0.5),
        circulation=dict(vertical_strategy="stair",description="U形双跑连接首层与二层；茶室与长辈房经共用墙门连通主楼",
            paths=[dict(id="entry_route",floor=1,points=[[8,0.9],[8,6.55]],width=1.2,height=2.2),
                   dict(id="stair_approach",floor=1,points=[[8,6.55],[12,6.55],[12,7.5]],width=0.8,height=2.1),
                   dict(id="upper_exit",floor=2,points=[[13.35,7.45],[13.35,6.55],[8,6.55]],width=0.8,height=2.1)]),
        floor_layouts=layouts, components=parts,
        construction=dict(wall_thickness=0.24,slab_thickness=0.22),
        materials=dict(keywords=["米白抹灰","炭灰瓦面","深木色细框","灰石勒脚"],
            resolved_plan=dict(concept="白、灰、木、石", palette=["米白","炭灰","深木色","灰石"],
                               roles=[dict(role=k,materialId=k,material=v) for k,v in colors.items()]),
            definitions=extra),
        design_intent=dict(goals=["三面围合的开敞庭院","两层主楼与单层厢房的高低屋面","真实洞口与可达楼梯"],
            assumptions=["用户未指定面积与层数，本次选择两层主楼与单层厢房","单位米，X向右、Y向上、南立面为Z减小方向", "建筑表达模型，不是施工图"],
            spatial_strategy="中央玄关连接主楼公共空间；西厢长辈房、东厢茶室各有庭院入口；二层两翼为卧室套间分区",
            composition="16×13米U形体量，中央6×5米露天庭院，最高点8.47米（含脊饰）",
            material_strategy="白墙灰瓦形成主调，以木檐、格栅、石脚与浅水院补充尺度层次",
            selected_systems=["原生wall/floor/door/window/roof/stair/railing","primitive组合细部"]),
        design_rationale=["厢房背面开敞，共用主楼南墙，避免共面重复", "两侧上层南窗高窗台避让厢房屋脊", "二层显式挑空覆盖两跑与半平台上空，井口三边护栏，南侧保留出口承接板", "所有景观与装饰均显式列入components"])
    document = dict(schema_version="design/1.0",design_id="qiting-villa-v4-20261021",session_id="codex-v4-20261021",
        revision=1,status="draft",created_at="2026-10-21T00:00:00+08:00",updated_at="2026-10-21T00:00:00+08:00",
        requirements=dict(source_request="创建一栋可渲染的新中式别墅，先按当前项目设计图纸契约创建设计，再编译WILD并记录流程。",
                          building_type="villa",profile="custom",style_intent=["新中式","白墙灰瓦","庭院","木格栅"]),
        decisions=decisions)
    return document


if __name__ == "__main__":
    import sys
    sys.path.insert(0,str(ROOT/"wild-server"))
    from app.design.contracts import DesignDocument
    document=DesignDocument.model_validate(create())
    (OUT/"02-栖庭V4-设计图纸-草稿.json").write_text(
        json.dumps(document.model_dump(mode="json",exclude_none=True),ensure_ascii=False,indent=2),encoding="utf-8")
    print(f"DesignDocument {document.schema_version}：{len(document.decisions.components)} 个显式构件")
