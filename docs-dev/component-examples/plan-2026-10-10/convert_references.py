"""本批参考资料对应的最小构件样例；--ingest 将已核验 JSON 整理为知识条目。"""
from __future__ import annotations

import json
import math
import sys
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
KB = ROOT / "wild-server/storage/knowledge_base"
SOURCES = {
    "masonry": ("CMHA 砌体基础详图", "https://www.cmha.org/resource/tek-05-03a/"),
    "landscape": ("Allan Block 墙顶、端部和转角", "https://allanblock.com/installation/commercial-installation/finishing-retaining-walls"),
    "window": ("Andersen 门窗立面与节点资料", "https://www.andersenwindows.com/for-professionals/architect/architectural-tools"),
    "bay": ("Andersen 30°／45° 凸窗组装图", "https://www.andersenwindows.com/-/media/Project/AndersenCorporation/AndersenWindows/AndersenWindows/files/technical-docs/installation-guide/installationguide-0005132.pdf"),
    "garage": ("Hörmann 分节车库门与安装剖面", "https://www.hoermann.com/fileadmin/_country/kataloge/pdf/86_912-Sectional_Garage_Doors_-0518-EN-UK.pdf"),
    "trim": ("Melton 檐口线脚图纸目录", "https://meltonclassics.com/products/cornices/fiberglass-cornices/designs/"),
    "pilaster": ("Melton 门套、壁柱和上部饰件图", "https://www.meltonclassics.com/files/melton-urethane-entry-systems.pdf"),
    "column": ("Melton Roman Ionic 柱式与分件尺寸图", "https://meltonclassics.com/products/architectural-columns/fiberglass-composite-columns/designs/"),
    "roof": ("RHEINZINK 屋面与建筑节点", "https://www.rheinzink.com/products/architectural-details/"),
    "dormer": ("RHEINZINK 老虎窗及屋面接口", "https://www.rheinzink.com/products/architectural-details/dormer/"),
    "awning": ("Canopia Aquila 雨棚组装图", "https://canopia.com/app/uploads/2022/03/600483_Palram-Canopia_Door-Awnings_Aquila_1x2_3x7_Assembly-Instructions.pdf"),
    "louvre": ("TROX WG 外墙通风百叶构造", "https://www.troxuk.co.uk/external-weather-louvres/wg-3a5581e60ae1533b"),
    "equipment": ("Daikin 外机支架与底座安装图", "https://www.daikin.eu/content/dam/document-library/installation-manuals/ac/split/RXP-L%2CARXP-L%2CRXF-A_3PDA512025-2_Installation%20Manual_Danish.pdf"),
    "railing": ("Q-railing 栏杆系统技术图纸入口", "https://q-railing.com/pl-pl/uslugi/materialy-do-pobrania/rysunki-cad/"),
    "iron": ("King Metals 双端卷花栏杆构件", "https://www.kingmetals.com/ECItemMainPage.aspx?ItemId=ITM-10273550"),
}


def material(color, roughness=0.7, metallic=0, **extra):
    return dict(baseColor=color, roughness=roughness, metallic=metallic,
                albedo=1, lightingCondition="D65_noon", **extra)


PALETTE = {
    "stone": material([0.72, 0.69, 0.62]),
    "plaster": material([0.9, 0.88, 0.81]),
    "metal": material([0.13, 0.15, 0.17], 0.4, 0.75),
    "wood": material([0.3, 0.18, 0.1]),
    "glass": material([0.85, 0.93, 0.98], 0.08, materialClass="glass", transmission=0.92, ior=1.5, opacity=1),
}


def box(id, position, dimensions, material="metal", **extra):
    return dict(type="primitive", id=id, shape="box", position=position,
                dimensions=dimensions, material=material, **extra)


def wall(id="host_wall", width=4, height=3.2, bottom=0, z=0, material="plaster"):
    return dict(type="wall", id=id, **{"from": [-width/2, bottom, z]},
                to=[width/2, bottom+height, z], thickness=0.24, material=material)


def floor(id, start, end, thickness=0.18):
    return dict(type="floor", id=id, **{"from": start}, to=end, thickness=thickness, material="stone")


def window(id, width, height, sill, along, parent="host_wall", **extra):
    return dict(type="window", id=id, parentWall=parent, **{"from": [along, sill, 0]},
                width=width, height=height, frameWidth=0.05,
                frameMaterial="metal", glassMaterial="glass", **extra)


def door(id, width=0.9, height=2.1, along=1.55, parent="host_wall", **extra):
    return dict(type="door", id=id, parentWall=parent, **{"from": [along, 0, 0]},
                width=width, height=height, frameMaterial="metal", leafMaterial="wood", **extra)


def scene(name, elements, components=()):
    refs = {value for row in [*elements, *components] for key, value in row.items()
            if key.endswith("Material") or key == "material"}
    return {"meta": {"version": "1.1", "type": "asset", "name": name},
            "geometry": {"elements": elements, "components": list(components)},
            "materials": {key: deepcopy(PALETTE[key]) for key in sorted(refs)}}


ROWS = []


def add(slug, name, group, entity, sources, explanation, elements, components=(), aliases=()):
    ROWS.append(dict(slug=slug, name=name, group=group, entity_type=entity,
                     sources=sources, explanation=explanation, aliases=list(aliases),
                     blueprint=scene(name, elements, components)))


body = [floor("body_slab", [-2, -0.18, -1.5], [2, -0.18, 1.5])]
for id, a, b in [("front", [-2,0,-1.5], [2,3,-1.5]), ("right", [2,0,-1.5], [2,3,1.5]),
                 ("back", [2,0,1.5], [-2,3,1.5]), ("left", [-2,0,1.5], [-2,3,-1.5])]:
    body.append(dict(type="wall", id=id, **{"from": a}, to=b, thickness=0.24, material="plaster"))
