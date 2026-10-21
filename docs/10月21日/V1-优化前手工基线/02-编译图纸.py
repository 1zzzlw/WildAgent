"""此图专用的离线实现器：按项目标记协议验收，再调用项目装配入口。"""
import json
import sys
from copy import deepcopy
from graphlib import TopologicalSorter
from hashlib import sha256
from pathlib import Path

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[1]
sys.path.insert(0,str(ROOT/"wild-server"))

from app.design.contracts import DesignDocument
from app.design.compilation import project_drawing
from app.design.resolver import render_design_svg, _stable_hash
from app.agent.plan.implementation import _accept_group
from app.agent.design_flow.compile import _assemble_with_relations
from app.agent.validation.candidate import evaluate_candidate


def save(name, value):
    (OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False),encoding="utf-8")


def box(name, values):
    x,y,z,w,h,d,mat=values
    return dict(type="primitive",id=name,shape="box",position=[x,y,z],dimensions=[w,h,d],material=mat)


def floor(name, rect, y, material="floor", thickness=0.22):
    x0,z0,x1,z1=rect
    return dict(type="floor",id=name,**{"from":[x0,y-thickness,z0],"to":[x1,y-thickness,z1]},
                thickness=thickness,material=material)


def implement(marker, document):
    d=document.decisions
    spec=marker["design"]
    form=spec.get("form") or {}
    elements,components=[],[]
    mid=marker["id"]
    if mid=="building_body":
        construction=d.model_extra["construction"]
        for v in d.volumes:
            faces={"front":([v.x,v.z],[v.x+v.width,v.z]),
                   "right":([v.x+v.width,v.z],[v.x+v.width,v.z+v.depth]),
                   "back":([v.x+v.width,v.z+v.depth],[v.x,v.z+v.depth]),
                   "left":([v.x,v.z+v.depth],[v.x,v.z])}
            for f in range(v.start_floor,v.end_floor+1):
                y=(f-1)*d.massing.floor_height
                rectangles=[(v.x,v.z,v.x+v.width,v.z+v.depth)]
                for layout in d.model_extra["floor_layouts"]:
                    if layout["floor"]!=f:
                        continue
                    for room in layout["rooms"]:
                        if not room.get("void"):
                            continue
                        b=room["bounds"]
                        cut=(b["x"],b["z"],b["x"]+b["width"],b["z"]+b["depth"])
                        remaining=[]
                        for x0,z0,x1,z1 in rectangles:
                            a,c=max(x0,cut[0]),min(x1,cut[2])
                            b0,d0=max(z0,cut[1]),min(z1,cut[3])
                            if c<=a or d0<=b0:
                                remaining.append((x0,z0,x1,z1))
                            else:
                                remaining.extend(r for r in [(x0,z0,a,z1),(c,z0,x1,z1),(a,z0,c,b0),(a,d0,c,z1)]
                                                 if r[2]-r[0]>0.001 and r[3]-r[1]>0.001)
                        rectangles=remaining
                for i,rect in enumerate(rectangles):
                    elements.append(floor(f"slab_{v.id}_{f}_{i}",rect,y,
                                          thickness=construction["slab_thickness"]))
                for face,(a,b) in faces.items():
                    facade=v.facades.get(face) or d.facades[face]
                    pattern=facade.ground_pattern if f==1 else facade.upper_pattern
                    if pattern==["open"]:
                        continue
                    elements.append(dict(type="wall",id=f"wall_{v.id}_{face}_L{f}",
                        **{"from":[a[0],y,a[1]],"to":[b[0],y+d.massing.floor_height,b[1]]},
                        thickness=construction["wall_thickness"],material="facade_primary"))
        for layout in d.model_extra["floor_layouts"]:
            for wall in layout["walls"]:
                a,b=wall["from"],wall["to"]
                elements.append(dict(type="wall",id=wall["id"],
                    **{"from":[a[0],layout["level"],a[1]],"to":[b[0],layout["level"]+d.massing.floor_height,b[1]]},
                    thickness=wall["thickness"],material="facade_primary"))
    elif marker["type"] in ("door","window"):
        kind=marker["type"]
        host=marker["diagram_host"]
        y=host["from"][1]+spec["placement"].get("sill_height",0)
        e=dict(type=kind,id=mid,parentWall=marker["host"],
            **{"from":[spec["placement"]["offset"],y,0]},**spec["size"],
            **{k:v for k,v in form.items() if k!="description"})
        if kind=="window":
            e.update(verticalMullions=form.get("verticalMullions",2),horizontalMullions=form.get("horizontalMullions",1))
        else:
            e.update(doorStyle=form.get("doorStyle","single"),leafRows=form.get("leafRows",2))
        components.append(e)
    elif form.get("recipe")=="hip_roof":
        v=spec["volume"]
        over=form["overhang"]
        w,depth=v["width"]+2*over,v["depth"]+2*over
        x,z=v["x"]+v["width"]/2,v["z"]+v["depth"]/2
        y=v["end_floor"]*d.massing.floor_height
        h=form["height"]
        elements.append(dict(type="roof",id=mid,roofType="hip",ridgeAxis=form["ridgeAxis"],
                             span=w,depth=depth,height=h,thickness=form["thickness"],position=[x,y,z],material="roof"))
        axis=form["ridgeAxis"]
        ridge=max(0.3,(w-depth) if axis=="x" else (depth-w))
        rh,fh,fd=form["ridge_height"],form["fascia_height"],form["fascia_depth"]
        elements.append(box(mid+"_ridge",[x,y+h+rh/2,z,ridge if axis=="x" else form["ridge_width"],
                             rh,form["ridge_width"] if axis=="x" else ridge,"roof"]))
        for i,row in enumerate([[x,y,z-depth/2,w,fh,fd,"roof"], [x,y,z+depth/2,w,fh,fd,"roof"],
                               [x-w/2,y,z,fd,fh,depth,"roof"], [x+w/2,y,z,fd,fh,depth,"roof"]]):
            elements.append(box(mid+f"_fascia_{i}",row))
    elif form.get("recipe")=="u_stair":
        x,z=form["origin"]
        w,gap,run,landing=form["flight_width"],form["gap"],form["run"],form["landing"]
        rise=d.massing.floor_height
        for suffix,cx,ya,yb,za,zb in [("first",x+w/2,0,rise/2,z,z+run),
                                      ("second",x+w+gap+w/2,rise/2,rise,z+run,z)]:
            elements.append(dict(type="stair",id=mid+"_"+suffix,**{"from":[cx,ya,za],"to":[cx,yb,zb]},
                width=w,stepCount=form["steps_each"],stepDepth=run/form["steps_each"],
                stepHeight=rise/(2*form["steps_each"]),material="structure"))
        elements.append(floor(mid+"_landing",[x,z+run,x+2*w+gap,z+run+landing],rise/2,"structure",form["landing_thickness"]))
    elif form.get("recipe")=="stair_guard":
        stair=next(c for c in d.components if c.id==form["stair"]).form
        x,z=stair["origin"]
        w,gap,run,land=stair["flight_width"],stair["gap"],stair["run"],stair["landing"]
        xmax=x+2*w+gap
        rise=d.massing.floor_height
        paths=[[[x,0,z],[x,rise/2,z+run]], [[xmax,rise/2,z+run],[xmax,rise,z]],
               [[x,rise/2,z+run+land],[xmax,rise/2,z+run+land]],
               [[x,rise,z],[x,rise,z+run+land],[xmax,rise,z+run+land],[xmax,rise,z]]]
        for i,path in enumerate(paths):
            components.append(dict(type="railing",id=mid+f"_{i}",path=path,height=spec["size"]["height"],
                **{k:form[k] for k in ("postSpacing","postRadius","railRadius","railLevels")},material="frame"))
    elif form.get("recipe")=="boxes":
        elements.extend(box(f"{mid}_{i}",row) for i,row in enumerate(form["members"]))
    else:
        raise ValueError(f"未实现的图纸标记 {mid}，禁止静默遗漏")
    return dict(id=mid,geometry=dict(elements=elements,components=components),
                explanation="Codex 按当前设计输入离线落实；未调用外部模型")


