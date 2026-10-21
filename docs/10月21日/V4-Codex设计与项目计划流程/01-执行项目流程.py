"""V4：实际项目 plan/execute/replanner/compile/final_validate，Codex 提供生成处理器。

替换只存在于本进程；不改项目源码、模型配置和知识库。不是原模型节点的自动生成。
"""
import os
os.environ.setdefault("SystemRoot", r"C:\Windows")
os.environ.setdefault("WINDIR", r"C:\Windows")
os.environ["RAG__ENABLED"] = "false"
os.environ["LANGSMITH_TRACING"] = "false"
import asyncio
import json
import sys
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from datetime import datetime, timezone, timedelta
SHANGHAI=timezone(timedelta(hours=8))

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[2]
sys.path.insert(0,str(ROOT/"wild-server"))

# 保留纯校验模块的导入能力，同时禁止使用项目聊天/嵌入服务。
from config import config
config.rag.enabled = False
NETWORK_ATTEMPTS=[]
MODEL_ATTEMPTS=[]

class DisabledModel:
    def __getattr__(self, name):
        MODEL_ATTEMPTS.append(name)
        raise RuntimeError(f"V4 禁止项目模型调用：{name}")

import app.llm.client as llm_client
llm_client.create_llm = lambda *args, **kwargs: DisabledModel()
import socket
original_connect=socket.socket.connect
def local_connect(sock, address):
    # Windows asyncio 自身的唤醒管道需要 loopback socketpair。
    if isinstance(address,tuple) and address[0] in {"127.0.0.1","::1"}:
        return original_connect(sock,address)
    NETWORK_ATTEMPTS.append("external socket.connect")
    raise RuntimeError("V4 生成进程禁止外部网络访问")
socket.socket.connect = local_connect

from app.design.contracts import DesignDocument
from app.design.compilation import project_drawing
from app.design.resolver import render_design_svg, _stable_hash
from app.design.coordinates import design_geometry_context, resolve_stair_geometry, repetition_geometry
from app.design.repository import DesignRepository
from app.agent.plan.implementation import _accept_group, _bind_materials, _item_context, implementation_blueprint
from app.agent.plan.workflow import plan_node, execute_node, replanner_node
from app.agent.plan.handlers import HANDLERS
from app.agent.plan.contracts import PlanDocument
from app.agent.plan.store import poll_runnable
from app.agent.design_flow.compile import _assemble_with_relations, compile_node
from app.agent.validation.candidate import evaluate_candidate
from app.agent.validation.workflow import validate_node
from app.agent.validation.diagnostics import blueprint_fingerprint


def save(name, value):
    (OUT/name).parent.mkdir(parents=True,exist_ok=True)
    (OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False),encoding="utf-8")


def box(name, values):
    x,y,z,w,h,d,mat=values
    return dict(type="primitive",id=name,shape="box",position=[x,y,z],dimensions=[w,h,d],material=mat)


def floor(name, rect, y, material="floor", thickness=0.22):
    x0,z0,x1,z1=rect
    return dict(type="floor",id=name,**{"from":[x0,y-thickness,z0],"to":[x1,y-thickness,z1]},
                thickness=thickness,material=material)