roof = dict(type="roof", id="main_roof", roofType="hip", span=4.4, depth=3.4,
            height=0.8, thickness=0.08, position=[0,3,0], material="metal")
add("building-body", "building_body", "envelope", "component", ["masonry"],
    "这是宿主骨架示例，不是别墅设计模板。楼板底标高 -0.18、厚 0.18，板顶为 0；四面 wall 接到标高 3。替换各端点和材料即可表达本次体量，不能自动加窗、屋顶或固定层数。", body)
add("solid-base", "实墙基座", "envelope", "wall", ["masonry"],
    "保留基础底座、基座墙与顶面压盖的分层表达。示例仅显示外观；墙宽、厚度、基座高度和压盖外挑可改，不从参考图移植承载或配筋要求。", [
    box("footing", [0,-0.175,0], [4.8,0.35,0.75], "stone"), wall(width=4.4,height=0.65,material="stone"),
    box("base_cap", [0,0.69,0], [4.6,0.08,0.55], "stone")])
add("solid-wall", "实墙", "envelope", "wall", ["masonry"],
    "实墙、实体墙属于同一原生 wall 用法，不因名称不同重复建模。from/to 同时表达水平端点及底顶标高，thickness 为墙厚；出现开口时另用宿主开口组件，不把窗形装饰贴在整块实墙上。", [wall()], aliases=["实体墙"])
add("landscape-low-wall", "景观矮墙", "envelope", "wall", ["landscape"],
    "用低 wall 和略外挑的顶盖表达矮墙。压顶底面与墙顶相接；端部、转角或分段高度依据本次设计调整。该 JSON 没有挡土计算或地下排水系统。", [wall(width=3,height=0.6,material="stone"),box("cap",[0,0.64,0],[3.1,0.08,0.35],"stone")])
add("garden-wall-junction", "庭院围墙接口", "envelope", "wall", ["landscape"],
    "这里的接口是两段围墙的端点及压顶关系，不是新增 WILD 类型。转角共享水平端点 [0,0,0]，高低墙可以独立取高度；接已有建筑时替换墙端点和材质，不自动复制第二面重合墙。", [
    dict(type="wall",id="wall_a",**{"from":[0,0,-1.5]},to=[0,2,0],thickness=0.24,material="stone"),
    dict(type="wall",id="wall_b",**{"from":[0,0,0]},to=[2,1,0],thickness=0.24,material="stone"),
    box("cap_b",[1,1.04,0],[2,0.08,0.34],"stone")])

for slug,name,width,height,sill,along,host_height,extra,explanation in [
    ("floor-window","落地窗",2.4,2.8,0.15,0.8,3.2,{},"低窗台、大玻璃与外围窗框构成落地窗。示例窗底为 0.15，可按真实门槛改为其他值；窗是 window，不能因落地就自动当门。"),
    ("double-height-window","通高窗",2.4,5.8,0.2,0.8,6.4,{"verticalMullions":1,"horizontalMullions":1},"通高由宿主与开口的实际高度表达。示例整段高墙承载高窗，中部横梃只是分格；不能以多层重合 window 冒充一个连续开口。"),
    ("operable-sash","开启扇",1.4,1.5,0.9,1.3,3.2,{"interaction":{"mode":"swing","hingeSide":"left","openAngle":55}},"开启语义使用 interaction，而不是新增 sash 类型。当前 window 交互编译会创建左右两扇；不能称作精确的单扇产品复制。开启角是示例取值。"),
    ("fixed-glazing","固定玻璃",1.8,1.6,0.9,1.1,3.2,{},"固定玻璃用不带 interaction 的 window。外围框和玻璃深度由宿主厚度内的默认值承担；无交互表示固定窗，不能附加虚构的 fixed 字段。"),
    ("small-window","小窗",0.65,0.8,1.2,1.675,3.2,{},"小窗只调整 opening 的尺寸和窗台，不形成新类型。保留真实宿主、框及玻璃，参数仍需放在墙长和墙高以内；小窗尺寸是示例，不是通用下限。"),
    ("high-window","高窗",1.4,0.55,2.25,1.3,3.2,{},"高窗指较高的窗底标高，不等于窗体很高。from[1] 为世界窗底，height 为开口高度；应同步调整宿主高度，不能把世界 X 误写进 from[0]。"),
    ("floor-window-group","落地窗组",3.2,2.7,0.2,0.4,3.2,{"verticalMullions":2},"这是一组等分玻璃的最小用法：一个 window 用两条竖梃得到三格。若需不同开启方式或不等宽扇，拆成多个互不重叠的 window，并保留各自沿墙坐标。"),
]:
    add(slug,name,"glazing","window",["window"],explanation,[wall(height=host_height)],
        [window("sample_window",width,height,sill,along,**extra)])
add("bay-window", "凸窗", "glazing", "bay_window", ["bay"],
    "参考图的前窗、侧窗及上下平台保留为凸窗的分件意识。当前 bay_window 为矩形外挑盒式窗体，projectionDepth 是外挑深度；不声称复现原图 30°／45° 的斜侧窗。该斜角造型需改用多个墙窗或 primitive。", [wall()], [
    dict(type="bay_window",id="bay",parentWall="host_wall",**{"from":[0.8,0.8,0]},width=2.4,height=1.7,projectionDepth=0.65,frameWidth=0.06,frameMaterial="metal",glassMaterial="glass")])

