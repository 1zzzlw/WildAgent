"""从已发生的命令与最终指纹整理记录，不改写历史命令和失败输出。"""
import hashlib
import json
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]
DAY=ROOT/'docs'/'10月22日'
NOTES={
    '07-图书馆':('内庭环廊、赤陶遮阳、书架阅览席、咨询台与新书展示。',
        '首轮楼梯终点在洞口边界内侧，缩回洞口起点后通过端点承托；屋面改为原生分块平顶，补内庭梁柱与设备围屏；实图发现雨棚遮住部分招牌，抬高招牌；入口纪念牌移到左侧，避开中央通路。',
        '后端 validate_roof_coverage 仍有两条 depth=0 的承托识别警告。该检查的墙/柱/梁候选不识别本稿的矩形 primitive.box 内庭梁柱；没有修改校验器或隐藏输出。交付关系核对已按实体顶标高与矩形交叠列出四块屋顶的实际接触构件，顶标高均为8.8米，墙顶覆盖7e通过。此复核证明几何接触，不代替承载计算。'),
    '08-现代别墅':('双层退台、木格棚、玻璃露台、餐厨卧室卫浴、下沉泳池与庭院照明。',
        '初稿泳池下方的场地板未挖空，已按同一池边界拆板，池深核对为1.04米；客卫隔墙移离楼梯；次卧增加独立门，避免必须经过浴室；室内门改实心门；招牌移到入口雨棚前缘，避免立柱挡字；补退台格棚、室外家具和屋面收边。',
        '后端全流水线零错误零警告。前端 reconstructionDiagnostics 仍提示 RECONSTRUCTION_ROOF_COVERAGE：只统计 roof 并集，没有把南、东向露台 floor 计作首层封顶。前端源码也注明该检查只作提示，权威7e包含楼板/上层墙。本稿7e通过，楼板净面积、开口和实图另外复核；原警告保留，未改判据。'),
    '09-咖啡厅':('连续檐廊、窗边长椅、室内外座席、咖啡机杯具、糕点柜和独立卫生间。',
        '砖饰面约束在实心窗间墙，不穿玻璃；主招牌从墙檐之间移到雨棚前缘，消除屋面遮字；补窗边长椅，卫生间使用实心门。',
        '最终Schema、后端流水线、Core编译重建和前端重建均无错误、无警告。'),
    '10-超市':('连续招牌、双面分区货架、商品、生鲜、冷藏柜、收银、后场与推车。',
        '双面货架按两侧方向装配，避免两排商品同向遮挡；补后场围合与实心门；推车移到门外；主招牌移到雨棚前缘；补分区文字和副招牌吊杆。',
        '最终Schema、后端流水线、Core编译重建和前端重建均无错误、无警告。'),
}
deliveries=[]
ref=json.loads((DAY/'00-质量参考/本次命名建筑对照/汀院/render_manifest.json').read_text(encoding='utf-8'))
for folder,(features,changes,boundary) in NOTES.items():
    base=DAY/folder;target=next(base.glob('*.wild'))
    bp=json.loads(target.read_text(encoding='utf-8'));name=bp['meta']['name']
    audit=json.loads((base/'04-校验/交付关系核对.json').read_text(encoding='utf-8'))
    render=json.loads((base/'05-效果图/render_manifest.json').read_text(encoding='utf-8'))
    assert render['contextSha256']==ref['contextSha256']
    records=[(f,json.loads(f.read_text(encoding='utf-8'))) for f in (base/'03-过程记录/命令记录').glob('*.json')]
    records.sort(key=lambda v:(v[1]['started_at'],v[0].name))
    for stage in ['作者编译','项目校验','Core重建','四视图','日夜与招牌','关系与剖切','剖切实图','字节重放']:
        assert any(f.stem=='最终收尾-'+stage and r['exit_code']==0 for f,r in records)
    for cut in audit['cuts']:
        path=base/cut['path'];m=json.loads((path.parent/'效果图/render_manifest.json').read_text(encoding='utf-8'))
        assert m['inputSha256']==cut['sha256'] and m['compileErrors']==m['reconstructErrors']==0
    size=round(audit['site_size_m'][0]);n=len(bp['geometry']['elements']);c=len(bp['geometry']['components'])
    cut_links='\n'.join(f"- [{Path(cut['path']).parent.name}查看]({cut['path'].replace(chr(92),'/')}) · [俯视实图]({Path(cut['path']).parent.as_posix()}/效果图/top.png)" for cut in audit['cuts'])
    readme=f'''# {name}

正式文件：[打开 {name}.wild]({name}.wild)

地块 **{size}×{size}米**，包括入口、庭院和景观；主体退进地块边界。{features}

主招牌文字为“{name}”，直接保存在 `geometry.elements[].label.text` 中，朝向世界−Z。共有{audit['real_lights']}个自制灯罩使用 `lightSource`，能照亮周围；不只是材质自发光。正式文件有{n}个基础元素、{c}个组合构件，数量只用于核对文件，不充当精细度评价。

## 直接看效果

- [日景](05-效果图/世界环境/day.png) · [夜景](05-效果图/世界环境/night.png) · [招牌近景](05-效果图/世界环境/sign.png)
- [同条件透视](05-效果图/perspective.png) · [正面](05-效果图/front.png) · [侧面](05-效果图/side.png) · [俯视](05-效果图/top.png)
{cut_links}

日夜图复用生产渲染器的材质、水面和环境贴图运行时，并启用太阳阴影；没有用AI生成或修饰建筑效果图。同条件四视图使用项目 `render-baseline.mjs` 的固定设置。

## 设计与创建记录

- [DesignDocument](01-需求与设计/DesignDocument.json) · [主体设计投影](01-需求与设计/主体设计投影.json) · [设计说明](01-需求与设计/设计说明.md)
- [重建入口](02-生成脚本/重建说明.md) · [完整流程与命令索引](03-过程记录/流程日志.md)
- [最终项目校验](04-校验/最终项目校验.json) · [尺寸、招牌、楼梯、屋面接触与文件指纹](04-校验/交付关系核对.json)

创建方式：Codex先独立设计，保存当前DesignDocument，再由确定性作者脚本装配WILD；`project_drawing`是主壳设计投影，详细成品通过作者装配生成。没有运行完整LangGraph、RAG或外部模型API。

## 验证结果与保留问题

Schema、后端流水线、Core编译/重建错误均为0；未映射材质0；独立Chromium/WebGL运行时错误0。最终作者脚本重放与正式WILD逐字节一致。剖切仅删除遮挡构件，保留项与正式文件逐项相等，剖切本身也已通过Schema及Core重建并真实渲染。

{boundary}

尺寸是完整场景占地，不能读作主体净开间。实图已查看并据此修订，审美评价请结合[与汀院的同条件对照](../00-质量参考/本次命名建筑对照/对照说明.md)；不以静态校验代替效果判断。
'''
    if folder=='08-现代别墅':readme+='\n[泳池近景](05-效果图/世界环境/water.png)：场地下方已挖空，池深1.04米，浅色分缝池底透过水面可见。固定基线有y=−0.02的外部地面，因此下沉池的透明度以这张世界环境近景为准。\n'
    (base/'README.md').write_text(readme,encoding='utf-8')
    lines=[f'# {name}创建流程', '', '仅记录建筑创作；应用优化未另写过程日志。', '',
        '## 执行方式', '', '设计输入 → 作者装配 → Schema/后端/Core只读校验 → Chromium/WebGL实图 → 看图修订 → 剖切复核 → 字节重放。', '',
        '作者装配没有使用项目Agent；共用构件工具只提供基本几何，不把旧建筑的布局作为本稿模板。', '',
        '## 实际修订', '', changes, '',
        '最初作者编译只写正式文件和命令记录，第一轮完整作者源码未单独快照；该早稿在后续r1/修订前.wild中保留。启用快照后的rN保存当次WILD、设计和作者源码；后续快照另保留修订前效果图。这里不倒填或虚构早期文件。' if folder=='07-图书馆' else 'rN目录保留作者源码、设计与WILD；修订前文件和后期修订前效果图随快照保存。', '',
        '一次字节重放因Windows写盘CRLF与新检查代码LF不一致而失败；已把作者编译器的输出换行明确为CRLF，重放检查仍逐字节比较，正式文件未为过检查而改写。失败命令原样保留。', '',
        '## 命令原始记录', '', '| 开始时间（UTC+8） | 任务 | 退出码 | 原始输出 |', '|---|---|---|---|']
    for file,r in records:
        lines.append(f"| {r['started_at']} | {file.stem} | {r['exit_code']} | [{file.name}](命令记录/{file.name}) |")
    lines += ['', '## 最终状态', '', boundary, '', f"最终WILD SHA-256：`{audit['wild_sha256']}`。设计、实图、校验、剖切的来源一致性见交付关系核对。"]
    (base/'03-过程记录/流程日志.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    command=f"wild-server/.venv/Scripts/python.exe docs/10月22日/00-公共脚本/完成命名建筑交付.py docs/10月22日/{folder}"
    (base/'02-生成脚本/重建说明.md').write_text(f'''# 重建{name}

在仓库根目录运行（将重新生成本建筑、保存新快照并完成全部校验与实图）：

```powershell
{command}
```

只核对确定性，不改动WILD：

```powershell
wild-server/.venv/Scripts/python.exe docs/10月22日/00-公共脚本/编译命名建筑.py docs/10月22日/{folder}/01-需求与设计/DesignDocument.json --check
```

- [设计编写器](../../00-公共脚本/编写命名建筑设计.py)：当次需求、体量、功能与细部清单。
- [作者编译器](../../00-公共脚本/编译命名建筑.py)：材料、场地、壳体、室内、细部、文字和真实灯源的完整装配。
- [基本几何工具](../../00-公共脚本/构件作者工具.py)：box/wall/floor等基本构件。
- [交付核对](../../00-公共脚本/核对命名建筑.py) · [世界环境渲染](../../00-公共脚本/渲染命名建筑.mjs)

编译读取已保存的DesignDocument，不重新生成设计时间戳。历史修订源码见 ../03-过程记录/rN/；最终源码指纹见当日根目录命名建筑交付核对.json。
''',encoding='utf-8')
    deliveries.append(dict(folder=folder,name=name,wild=str(target.relative_to(DAY)),sha256=audit['wild_sha256'],
        site_size=size,element_count=n,component_count=c,light_sources=audit['real_lights'],
        project_error_steps=audit['project_error_steps'],project_warning_steps=audit['project_warning_steps'],
        reconstruction_warnings=audit['reconstruction_warnings'],baseline_context=render['contextSha256'],cuts=len(audit['cuts'])))

script_hashes={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in Path(__file__).parent.iterdir()
               if f.suffix in ['.py','.mjs'] and ('命名建筑' in f.name or f.name in ['构件作者工具.py','校验蓝图.py','运行建筑任务.py'])}
(DAY/'命名建筑交付核对.json').write_text(json.dumps(dict(deliveries=deliveries,author_script_sha256=script_hashes,
    reference_sha256=ref['inputSha256'],same_render_context=True),ensure_ascii=False,indent=2),encoding='utf-8')
comparison='''# 本次四栋命名建筑与汀院的同条件对照

汀院参考原件未修改，使用本次当前引擎重新渲染到 [汀院](汀院/perspective.png)。四栋正式文件与参考的baseline context SHA-256完全相同，包含相机规则、光照、源码摘要与浏览器版本；不能拿不同渲染条件的截图直接比较。

| 建筑 | 同条件透视 | 新增可见细化 |
|---|---|---|
| 汀院参考 | [查看](汀院/perspective.png) | 主楼/书房翼、透空格棚、泳池与玻璃露台 |
'''
    # 以下表格由已完成交付生成。
for d in deliveries:
    comparison+=f"| {d['name']} | [查看](../../{d['folder']}/05-效果图/perspective.png) | {NOTES[d['folder']][0]} |\n"
comparison+='''
已结合正面、侧面、俯视、透视、日夜、招牌近景与室内剖切查看：四栋的类型、入口、建筑层次、室内功能和招牌均有可见实体；实图反馈用于修正遮字、通路、池底和隔墙问题。不同建筑以适合用途的构造层次细化，不以构件数量排名，也不把“零错误”写作审美保证。

基线不包含编辑器的整套天空、天气与后期，因此另外保存复用生产材质、水面、环境贴图的世界环境日夜实图。基线固定外部地面为y=−0.02，会遮住下沉池内较低部分；泳池细节请查看别墅的世界环境water.png。
'''
(DAY/'00-质量参考/本次命名建筑对照/对照说明.md').write_text(comparison,encoding='utf-8')
print(json.dumps(deliveries,ensure_ascii=False,indent=2))
