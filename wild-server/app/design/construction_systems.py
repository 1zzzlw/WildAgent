"""已选构造的确定性展开；设计决定形式和参数，输出仍是原生 WILD。"""
from math import atan2, hypot, isfinite

VERSION = "construction-systems/1"


def construction_spec(design):
    form = design.get("form")
    return form.get("construction") if isinstance(form, dict) else None


def check_opening_bounds(spec, opening, wall):
    a, b = wall["from"], wall["to"]
    length = hypot(b[0]-a[0], b[2]-a[2])
    start, bottom, _ = opening["from"]
    width, height = opening["width"], opening["height"]
    if "surround" in spec:
        w = spec["surround"]["width"]
        lower = bottom-w if opening["type"] == "window" else bottom
        if start-w < -0.001 or start+width+w > length+0.001 or lower < min(a[1], b[1])-0.001 or bottom+height+w > max(a[1], b[1])+0.001:
            raise ValueError(f"门窗套超出墙边界：沿墙 [{start-w:g},{start+width+w:g}]、竖向 [{lower:g},{bottom+height+w:g}]；墙长 {length:g}、标高 [{min(a[1],b[1]):g},{max(a[1],b[1]):g}]")
    if spec["system"] == "entrance":
        canopy = spec["canopy"]
        left = start+(width-canopy["width"])/2
        top = bottom+height+canopy["clearance"]+canopy["thickness"]
        if left < -0.001 or left+canopy["width"] > length+0.001 or top > max(a[1], b[1])+0.001:
            raise ValueError(f"入口顶板超出墙边界：沿墙 [{left:g},{left+canopy['width']:g}]、板顶 {top:g}；墙长 {length:g}、墙顶 {max(a[1],b[1]):g}")
        if "posts" in canopy and canopy["posts"]["baseY"] > bottom+0.001:
            raise ValueError(f"入口柱底 {canopy['posts']['baseY']:g} 高于门底 {bottom:g}，需要明确承托标高")