for slug,name,width,height,along,extra,explanation in [
    ("side-door","侧门",0.95,2.1,1.525,{"interaction":{"mode":"swing","hingeSide":"left","openAngle":80}},"侧门是单扇 door 的安装位置选择。复用真正宿主墙和沿墙起点，不自动生成旁边的小窗；interaction 提供侧铰平开语义。"),
    ("storage-door","储藏间门",0.8,2.0,1.6,{"interaction":{"mode":"swing","hingeSide":"right","openAngle":70}},"储藏间门仍是 door，尺寸、门扇材料与铰链侧按本次空间决定。此示例不附带不存在的储藏间房间结构，安装时替换为本次室内墙宿主。"),
    ("glass-sliding-door","大面积玻璃移门",3,2.4,0.5,{"doorStyle":"double","leafRows":1,"interaction":{"mode":"slide","openDistance":1.3}},"玻璃移门使用 doorStyle=double、玻璃门扇材料和 slide。滑移示例不表示多轨折叠或完全收入墙内；将门旁滑移空间、玻璃和框料一起核对。"),
    ("sectional-garage-door","车库门",3,2.2,0.5,{"leafRows":5,"interaction":{"mode":"lift","openDistance":2.2}},"保留分节门面及提升语义。当前 lift 把门扇整体竖直上移，不沿 Hörmann 的弯曲轨道逐节翻转；不能用示例宣称真实分节轨道仿真。宿主高 4.6 为提升留出净空，不把该高度推广到所有车库。"),
]:
    c=door("sample_door",width,height,along,**extra)
    if slug=="glass-sliding-door":c["leafMaterial"]="glass"
    if slug=="sectional-garage-door":c["leafMaterial"]="metal"
    add(slug,name,"entrance","door",["garage" if "garage" in slug else "window"],explanation,
        [wall(height=4.6 if "garage" in slug else 3.2)],[c])
vestibule=[wall("inner_wall",width=3.4,height=2.8),wall("outer_wall",width=3.4,height=2.8,z=-1.5),
           floor("vestibule_slab",[-1.7,-0.15,-1.5],[1.7,-0.15,0],0.15),
           box("vestibule_roof",[0,2.9,-0.75],[3.6,0.2,1.7],"stone")]
for id,x in [("left_wall",-1.7),("right_wall",1.7)]:
    vestibule.append(dict(type="wall",id=id,**{"from":[x,0,-1.5]},to=[x,2.8,0],thickness=0.24,material="plaster"))
add("entrance-vestibule","主入口门斗","entrance","door",["window","pilaster"],
    "门斗是有深度的入口空间，不能只画装饰门套。示例包含前后两道门、侧壁、楼板和顶盖；若本次只要开放门廊，应删去前道门和相应围护并重新设计，不机械保留封闭门斗。此空间组合是本项目示例设计，来源仅用于门窗和门套分件参考。",vestibule,[
    door("inner_door",1.6,2.35,0.9,parent="inner_wall",doorStyle="double",interaction={"mode":"swing","hingeSide":"left","openAngle":75}),
    door("outer_door",1.8,2.35,0.8,parent="outer_wall",doorStyle="double",interaction={"mode":"swing","hingeSide":"right","openAngle":75}),
    window("side_light",0.95,1.9,0.5,0.25,parent="left_wall")])
gate=[box("pier_left",[-1.65,0.95,0],[0.3,1.9,0.3],"stone"),box("pier_right",[1.65,0.95,0],[0.3,1.9,0.3],"stone")]
for n,cx in enumerate([-0.725,0.725]):
    for y in [0.15,1.65]:gate.append(box(f"gate_{n}_rail_{y}",[cx,y,0],[1.42,0.045,0.05]))
    for j in range(7):gate.append(box(f"gate_{n}_bar_{j}",[cx-0.6+j*0.2,0.9,0],[0.025,1.5,0.025]))
add("garden-gate","庭院门","entrance","door",["iron"],
    "用两座门柱、两组边框与竖条表达静态镂空庭院门，保留两扇间缝隙。primitive 组合没有自动铰链或 door 交互；若要交互可改原生 door 并说明其实体门扇与镂空造型的差别。这里不复制来源产品的尺寸或规范声明。",gate)

balcony_wall=wall(height=4)
add("balcony-panel","阳台栏板","balcony","balcony",["railing"],
    "采用 balcony 生成悬挑板，railingEnabled=false 后由独立 panel 栏杆接管三边。宿主后方楼板确定内外方向；沿墙 from[0]=0.5，板顶 from[1]=3.2，墙外表面 z=-0.12，因此外边 z=-1.37。更换宿主后重算世界路径，不能只改板宽。",[
    balcony_wall,floor("interior_slab",[-2,3.02,0],[2,3.02,2],0.18)], [
    dict(type="balcony",id="balcony",parentWall="host_wall",**{"from":[0.5,3.2,0]},width=3,depth=1.25,slabThickness=0.18,railingEnabled=False,material="stone"),
    dict(type="railing",id="panel_guard",path=[[-1.5,3.2,-0.12],[-1.5,3.2,-1.37],[1.5,3.2,-1.37],[1.5,3.2,-0.12]],height=1.05,postSpacing=0.75,infillType="panel",infillThickness=0.06,infillMaterial="stone",material="metal")])
add("terrace-railing","露台栏杆","balcony","railing",["railing"],
    "楼板底标高为 -0.18、顶面为 0，栏杆世界路径从板顶起。三边栏杆由连续 path 与 glass 填充构成；没有 parentFloor 时 path 是世界坐标，不把这些点当沿墙坐标。栏杆高度及立柱间距是本次示例值。",[
    floor("terrace_slab",[-1.5,-0.18,0],[1.5,-0.18,1.8])],[
    dict(type="railing",id="glass_guard",path=[[-1.5,0,0],[-1.5,0,1.8],[1.5,0,1.8],[1.5,0,0]],height=1.1,postSpacing=1,infillType="glass",infillThickness=0.012,infillMaterial="glass",material="metal")])