def main():
    source=OUT/"01-栖庭别墅-设计图纸.json"
    document=DesignDocument.model_validate_json(source.read_text(encoding="utf-8"))
    before=document.model_dump(mode="json")
    resolved=project_drawing(document)
    save("03-设计投影与构件标记.json",resolved.model_dump(mode="json"))
    for f in (1,2):
        (OUT/f"03-第{f}层设计图.svg").write_text(render_design_svg(document,resolved,floor=f),encoding="utf-8")
    materials={r.materialId:r.material for r in document.decisions.materials.resolved_plan.roles}
    materials.update(document.decisions.materials.model_extra["implementation_materials"])
    base=dict(meta=dict(version="1.0",type="building",name="栖庭·新中式庭院别墅",author="Codex",style="新中式"),
              geometry=dict(elements=[],components=[]),materials=materials,assets={})
    state=dict(design_document=before,resolved_design=resolved.model_dump(mode="json"),
               skeleton_blueprint=deepcopy(base),component_fragments={},component_diagnostics={})
    markers={m["id"]:m for m in resolved.component_markers}
    rows=[]
    for mid in TopologicalSorter({k:set(m["depends_on"]) for k,m in markers.items()}).static_order():
        marker=markers[mid]
        row=implement(marker,document)
        base,entities,record=_accept_group(base,row,marker)
        state["component_fragments"][mid]=entities
        state["component_diagnostics"][mid]=dict(implementations={mid:record},
            elements=[e["id"] for e in row["geometry"]["elements"]],
            components=[e["id"] for e in row["geometry"]["components"]])
        rows.append(row)
        print(f"已验收 {mid}: {len(entities)} entities",flush=True)
    save("04-构件实现片段.json",rows)
    save("04-装配输入状态.json",state)
    blueprint,missing,records=_assemble_with_relations(document,state)
    brief=dict(realization=document.decisions.massing.model_dump(mode="json"),
               implementation=dict(design_hash=_stable_hash(document),records=records))
    evaluation=evaluate_candidate(blueprint,design_document=before,design_brief=brief,source="codex_offline_author")
    errors=[str(getattr(e,"output",e)) for e in evaluation["errors"]]
    report=dict(ok=not errors and not missing,missing_markers=missing,errors=errors,
                design_hash=_stable_hash(document),source_sha256=sha256(source.read_bytes()).hexdigest(),
                implemented_markers=len(records),model_calls=0,
                implementations=records,fulfillment=evaluation.get("fulfillment"),
                snapshot=evaluation.get("snapshot"),
                source_unchanged=(before==document.model_dump(mode="json")))
    # 报告字段保持项目原始结构，数据类和 Pydantic 只在写出时转成 JSON。
    from dataclasses import asdict,is_dataclass
    def serial(value):
        if is_dataclass(value): return asdict(value)
        if hasattr(value,"model_dump"): return value.model_dump(mode="json")
        if isinstance(value,dict): return {k:serial(v) for k,v in value.items()}
        if isinstance(value,(list,tuple)): return [serial(v) for v in value]
        return value
    save("05-编译与验收报告.json",serial(report))
    save("栖庭-新中式别墅.wild",blueprint)
    print(json.dumps({k:report[k] for k in ("ok","missing_markers","errors","implemented_markers","source_unchanged")},ensure_ascii=False))
    if not report["ok"]:
        raise SystemExit(1)


if __name__=="__main__":
    main()