def implement(marker, document, context):
    d=document.decisions
    spec=marker["design"]
    form=spec.get("form") or {}
    elements,components=[],[]
    mid=marker["id"]
    if mid=="building_body":
        # 使用当前项目统一计算的体量并集减挑空，不在实验脚本另写楼层/梯井算法。
        for level in context["levels"]:
            for i,rect in enumerate(level["floor_rectangles"]):
                elements.append(floor(f"slab_L{level['index']}_{i}",rect,level["base_y"],
                    thickness=context["construction"]["slab_thickness"]))
        for host in context["diagram_hosts"]:
            if host["type"]=="wall" and not host.get("open"):
                elements.append({**{k:host[k] for k in ("type","id","from","to","thickness")},
                                 "material":"facade_primary"})
    elif marker["type"] in ("door","window"):
        kind=marker["type"]
        target=context["opening_hosts"].get(mid) or {k:marker["entity"][k] for k in ("parentWall","from")}
        e=dict(type=kind,id=mid,**target,**spec["size"],
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
        route=context["stair_route_targets"][mid]
        for suffix in ("first_flight","second_flight"):
            flight=route[suffix]
            elements.append(dict(type="stair",id=mid+"_"+suffix,
                **{k:flight[k] for k in ("from","to","width","stepCount","stepDepth","stepHeight")},material="structure"))
        land=route["landing"]
        elements.append(floor(mid+"_landing",land["bounds"],land["top_y"],"structure",form["landing_thickness"]))
    elif form.get("recipe")=="stair_guard":
        geometry=design_geometry_context(d.model_dump(mode="json"))
        route=geometry["stair_routes"][form["stair"]]
        x,z,xmax,zmax=route["void"]["bounds"]
        turn=route["landing"]["bounds"][1]
        rise=d.massing.floor_height
        paths=[[[x,0,z],[x,rise/2,turn]], [[xmax,rise/2,turn],[xmax,rise,z]],
               [[x,rise/2,zmax],[xmax,rise/2,zmax]],
               [[x,rise,z],[x,rise,zmax],[xmax,rise,zmax],[xmax,rise,z]]]
        for i,path in enumerate(paths):
            components.append(dict(type="railing",id=mid+f"_{i}",path=path,height=spec["size"]["height"],
                **{k:form[k] for k in ("postSpacing","postRadius","railRadius","railLevels")},material="frame"))
    elif form.get("recipe")=="boxes":
        elements.extend(box(f"{mid}_{i}",row) for i,row in enumerate(form["members"]))
    elif form.get("recipe")=="repeat":
        target=repetition_geometry(spec)
        elements.extend(box(f"{mid}_{i}",[*position,*target["member_size"],"wood"])
                        for i,position in enumerate(target["positions"]))
    else:
        raise ValueError(f"未实现的图纸标记 {mid}，禁止静默遗漏")
    return dict(id=mid,geometry=dict(elements=elements,components=components),
                explanation="Codex 按当前设计输入离线落实；未调用外部模型")


async def codex_generate(state, item):
    """仅替换模型产出片段这一步；继续使用原任务上下文和片段验收器。"""
    document=DesignDocument.model_validate(state["design_document"])
    targets=set(item.target["marker_ids"])
    markers={m["id"]:deepcopy(m) for m in state["resolved_design"]["component_markers"] if m["id"] in targets}
    base=implementation_blueprint(state)
    context=_item_context(state,markers,base)
    save(f"任务证据/{item.id}-上下文.json",context)
    records,fragments,rows={},[],[]
    buckets={"elements":[],"components":[]}
    for mid,marker in markers.items():
        row=implement(marker,document,context)
        row,_bindings=_bind_materials(base,row,marker)
        base,entities,record=_accept_group(base,row,marker)
        record["author"]="Codex"
        records[mid]=record
        fragments.extend(entities)
        rows.append(row)
        for key in buckets:
            buckets[key].extend(e["id"] for e in row["geometry"][key])
    summary={"implemented":len(records),"abandoned":0,"total":len(targets),"design_complete":True}
    diag={"implementations":records,"implementation_summary":summary,"materials":{},"assets":{},**buckets}
    save(f"任务证据/{item.id}-实现及验收.json",{"item":item.model_dump(mode="json"),"rows":rows,"diagnostics":diag})
    return ({"component_fragments":{item.id:fragments},"component_diagnostics":{item.id:diag}},
            "succeeded",[e["id"] for e in fragments],f"Codex 实现并由项目验收 {len(records)} 个标记",
            [{"tool":"codex_authored_implementation","model_calls":0,"marker_ids":list(markers)}])


async def main():
    source=OUT/"02-栖庭V4-设计图纸-草稿.json"
    started=datetime.now(SHANGHAI).isoformat()
    repo=DesignRepository(OUT/"设计仓库")
    document=DesignDocument.model_validate_json(source.read_text(encoding="utf-8"))
    repo.save(document)
    # 本轮端到端生成授权下由 Codex 作流程确认；不代表用户已作视觉评价。
    document,_=repo.approve(document.session_id,document.revision)
    resolved=project_drawing(document)
    before=document.model_dump(mode="json")
    save("03-批准设计图纸.json",before)
    save("03-设计投影与构件标记.json",resolved.model_dump(mode="json"))
    for f in (1,2):
        (OUT/f"03-第{f}层设计图.svg").write_text(render_design_svg(document,resolved,floor=f),encoding="utf-8")
    paths=[*sorted((ROOT/"wild-server/app").rglob("*.py")),ROOT/"wild-core/schema.json"]
    fingerprints={str(p.relative_to(ROOT)).replace("\\","/"):sha256(p.read_bytes()).hexdigest() for p in paths}
    save("00-运行来源与指纹.json",{"started_at":started,"author":"Codex","basis":"V1 栖庭布局，当前图纸契约",
        "configured_chat_model_used":False,"embedding_used":False,"approval_actor":"Codex runner",
        "generation_handler":"本进程替换 HANDLERS.generate，项目源码不变",
        "actual_nodes":["plan","execute","replanner","compile","final_validate"],"source_sha256":fingerprints})
    state={"session_id":document.session_id,"user_message":document.requirements.source_request,
           "design_document":before,"resolved_design":resolved.model_dump(mode="json"),
           "design_review_status":"approved","detail_level":"detailed","component_fragments":{},"component_diagnostics":{}}
    state.update(await plan_node(state))
    assert state["plan_diag"]["model_calls"]==0
    save("04-plan节点输出.json",{k:state[k] for k in ("plan","plan_diag","drawing_hosts","skeleton_blueprint")})
    original=HANDLERS["generate"]
    HANDLERS["generate"]=codex_generate
    try:
        iteration=0
        while poll_runnable(PlanDocument.model_validate(state["plan"])):
            iteration+=1
            updates=await execute_node(state)
            for key in ("component_fragments","component_diagnostics","tool_trace"):
                if key in updates:
                    state.setdefault(key,{}).update(updates.pop(key))
            state.update(updates)
            save(f"节点证据/{iteration:02d}-execute.json",updates)
            assert state["execute_diag"]["run_state"]=="succeeded",state["execute_diag"]
            updates=await replanner_node(state)
            state.update(updates)
            save(f"节点证据/{iteration:02d}-replanner.json",updates)
    finally:
        HANDLERS["generate"]=original
    plan=PlanDocument.model_validate(state["plan"])
    assert all(i.status=="done" for i in plan.items),plan.model_dump(mode="json")
    save("05-plan完成状态.json",state["plan"])
    save("05-装配输入状态.json",state)
    # 先做纯函数预检；若有错误保留证据，由 Codex 修订实现，禁止转入项目模型修复。
    blueprint,missing,records=_assemble_with_relations(document,state)
    brief={"realization":document.decisions.massing.model_dump(mode="json"),
           "implementation":{"design_hash":_stable_hash(document),"records":records}}
    evaluation=evaluate_candidate(blueprint,design_document=before,design_brief=brief,source="v4_preflight")
    errors=[str(getattr(e,"output",e)) for e in evaluation["errors"]]
    save("06-装配预检.json",{"missing":missing,"errors":errors,"snapshot":evaluation["snapshot"]})
    assert not errors and not missing,{"errors":errors,"missing":missing}
    updates=await compile_node(state)
    state.update(updates)
    save("06-compile节点输出.json",updates)
    assert state["status"]=="complete",state.get("error")
    updates=await validate_node(state)
    state.update(updates)
    save("07-final_validate节点输出.json",updates)
    assert state["status"]=="complete",state.get("error")
    final=state["final_blueprint"]
    assert blueprint_fingerprint(final)==state["validation_snapshot"]["blueprint_fingerprint"]
    assert not MODEL_ATTEMPTS and not NETWORK_ATTEMPTS
    assert before==state["design_document"]
    save("栖庭V4-新中式别墅.wild",final)
    save("07-validation_snapshot.json",state["validation_snapshot"])
    repo.mark_compiled(document.session_id,revision=document.revision,design_hash=resolved.design_hash)
    result={"status":state["status"],"error_count":state["validation_error_count"],
        "warning_count":state["validation_warning_count"],"design_hash":resolved.design_hash,
        "blueprint_fingerprint":blueprint_fingerprint(final),"plan_items":len(plan.items),
        "implemented_markers":len(records),"model_calls":plan.llm_calls,"model_attempts":MODEL_ATTEMPTS,
        "network_attempts":NETWORK_ATTEMPTS,"finished_at":datetime.now(SHANGHAI).isoformat(),
        "source_unchanged":before==state["design_document"],"author":"Codex",
        "visual_review":"待实际渲染和查看；本报告不宣称用户视觉验收通过"}
    save("08-生成结果.json",result)
    print(json.dumps(result,ensure_ascii=False),flush=True)


if __name__=="__main__":
    asyncio.run(main())