platform=[wall(height=3.4),floor("equipment_slab",[-1,2.08,-0.12],[1,2.08,-1.12],0.12)]
for n,x in enumerate([-0.7,0.7]):
    platform.extend([box(f"bracket_{n}",[x,2.04,-0.62],[0.08,0.08,1]),box(f"anchor_{n}",[x,1.7,-0.15],[0.08,0.72,0.06])])
add("equipment-platform","设备平台","balcony","component",["equipment"],
    "以悬挑楼板和两组墙支架表达设备平台。floor.from[1]=2.08、厚度 0.12，故板顶 2.2；支架水平臂顶面接板底。安装原点、平台外挑、支架位置及设备净空由本次需求给出，不套用产品图的气候或载荷要求。",platform)
equipment=[box("equipment_base",[0,0.06,0],[1.2,0.12,0.65],"stone"),box("condenser",[0,0.445,0],[0.95,0.65,0.3],"plaster"),
           dict(type="primitive",id="fan_face",shape="cylinder",position=[0,0.45,-0.16],rotation=[math.pi/2,0,0],radius=0.22,height=0.02,segments=24,material="metal")]
add("ac-position","空调机位","balcony","component",["equipment"],
    "机位示例包含底座、外机外壳和前侧风扇外观；底座顶为 0.12，机壳底为 0.12。安装到设备平台时将这组世界坐标平移到板顶，并保留方案要求的通风空间。该几何不表示制冷、排水、风量或风扇动画。",equipment)

louvres=[]
for id,p,d in [("top",[0,1,0],[1.2,0.05,0.18]),("bottom",[0,0,0],[1.2,0.05,0.18]),
               ("left",[-0.575,0.5,0],[0.05,1,0.18]),("right",[0.575,0.5,0],[0.05,1,0.18])]:
    louvres.append(box(id,p,d))
for i in range(8):louvres.append(box(f"blade_{i}",[0,0.105+i*0.11,0],[1.1,0.025,0.14],rotation=[math.radians(35),0,0]))
add("ventilation-louvre","通风百叶","equipment","window",["louvre"],
    "TROX 图纸的边框与倾斜叶片保留为独立几何，不用窗棂冒充叶片。此模块用 primitive.box 旋转出八片固定叶片；rotation 为弧度。数量、间距、倾角和框深可改。安装到实墙时需要另外落实洞口；没有通风计算、叶片联动或防雨认证。",louvres,aliases=["百叶叶片"])
add("exhaust-outlet","排风口","equipment","component",["louvre"],
    "排风口复用边框及固定百叶，后方圆筒只显示短管外形；cylinder 不是空心风管。接外墙或设备平台时先确定接口和实际开孔，不能靠把模块贴在未开孔的实墙上宣称通风已连通。",deepcopy(louvres)+[
    dict(type="primitive",id="rear_stub",shape="cylinder",position=[0,0.5,0.18],rotation=[math.pi/2,0,0],radius=0.32,height=0.2,segments=24,material="metal")])

add("hip-roof","roof","roof","roof",["roof"],
    "roof 是原生元素，这里展示四坡屋面落在宿主墙顶标高 3。position 是中心与支承标高，span/depth 为屋面覆盖尺寸，height 为屋面上表面从檐口到屋脊的高差。多体量按各体量独立覆盖，不把此矩形示例当整栋固定屋顶。",deepcopy(body)+[roof],aliases=["屋顶"])
add("parapet","女儿墙","roof","wall",["roof"],
    "平屋面边沿采用两段相交的低 wall 与可选压顶。floor 底 2.82、厚 0.18，顶为 3；女儿墙底接 3。其高度、覆盖边数及压顶外挑留给图纸，不把示例高度当规范，也不自动补满未选的四边。",[
    floor("roof_slab",[-2,2.82,0],[2,2.82,2],0.18),wall("parapet_front",height=0.9,bottom=3),
    dict(type="wall",id="parapet_side",**{"from":[-2,3,0]},to=[-2,3.9,2],thickness=0.24,material="plaster"),
    box("coping_front",[0,3.94,0],[4.1,0.08,0.34],"metal")])
add("eave-soffit","屋檐下悬","roof","roof",["roof"],
    "这里按檐下封板及下挂封檐条解释“屋檐下悬”。封板只占墙外至屋面边缘的窄带，不以整块板堵住阁楼；示例展示前檐，其他边需要按本次覆盖关系补齐。若用户指悬挑构架，应按原图重新选构造，而不是仅改这个名称。",deepcopy(body)+[deepcopy(roof),
    box("front_soffit",[0,2.98,-1.6],[4.4,0.04,0.2],"plaster"),box("front_fascia",[0,2.93,-1.68],[4.4,0.14,0.08],"plaster")])
add("decorative-cornice","装饰檐口","roof","cornice",["trim"],
    "截面线脚通过 cornice 沿墙顶扫掠表达，适合腰线或屋檐装饰。profile 是二维截面，path 是世界路径；改变走向时需检查截面朝向，转角共享端点。此阶梯形截面是自行简化的示例，不是 Melton 产品尺寸复刻，也不增加不存在的齿饰字段。",[wall()],[
    dict(type="cornice",id="cornice",path=[[-2,3.2,0],[2,3.2,0]],profile=[[0,0],[0.18,0],[0.18,0.08],[0.1,0.08],[0.1,0.18],[0,0.18]],closedProfile=True,material="stone")])
add("decorative-pilaster","装饰壁柱","roof","column",["pilaster"],
    "壁柱是贴墙的矩形浅浮雕，而非独立圆柱。使用 primitive.box 组合柱脚、柱身、柱头，后侧略嵌入墙面；若设计要槽纹可再组合细条。保留壁柱与 host_wall 的位置关系，不把没有的 parentWall 属性写进 primitive。",[
    wall(),box("pilaster_base",[0,0.1,-0.16],[0.45,0.2,0.2],"stone"),box("pilaster_shaft",[0,1.4,-0.15],[0.25,2.4,0.12],"stone"),
    box("pilaster_cap",[0,2.68,-0.16],[0.5,0.16,0.25],"stone")])