def validate_construction(design):
    spec = construction_spec(design)
    if spec is None:
        return

    def fields(value, required, optional=()):
        if not isinstance(value, dict):
            raise ValueError("form.construction 及其参数组必须是对象；不选用的可选参数组应省略")
        missing, extra = set(required)-value.keys(), value.keys()-set(required)-set(optional)
        if missing or extra:
            raise ValueError(f"form.construction 字段错误：缺少 {sorted(missing)}；未定义 {sorted(extra)}")

    def positive(value, name):
        if type(value) not in (int, float) or not isfinite(value) or value <= 0:
            raise ValueError(f"form.construction.{name} 必须为有限正数")

    def material(value):
        if not isinstance(value, str) or not value.strip():
            raise ValueError("构造材料必须为明确的材质角色或 ID")

    size = design.get("size") or {}
    system = spec.get("system") if isinstance(spec, dict) else None
    if system == "layered_band":
        fields(spec, {"system", "axis", "layers"})
        if design["type"] != "cornice" or spec["axis"] not in {"x", "z"}:
            raise ValueError("layered_band 用于 cornice，axis 为 x 或 z；size 始终为世界 X/Y/Z 尺度")
        for key in ("width", "height", "depth"):
            positive(size.get(key), "size."+key)
        position = (design.get("placement") or {}).get("position")
        if not isinstance(position, list) or len(position) != 3 or any(type(v) not in (int, float) or not isfinite(v) for v in position):
            raise ValueError("layered_band 需要 placement.position 世界中心")
        layers = spec["layers"]
        if not isinstance(layers, list) or not 2 <= len(layers) <= 8:
            raise ValueError("layered_band.layers 需要 2 至 8 层，从下到上排列")
        for layer in layers:
            fields(layer, {"fraction", "depth_ratio", "material"})
            positive(layer["fraction"], "fraction")
            positive(layer["depth_ratio"], "depth_ratio")
            material(layer["material"])
        if abs(sum(l["fraction"] for l in layers)-1) > 1e-6 or abs(max(l["depth_ratio"] for l in layers)-1) > 1e-6:
            raise ValueError("各层 fraction 之和须为 1，depth_ratio 最大值须为 1，保持图纸整体尺寸")
        return
    if system not in {"framed_opening", "entrance"} or design["type"] not in {"window", "door"}:
        raise ValueError("未知或不适用的构造系统；仅支持 cornice.layered_band、门窗 framed_opening 和 door.entrance")
    kind = design["type"]
    if system == "entrance" and kind != "door":
        raise ValueError("entrance 仅用于门，门洞尺寸与位置保持原图纸")
    glazing = {"glassDepth", "glassMaterial", "verticalMullions", "horizontalMullions", "mullionWidth"}
    leaf = {"leafDepth", "leafMaterial", "interaction"}
    fields(spec, {"system", "frameWidth", "frameDepth", "frameMaterial"} | (glazing if kind == "window" else leaf)
           | ({"canopy"} if system == "entrance" else set()), {"surround"})
    for key in ("width", "height"):
        positive(size.get(key), "size."+key)
    for key in ("frameWidth", "frameDepth", "glassDepth" if kind == "window" else "leafDepth"):
        positive(spec[key], key)
    material(spec["frameMaterial"])
    material(spec["glassMaterial" if kind == "window" else "leafMaterial"])
    if kind == "door":
        from app.agent.generation.capability import load_engine_schema, capability_surface
        from jsonschema import Draft202012Validator
        schema = load_engine_schema()
        field = capability_surface()["door"]["schema"]["properties"]["interaction"]
        errors = list(Draft202012Validator({**field, "$defs": schema["$defs"]}).iter_errors(spec["interaction"]))
        if errors:
            raise ValueError("form.construction.interaction："+errors[0].message)
    if 2*spec["frameWidth"] >= min(size["width"], size["height"]) or spec.get("glassDepth", spec.get("leafDepth")) > spec["frameDepth"]:
        raise ValueError("框宽须保留洞口净空，玻璃/门扇厚度不能超过框深")
    if kind == "window":
        positive(spec["mullionWidth"], "mullionWidth")
        for key, extent in (("verticalMullions", "width"), ("horizontalMullions", "height")):
            if type(spec[key]) is not int or not 0 <= spec[key] <= 16:
                raise ValueError(f"{key} 必须是 0 至 16 的整数")
            if 2*spec["frameWidth"]+spec[key]*spec["mullionWidth"] >= size[extent]:
                raise ValueError(f"{key} 分格占满洞口，没有玻璃净空")
    if "surround" in spec:
        surround = spec["surround"]
        fields(surround, {"width", "depth", "embed", "material"})
        positive(surround["width"], "surround.width")
        positive(surround["depth"], "surround.depth")
        positive(surround["embed"], "surround.embed")
        if surround["embed"] >= surround["depth"]:
            raise ValueError("门窗套嵌入深度必须小于总厚度，保留外露层次")
        material(surround["material"])
    if system == "entrance":
        canopy = spec["canopy"]
        fields(canopy, {"width", "depth", "thickness", "clearance", "material", "soffit"}, {"posts"})
        for key in ("width", "depth", "thickness", "clearance"):
            positive(canopy[key], "canopy."+key)
        material(canopy["material"])
        fields(canopy["soffit"], {"thickness", "embed", "material"})
        positive(canopy["soffit"]["thickness"], "soffit.thickness")
        positive(canopy["soffit"]["embed"], "soffit.embed")
        material(canopy["soffit"]["material"])
        surround_width = spec.get("surround", {}).get("width", 0)
        if canopy["width"] < size["width"]+2*surround_width or canopy["clearance"] <= canopy["soffit"]["thickness"]+surround_width:
            raise ValueError("入口顶板须覆盖门套宽度，板底与门顶净距须容纳檐底和上门套")
        if "posts" in canopy:
            posts = canopy["posts"]
            fields(posts, {"width", "baseY", "material"})
            positive(posts["width"], "posts.width")
            if type(posts["baseY"]) not in (int, float) or not isfinite(posts["baseY"]):
                raise ValueError("posts.baseY 必须是明确的有限承托标高")
            material(posts["material"])
            if 2*posts["width"] >= canopy["width"]-size["width"]-2*surround_width or posts["width"] >= canopy["depth"]:
                raise ValueError("入口两侧支柱不能侵占门洞/门套净宽，且须位于顶板范围内")