add("roman-column","罗马柱","roof","column",["column"],
    "原生 column 放入 elements，用 base、height、上下半径和 style 描述独立柱。ionic 是当前支持的样式枚举；引擎为简化表达，不以 style 名称宣称历史柱式细部完全复原。需要额外柱头饰件时另用 primitive，柱高和柱数由本次方案决定。",[
    dict(type="column",id="roman_column",base=[0,0,0],height=3,bottomRadius=0.23,topRadius=0.19,style="ionic",flutes=16,entasis=0.015,material="stone")])
dormer=[floor("dormer_base",[-0.7,1.9,-0.7],[0.7,1.9,0.7],0.1),wall("dormer_front",width=1.4,height=1.2,bottom=2,z=-0.7)]
for id,x in [("dormer_left",-0.7),("dormer_right",0.7)]:
    dormer.append(dict(type="wall",id=id,**{"from":[x,2,-0.7]},to=[x,3.2,0.7],thickness=0.12,material="metal"))
dormer.append(dict(type="roof",id="dormer_roof",roofType="gable",span=1.65,depth=1.8,height=0.5,thickness=0.05,position=[0,3.2,0],material="metal"))
add("gable-dormer","老虎窗","roof","roof",["dormer"],
    "老虎窗由凸出屋面的前窗、两侧围护和自身小屋顶组成，区别于直接嵌在坡面里的天窗。这里给出自选双坡造型，官方照片用于侧壁和屋面接口参考。原生主屋顶没有任意开孔字段：此独立样例没有主屋面；装到整栋时要按交线分块主屋面，不能直接叠在完整 hip/gable 屋面上。",dormer,[
    window("dormer_window",0.9,0.9,2.2,0.25,parent="dormer_front")])
awning=[wall(height=3.1),box("awning_panel",[0,2.565,-0.62],[2.1,0.03,1],"glass")]
for n,x in enumerate([-0.75,0.75]):
    awning.append(dict(type="primitive",id=f"curved_bracket_{n}",shape="profile_sweep",profile=[[-0.02,-0.02],[0.02,-0.02],[0.02,0.02],[-0.02,0.02]],path=[[x,1.9,-0.12],[x,2.12,-0.3],[x,2.35,-0.55],[x,2.5,-0.85],[x,2.55,-1.1]],closedProfile=True,material="metal"))
    awning.append(box(f"side_frame_{n}",[x,2.575,-0.62],[0.04,0.08,1.04]))
add("framed-awning","雨棚构造","roof","canopy",["awning"],
    "参考装配图保留透明顶板、两侧支承和墙连接的组合。顶板用 glass 材料，曲折支架用 profile_sweep；这组原语用世界坐标，不能套 canopy.from 的沿墙坐标。原图的精确曲率、密封件和螺栓被简化，安装需替换墙位置并同步支架末端与板底。",awning)

iron=[box("iron_top",[0,1.1,0],[2.4,0.04,0.04]),box("iron_bottom",[0,0.08,0],[2.4,0.04,0.04])]
for n,x in enumerate([-1.15,-0.6,0,0.6,1.15]):iron.append(box(f"iron_bar_{n}",[x,0.59,0],[0.025,1.02,0.025]))
scroll=[[0.02,0.32,0],[0.18,0.2,0],[0.28,0.29,0],[0.24,0.4,0],[0.12,0.42,0],[0.08,0.36,0],[0.12,0.3,0]]
iron.append(dict(type="primitive",id="lower_scroll",shape="profile_sweep",profile=[[-0.008,-0.008],[0.008,-0.008],[0.008,0.008],[-0.008,0.008]],path=scroll,closedProfile=True,material="metal"))
iron.append(dict(type="primitive",id="upper_scroll",shape="profile_sweep",profile=[[-0.008,-0.008],[0.008,-0.008],[0.008,0.008],[-0.008,0.008]],path=[[-x,1.1-y,z] for x,y,z in scroll],closedProfile=True,material="metal"))
add("ornamental-iron-railing","铁艺栏杆","balcony","railing",["iron"],
    "保留顶部扶手、下横杆、竖条和两端卷花。卷花使用小方截面沿折线扫掠，路径点越密轮廓越平滑；不是把普通两道横杆称为铁艺。安装在露台时整体平移并按实际长度重复所选竖条。这里只表达静态外观，没有来源产品的受力或规范声明。",iron)

SOURCES.update({
    "interior_sofa": ("Herman Miller Wireframe 沙发立面与尺寸图，第 1 页", "https://www.hermanmiller.com/content/dam/hermanmiller/documents/product_literature/product_sheets/emea/wireframe_sofa_product_sheet_en-gb.pdf"),
    "interior_chair": ("Herman Miller Eames 餐椅图纸，第 2 页", "https://www.hermanmiller.com/content/dam/hermanmiller/documents/product_literature/product_sheets/eames_molded_plastic_dining_chair_product_sheet.pdf"),
    "interior_table": ("Herman Miller Eames 桌台图纸，第 1 页", "https://www.hermanmiller.com/content/dam/hermanmiller/documents/product_literature/product_sheets/eames_occasional_table_product_sheet.pdf"),
    "interior_bed": ("IKEA MALM 床架装配图，第 1 页", "https://www.ikea.com/us/en/assembly_instructions/malm-storage-bed-white__AA-2055625-9-100.pdf"),
    "interior_shelf": ("IKEA BILLY 书架装配图，第 1 页", "https://www.ikea.com/us/en/assembly_instructions/billy-bookcase-white__AA-2289105-4-100.pdf"),
    "interior_cabinet": ("IKEA METOD 柜体装配图，第 1 页", "https://www.ikea.com/de/de/assembly_instructions/metod-korpus-wandschrank-weiss__AA-2238433-5-2.pdf"),
    "interior_basin": ("Duravit Vero 台盆平面图，第 1 页", "https://csassets.duravit.com/1/2/Duravit_TD_1266386.pdf"),
    "interior_toilet": ("Duravit 马桶侧面尺寸图，第 1 页", "https://csassets.duravit.com/2/9/Duravit_TD_2912316.pdf"),
})
PALETTE.update(fabric=material([0.53, 0.58, 0.65], 0.9), ceramic=material([0.94, 0.94, 0.92], 0.2))


def furniture(id, subtype, position, width, depth, height, material="wood", angle=0):
    return dict(type="furniture", id=id, subtype=subtype, position=position,
                rotation=[0, angle, 0], dimensions=dict(width=width, depth=depth, height=height), material=material)


add("sofa", "沙发", "furniture", "furniture", ["interior_sofa"],
    "原生 furniture.sofa 表达底座、靠背、扶手与坐垫，正面朝 +Z，position 是底面中心；落地 Y 取所在楼板顶标高。示例宽 2.3、深 0.9、高 0.8 为自选米制设计值。来源的钢丝外框与软包曲面没有在本原生样例中复原，需要精确分件时改用 primitive 组合；不能把此简化沙发称为原厂模型。",
    [furniture("sofa", "sofa", [0,0,0], 2.3,0.9,0.8,"fabric")], aliases=["couch", "三人沙发"])
add("coffee-table", "茶几", "furniture", "furniture", ["interior_table"],
    "用 furniture.table 将桌面与腿组合成低桌。position 是底面中心，height 控制桌面总高；这里用矩形四腿近似，来源的圆桌与中心支脚仅为桌面、支承关系参考，未照搬产品结构。宽深、高度、材料与离沙发距离由图纸决定。",
    [furniture("coffee_table", "table", [0,0,0],1.1,0.6,0.42)], aliases=["coffee table", "矮桌"])
dining = [furniture("dining_table", "table", [0,0,0],1.6,0.85,0.75)]
for n,(x,z,angle) in enumerate([(-0.45,-0.7,0),(0.45,-0.7,0),(-0.45,0.7,math.pi),(0.45,0.7,math.pi)]):
    dining.append(furniture(f"dining_chair_{n}", "chair",[x,0,z],0.45,0.45,0.85,angle=angle))
add("dining-table-chairs", "餐桌椅", "furniture", "furniture", ["interior_chair","interior_table"],
    "餐桌和每把椅子分别写为 furniture 元素；椅背在 -Z，正面 +Z，rotation[1] 为弧度。两侧椅子转向桌边；示例椅子靠近桌边，正式安装仍要按房间留出拉椅与通行空间。餐椅是盒体近似，没有来源的曲面坐背或金属支脚造型。人数、布置和各尺寸为设计变量，不要求所有餐厅四椅。",
    dining, aliases=["dining set", "dining table chairs", "餐桌", "dining_table"])
add("bed", "床", "furniture", "furniture", ["interior_bed"],
    "furniture.bed 表达床架、床垫与床头板，床头在 -Z；height 是床头总高，不能当床垫离地高度。position 取底面中心和楼板顶标高；需要明确床垫、床头或床架不同材质/高度时拆为 primitive，不虚构 mattressHeight。来源的储物举升机构与排骨架未实现，示例尺寸自选。",
    [furniture("bed", "bed", [0,0,0],1.8,2.0,1.05)], aliases=["双人床", "double bed"])
add("wardrobe", "衣柜", "furniture", "furniture", ["interior_cabinet"],
    "furniture.wardrobe 为柜身、前侧双门和踢脚的简化整体，正面 +Z，position 是底面中心。来源只提供柜体板件参考，不是衣柜产品复刻；门为静态几何，不具备开门交互。宽深高与位置由图纸给定；要开放挂衣区或多门分格可组合 primitive，不添加未知 cabinetDoors 字段。",
    [furniture("wardrobe", "wardrobe", [0,0,0],1.8,0.6,2.2)], aliases=["closet"])
add("bookshelf", "书架", "furniture", "furniture", ["interior_shelf"],
    "原生 furniture.bookshelf 含侧板、背板、上下板及两块中间隔板；不能凭 dimensions 声称实现来源全部层数。此例保留开放书架的板件关系，正面 +Z。需要更多层、独立材质或异形柜时用多个 primitive.box 表达，书本不是默认实体。",
    [furniture("bookshelf", "bookshelf", [0,0,0],0.9,0.3,1.8)], aliases=["bookcase", "书柜"])
add("nightstand", "床头柜", "furniture", "furniture", ["interior_cabinet"],
    "furniture.nightstand 表达台面、低柜与静态抽屉分缝。position 取楼板顶，不挂 parentWall；柜前朝 +Z。来源的板件关系缩减为独立低柜，抽屉不可拉动；本例不自动配置床或台灯。数量、宽深高与床边距离由本次设计决定。",
    [furniture("nightstand", "nightstand", [0,0,0],0.5,0.45,0.5)], aliases=["bedside table"])
add("tv-cabinet", "电视柜", "furniture", "furniture", ["interior_cabinet"],
    "furniture.tv_cabinet 表达低柜台面、两侧柜体与中央设备区；柜前 +Z，底部锚点放在楼板顶。来源只用于柜体分件参考，本例没有电视屏幕或可操作设备。需要屏幕时另组合薄 primitive.box；整体长度、高度和分格应从图纸确定。",
    [furniture("tv_cabinet", "tv_cabinet", [0,0,0],1.8,0.4,0.5)], aliases=["tv cabinet", "电视机柜"])