def construct_system(marker, blueprint):
    design = marker["design"]
    validate_construction(design)
    spec = construction_spec(design)
    if spec is None:
        return None
    size, mid = design["size"], marker["id"]
    materials = marker.get("construction_materials") or {}
    elements, components = [], []

    def mat(name):
        return name if name in blueprint.get("materials", {}) else materials.get(name, name)

    def box(suffix, position, dimensions, material, rotation=None):
        item = {"id": mid+"_"+suffix, "type": "primitive", "shape": "box", "position": position,
                "dimensions": dimensions, "material": mat(material)}
        if rotation:
            item["rotation"] = rotation
        elements.append(item)

    if spec["system"] == "layered_band":
        center = design["placement"]["position"]
        y = center[1]-size["height"]/2
        for i, layer in enumerate(spec["layers"]):
            h = size["height"]*layer["fraction"]
            dims = [size["width"], h, size["depth"]]
            dims[2 if spec["axis"] == "x" else 0] *= layer["depth_ratio"]
            box(f"layer_{i}", [center[0], y+h/2, center[2]], dims, layer["material"])
            y += h
    else:
        from .relations import opening_host, opening_target, place_opening_group, wall_attached_point
        wall = opening_host(blueprint, marker)
        diagram = marker.get("diagram_host") or wall
        if not wall or not diagram or wall.get("curve"):
            raise ValueError("构造展开需要已实现的直墙宿主")
        origin = opening_target(marker, diagram, size["width"], size["height"])
        if origin is None:
            raise ValueError("构造展开缺少图纸门窗定位")
        opening = {"id": mid+"_opening", "type": design["type"], "parentWall": diagram["id"],
                   "from": origin, "width": size["width"], "height": size["height"],
                   **{k: mat(v) if k.endswith("Material") else v for k, v in spec.items()
                      if k not in {"system", "surround", "canopy"}}}
        placed, _ = place_opening_group(blueprint, {"geometry": {"components": [opening]}}, marker)
        opening = placed["geometry"]["components"][0]
        components.append(opening)
        wall = next(w for w in blueprint["geometry"]["elements"] if w["id"] == opening["parentWall"])
        check_opening_bounds(spec, opening, wall)
        a, b = wall["from"], wall["to"]
        length = hypot(b[0]-a[0], b[2]-a[2])
        ux, uz = (b[0]-a[0])/length, (b[2]-a[2])/length
        start, bottom, _ = opening["from"]
        width, height = size["width"], size["height"]

        def attached(suffix, along, y, outward, w, h, d, material):
            position = wall_attached_point(blueprint, opening, along, y, outward)
            if abs(uz) < 1e-6:
                box(suffix, position, [w, h, d], material)
            elif abs(ux) < 1e-6:
                box(suffix, position, [d, h, w], material)
            else:
                box(suffix, position, [w, h, d], material, [0, -atan2(uz, ux), 0])

        if "surround" in spec:
            surround = spec["surround"]
            w, d, material = surround["width"], surround["depth"], surround["material"]
            if surround["embed"] >= wall["thickness"]:
                raise ValueError("门窗套嵌入深度超过宿主墙厚")
            outward = d/2-surround["embed"]
            for suffix, along in (("left", start-w/2), ("right", start+width+w/2)):
                attached("surround_"+suffix, along, bottom+height/2, outward, w, height, d, material)
            attached("surround_top", start+width/2, bottom+height+w/2, outward, width+2*w, w, d, material)
            if design["type"] == "window":
                attached("surround_bottom", start+width/2, bottom-w/2, outward, width+2*w, w, d, material)
        if spec["system"] == "entrance":
            canopy = spec["canopy"]
            w, d, h = canopy["width"], canopy["depth"], canopy["thickness"]
            left = start+(width-w)/2
            top = bottom+height+canopy["clearance"]
            components.append({"id": mid+"_canopy", "type": "canopy", "parentWall": wall["id"],
                               "from": [left, top+h/2, opening["from"][2]], "width": w, "depth": d,
                               "thickness": h, "supportCount": 0, "material": mat(canopy["material"])})
            soffit = canopy["soffit"]
            t = soffit["thickness"]
            if soffit["embed"] >= wall["thickness"]:
                raise ValueError("檐底嵌入深度超过宿主墙厚")
            attached("soffit", start+width/2, top-t/2, (d-soffit["embed"])/2, w, t, d+soffit["embed"], soffit["material"])
            if "posts" in canopy:
                post = canopy["posts"]
                p, post_height = post["width"], top-t-post["baseY"]
                for suffix, along in (("left", left+p/2), ("right", left+w-p/2)):
                    attached("post_"+suffix, along, post["baseY"]+post_height/2, d-p/2, p, post_height, p, post["material"])

    def rounded(value):
        if isinstance(value, float):
            return round(value, 6)
        if isinstance(value, list):
            return [rounded(v) for v in value]
        if isinstance(value, dict):
            return {k: rounded(v) for k, v in value.items()}
        return value
    return rounded({"id": mid, "geometry": {"elements": elements, "components": components}, "materials": {}, "assets": {}})


def construction_review(blueprint, entities, marker):
    """重建同一批准构造，防止层、支承、分格或材料在采纳/装配时丢失。"""
    try:
        expected = construct_system(marker, blueprint)
    except (ValueError, KeyError, TypeError) as exc:
        return {"status": "needs_review", "checked": [], "unverified": [], "errors": [str(exc)]}
    wanted = {e["id"]: e for items in expected["geometry"].values() for e in items}
    actual = {e["id"]: e for e in entities}
    errors = []
    for entity_id in sorted(wanted.keys() | actual.keys()):
        if entity_id not in wanted or entity_id not in actual:
            errors.append(f"构造 {marker['id']} 的实体集合不一致：{entity_id}")
        elif wanted[entity_id] != actual[entity_id]:
            fields = [k for k in wanted[entity_id].keys() | actual[entity_id].keys() if wanted[entity_id].get(k) != actual[entity_id].get(k)]
            errors.append(f"构造 {marker['id']} 的 {entity_id} 偏离批准参数：{', '.join(sorted(fields))}")
    return {"status": "checked" if not errors else "needs_review", "checked": ["construction."+construction_spec(marker["design"])["system"]],
            "unverified": [], "errors": errors}


SYSTEM_PROTOCOL = """
可执行构造：在 components[].form.construction 中选择并写齐参数，审核后由程序直接展开，无需执行模型重写几何。不适用时保留自定义 form。
1. cornice 的 layered_band：{system:"layered_band",axis:"x",layers:[{fraction:0.25,depth_ratio:0.65,material:"facade_primary"},{fraction:0.5,depth_ratio:0.8,material:"accent"},{fraction:0.25,depth_ratio:1,material:"structure"}]}。
   2至8层从下到上；fraction 和为1，depth_ratio 最大为1。size 是世界 X/Y/Z 总尺寸，position 是整体中心；axis 选 x/z 为延伸方向，横向各层居中。适合直线叠层檐口，不代替曲檐或整片屋面。
2. window 的 framed_opening：{system:"framed_opening",frameWidth:0.06,frameDepth:0.14,glassDepth:0.02,verticalMullions:2,horizontalMullions:1,mullionWidth:0.035,frameMaterial:"frame",glassMaterial:"glass",surround:{width:0.09,depth:0.06,embed:0.015,material:"facade_primary"}}。
   门的完整 framed_opening 示例：{system:"framed_opening",frameWidth:0.06,frameDepth:0.14,frameMaterial:"frame",leafDepth:0.04,leafMaterial:"door",interaction:{mode:"swing",hingeSide:"left",openAngle:90}}。
   size.width/height 始终是原洞口宽高，surround 可省略；门套三边，窗套四边，不能超出墙边界。
3. 主入口 door 的完整 entrance 示例：{system:"entrance",frameWidth:0.06,frameDepth:0.14,frameMaterial:"frame",leafDepth:0.04,leafMaterial:"door",interaction:{mode:"swing",hingeSide:"left",openAngle:90},canopy:{width:3.2,depth:1.6,thickness:0.18,clearance:0.35,material:"structure",soffit:{thickness:0.06,embed:0.015,material:"accent"},posts:{width:0.14,baseY:0,material:"accent"}}}。
   clearance 是顶板底到门顶的净距，须容纳檐底和上门套；posts 可省略，有则为两侧前柱，不能挡住门洞。baseY 明确选择柱底承托标高，不自动等于门槛标高。顶板、檐底、柱均由同一门和实际墙关系定位；本门任务已包含它们，不再另列重复雨棚或柱。
   embed 为门窗套或檐底向墙内嵌入的正深度，须小于墙厚；门窗套 embed 还须小于 depth，外露厚度为 depth-embed。檐底向墙内延伸 embed，外边仍对齐顶板。
所有示例数值仅解释字段，由本次设计决定比例、材料和层次。材质填已声明角色或具体 ID；上述系统不能混入未定义字段，不用的可选参数组省略，不写 null；framed_opening 不含 canopy，需要雨棚须明确选择 entrance。不能用于替换不兼容的特殊造型。
"""