add("desk-chair", "书桌椅", "furniture", "furniture", ["interior_table","interior_chair"],
    "书桌与座椅分别用 furniture.table/chair，椅子正面转向桌子。示例椅子在桌前 +Z 并旋转 π 弧度，底面 Y 相同。来源提供桌面支承与椅背参考，示例为自选矩形桌、简化椅；没有显示器和抽屉。通行、桌椅距离及房间朝向由本次图纸调整。",
    [furniture("desk","table",[0,0,0],1.2,0.6,0.75),furniture("desk_chair","chair",[0,0,0.65],0.45,0.45,0.85,angle=math.pi)], aliases=["desk", "书桌", "办公桌", "desk chair"])
kitchen = [box("cabinet_body",[0,0.425,0],[1.8,0.7,0.6],"wood"),
           box("cabinet_plinth",[0,0.075,-0.025],[1.74,0.15,0.52],"wood"),
           box("countertop",[0,0.8,0],[1.86,0.05,0.64],"stone")]
for n,x in enumerate([-0.6,0,0.6]):
    kitchen += [box(f"cabinet_door_{n}",[x,0.43,0.312],[0.588,0.68,0.024],"wood"),
                box(f"cabinet_handle_{n}",[x,0.68,0.34],[0.12,0.02,0.03])]
add("kitchen-cabinet", "橱柜", "interior", "furniture", ["interior_cabinet"],
    "用 primitive.box 分别表达柜体、踢脚、三扇门板、把手与台面；世界坐标 position 是各盒体中心，板件底部不能直接把 Y 写为 0。来源是吊柜板件图，本例转换为自选落地橱柜，不照搬安装高度。门板在 +Z 为正面；没有抽屉/开门动作、厨房设备或水槽。柜体尺寸、门数、台面与材质分层均可修改。",
    kitchen, aliases=["kitchen cabinet", "厨房橱柜", "厨柜"])
basin = [box("basin_bottom",[0,0.735,0],[0.6,0.03,0.47],"ceramic"),
         box("basin_front",[0,0.81,0.2175],[0.6,0.12,0.035],"ceramic"),
         box("basin_back",[0,0.81,-0.2175],[0.6,0.12,0.035],"ceramic"),
         box("basin_left",[-0.2825,0.81,0],[0.035,0.12,0.4],"ceramic"),
         box("basin_right",[0.2825,0.81,0],[0.035,0.12,0.4],"ceramic"),
         box("basin_pedestal",[0,0.36,-0.05],[0.18,0.72,0.2],"ceramic"),
         box("faucet_stem",[0,0.945,-0.21],[0.035,0.15,0.035]),
         box("faucet_spout",[0,1.015,-0.155],[0.035,0.035,0.11])]
add("washbasin", "洗手盆", "interior", "furniture", ["interior_basin"],
    "用底板和四侧板形成有开口的盆体，避免整块实心箱体；另组合自选支座与水龙头。来源平面图标注宽 600、深 470 mm，转换为 0.6、0.47 m；其余高度、板厚、支座与龙头是本项目示例假设，不是厂家安装规范。primitive.position 是分件几何中心，所有片段需一起平移到安装位置。盆的圆角、排水和曲面仅近似表达，没有给排水模拟。",
    basin, aliases=["wash basin", "洗脸盆", "台盆", "lavatory"])
toilet = [box("toilet_pedestal",[0,0.18,0.04],[0.24,0.36,0.3],"ceramic"),
          box("toilet_tank",[0,0.52,-0.2],[0.36,0.4,0.18],"ceramic"),
          box("toilet_tank_lid",[0,0.73,-0.2],[0.38,0.03,0.2],"ceramic")]
rim = [[0.19*math.cos(i*math.tau/24),0.41,0.05+0.25*math.sin(i*math.tau/24)] for i in range(25)]
toilet.append(dict(type="primitive",id="toilet_bowl_rim",shape="profile_sweep",
                  profile=[[-0.035,-0.02],[0.035,-0.02],[0.035,0.02],[-0.035,0.02]],
                  path=rim,closedProfile=True,material="ceramic"))
for n,x in enumerate([-0.14,0.14]):
    toilet.append(box(f"toilet_bowl_side_{n}",[x,0.31,0.08],[0.06,0.16,0.36],"ceramic"))
add("toilet", "马桶", "interior", "furniture", ["interior_toilet"],
    "primitive 组合底座、盆侧、水箱、箱盖与椭圆开口盆沿，保留侧视图中水箱在后、盆口在前的关系。盆沿用闭合 profile_sweep，未用实心盒封死盆口；模型不具备冲水或盖板开合。来源标注高 730、坐高 410 mm，对应约 0.73、0.41 m；横向宽度与椭圆轮廓为自选近似，不宣称复刻内部水封。安装时整体平移/旋转各分件，不能给 primitive 添加 toilet 类型。",
    toilet, aliases=["WC", "坐便器"])

NAME_ALIASES = {
    "building-body": ["建筑主体", "主体骨架", "building body", "main building body"],
    "solid-base": ["墙体基座", "solid wall base"],
    "solid-wall": ["solid wall"],
    "floor-window": ["floor-to-ceiling window", "full-height glazing"],
    "double-height-window": ["double-height window", "通高玻璃窗"],
    "operable-sash": ["operable window sash", "开启窗扇"],
    "fixed-glazing": ["fixed glass", "固定玻璃窗"],
    "high-window": ["clerestory window"],
    "floor-window-group": ["floor-to-ceiling window group"],
    "glass-sliding-door": ["glass sliding door", "大面积玻璃推拉门"],
    "sectional-garage-door": ["garage door", "分节车库门"],
    "entrance-vestibule": ["entry vestibule", "入口门斗"],
    "equipment-platform": ["设备承托平台"],
    "ac-position": ["air conditioning unit", "air conditioner platform", "空调外机位"],
    "eave-soffit": ["soffit", "檐下封板"],
    "decorative-pilaster": ["pilaster", "壁柱"],
    "gable-dormer": ["dormer", "屋面老虎窗"],
    "framed-awning": ["awning", "雨棚支承构造"],
    "ornamental-iron-railing": ["wrought iron railing", "铁艺护栏"],
    "ventilation-louvre": ["ventilation louver", "通风百叶构造"],
    "exhaust-outlet": ["exhaust vent", "排气口"],
}
for row in ROWS:
    row["aliases"] = list(dict.fromkeys([*row["aliases"], *NAME_ALIASES.get(row["slug"], [])]))

GROUPS = {
    "envelope": ("envelope-detail-examples.md", "墙体、基座与围墙接口 JSON 示例"),
    "glazing": ("glazing-detail-examples.md", "玻璃窗、开启扇与凸窗 JSON 示例"),
    "entrance": ("entrance-door-examples.md", "门斗、庭院门与车库门 JSON 示例"),
    "balcony": ("balcony-equipment-examples.md", "阳台栏板、露台栏杆与设备平台 JSON 示例"),
    "equipment": ("ventilation-detail-examples.md", "固定百叶叶片与排风口 JSON 示例"),
    "roof": ("roof-facade-detail-examples.md", "屋面、老虎窗、壁柱与雨棚 JSON 示例"),
    "furniture": ("furniture-layout-examples.md", "家具与桌椅组合 JSON 示例"),
    "interior": ("kitchen-sanitary-examples.md", "橱柜与厨卫设施 JSON 示例"),
}

PLAN_TERMS = ['building_body','实墙基座','落地窗','主入口门斗','实墙','凸窗','阳台栏板','通高窗','装饰壁柱','庭院门','大面积玻璃移门','实体墙','设备平台','露台栏杆','开启扇','固定玻璃','装饰檐口','侧门','小窗','车库门','通风百叶','空调机位','女儿墙','屋檐下悬','储藏间门','高窗','庭院围墙接口','老虎窗','排风口','雨棚构造','roof','罗马柱','铁艺栏杆','景观矮墙','落地窗组']
PLAN_TERMS += ['沙发','茶几','餐桌椅','床','衣柜','书架','床头柜','电视柜','书桌椅','橱柜','洗手盆','马桶']


def compact_blueprint(bp, fragment=False):
    encode=lambda value: json.dumps(value,ensure_ascii=False,separators=(",",":"),allow_nan=False)
    lines=["{"]
    if not fragment:lines.append('  "meta":'+encode(bp["meta"])+',')
    if not fragment:lines.append('  "geometry":{')
    lines.append('    "elements":[')
    lines.extend('      '+encode(row)+(',' if i<len(bp["geometry"]["elements"])-1 else '') for i,row in enumerate(bp["geometry"]["elements"]))
    lines += ['    ],','    "components":'+encode(bp["geometry"]["components"])+(',' if fragment else '')]
    if not fragment:lines.append('  },')
    lines += ['  "materials":'+encode(bp["materials"]),'}']
    return '\n'.join(lines)


def main():
    import jsonschema
    schema=json.loads((KB/'schema.json').read_text(encoding='utf-8'))
    validator=jsonschema.Draft202012Validator(schema)
    OUT.joinpath('samples').mkdir(exist_ok=True)
    for row in ROWS:
        validator.validate(row['blueprint'])
        (OUT/'samples'/f"{row['slug']}.wild").write_text(compact_blueprint(row['blueprint'])+'\n',encoding='utf-8')
    (OUT/'catalog.json').write_text(json.dumps(ROWS,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    if '--ingest' in sys.argv:
        for group,(filename,title) in GROUPS.items():
            rows=[r for r in ROWS if r['group']==group]
            fm=['---',f'entity_name: {filename.removesuffix(".md").replace("-","_")}','topic: composition','status: experimental','authority: schema','primary_terms:']
            fm += [f'  - {title}']
            fm += ['synonyms: []','---',f'\n# {title}\n']
            for r in rows:
                formal_name = next((term for term in [r['name'], *r['aliases']] if any('\u4e00' <= char <= '\u9fff' for char in term)), r['name'])
                aliases = [term for term in dict.fromkeys([r['name'], *r['aliases']]) if term != formal_name]
                fm += [f'## {formal_name} · {r["slug"]}\n','<!-- rag-meta',f'entity_type: {r["entity_type"]}',f'entity_name: {r["slug"].replace("-","_")}', 'topic: composition','primary_terms:',f'  - {formal_name}',f'  - {r["slug"]}','synonyms:'+(' []' if not aliases else '')]
                fm += [f'  - {alias}' for alias in aliases]
                fm += ['-->\n',r['explanation']+'\n',
                       '下列是局部组装片段，不能直接当完整 `.wild` 加载：`elements`/`components` 分别并入蓝图的 `geometry.elements`/`geometry.components`，`materials` 并入蓝图材质字典。必要材料及宿主已包含；合并时替换 id、引用和安装坐标，不重复添加已有宿主。\n','```json',compact_blueprint(r['blueprint'],fragment=True),'```\n']
                fm += ['参考：'+'；'.join(f'[{SOURCES[s][0]}]({SOURCES[s][1]})' for s in r['sources'])+'。来源仅提供造型或分件参考，WILD 映射与示例取值为本项目转换。\n']
            (KB/'knowledge/components'/filename).write_text('\n'.join(fm),encoding='utf-8')
    terms={term for row in ROWS for term in [row['name'],*row['aliases']]}
    missing=set(PLAN_TERMS)-terms
    assert not missing, missing
    print(f'{len(ROWS)} 个 Schema 合法独立样例；覆盖 {len(PLAN_TERMS)} / {len(PLAN_TERMS)} 个原 plan 名称。')


if __name__=='__main__':main()
