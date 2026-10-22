"""汇总真实命令、快照、源文件和实图指纹；不改写任何旧失败记录。"""
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2];DAY=ROOT/'docs/10月22日'
NOTES={
 '11-图片复建-石光庭院':(
  '右高左低的体量、两层各四组高窗、右侧两扇竖窗、木饰单层翼、玻璃露台、屋顶绿化、四片方锥天窗和六级宽阶。',
  '初稿的左右关系与参考视角相反，已把设计volumes和输出模型同时镜像X并修订相机；文字保持正常阅读。首轮天窗误用了整栋屋顶语义，改为三边圆柱形成的四片薄三角玻璃，并补洞口框梁与基座。修正木饰共面、基座与庭院板重叠，细化低矮地被与林冠。',
  '最终Schema、后端全流水线、Core编译/重建与前端重建均零错误零警告。'),
 '12-图片复建-ForestCafe':(
  '三层退台、左侧Forest / Cafe / Cafe标识墙、细框转角玻璃、右侧18级室外楼梯、白色斜顶矮墙、黑色露台栏杆、叠片深檐、藤蔓与暖光。',
  '首轮补齐标识塔上部侧墙，避免屋顶下方出现无意缺口；修正腰线共面。英文牌改薄至6毫米并贴近墙面；藤蔓改成非等距的叶簇。露台椅子沿宽度摆放，核对全部脚点在实际板内；首批露台花盆上移到对应楼层。拉远相机，补街角道路和路缘石。',
  '全图无错误；后端保留外楼梯矮墙连接识别和“墙顶未盖屋顶”两组警告，前端保留外侧矮墙超出roof包围框的提示。矮墙本来露天，不能为了消警告给参考图的室外楼梯加屋顶。核对报告记录斜墙与平台墙1毫米交叠、防护高度0.9米、平台深2.44米及接门区间；未修改校验器。'),
}
deliveries=[]
for folder,(features,changes,boundary) in NOTES.items():
    base=DAY/folder;target=next(base.glob('*.wild'));raw=target.read_bytes();bp=json.loads(raw)
    doc=json.loads((base/'01-需求与设计/DesignDocument.json').read_text(encoding='utf-8'));p=doc['decisions']['authoring']
    audit=json.loads((base/'04-校验/设计落实与交通复核.json').read_text(encoding='utf-8'))
    baseline=json.loads((base/'05-效果图/render_manifest.json').read_text(encoding='utf-8'))
    photo=json.loads((base/'05-效果图/参考视角/photo-render-manifest.json').read_text(encoding='utf-8'))
    sha=hashlib.sha256(raw).hexdigest();assert sha==audit['source_sha256']==baseline['inputSha256']==photo['inputSha256']
    assert not audit['project_error_steps'] and not audit['runtime_errors']
    if p['recipe']=='stone':assert not audit['project_warning_steps'] and not audit['renderer_warnings']
    cuts=[]
    for cut in audit['cuts']:
        path=base/cut['path'];manifest=json.loads((path.parent/'效果图/render_manifest.json').read_text(encoding='utf-8'))
        assert manifest['inputSha256']==cut['sha256'] and manifest['compileErrors']==manifest['reconstructErrors']==0
        cuts.append(f"- [{path.parent.name}查看]({cut['path'].replace(' ','%20')}) · [俯视实图]({path.parent.relative_to(base).as_posix()}/效果图/top.png)")
    records=[(f,json.loads(f.read_text(encoding='utf-8'))) for f in (base/'03-过程记录/命令记录').glob('*.json')]
    records.sort(key=lambda item:item[1]['started_at'])
    assert any('字节重放' in f.name and r['exit_code']==0 and 'replay_identical' in r['stdout'] for f,r in records)
    name=p['name'];size=round(audit['site_size_m'][0])
    more='[立面近景](05-效果图/参考视角/facade-detail.png)' if p['recipe']=='stone' else '[暖光黄昏](05-效果图/参考视角/warm-evening.png)'
    readme=f'''# {name} · 图片复建

正式文件：[{target.name}]({target.name.replace(' ','%20')})

{features}

推定地块{size}×{size}米，层高{p['height']}米。参考没有标尺，背面、室内和隐蔽交通由本次设计补齐；这些推定已与图片可见事实分开记录。

## 看实际效果

- [参考方向日景](05-效果图/参考视角/reference-day.png) · [同方向夜景](05-效果图/参考视角/reference-night.png) · {more}
- [正面](05-效果图/front.png) · [侧面](05-效果图/side.png) · [俯视](05-效果图/top.png) · [标准透视](05-效果图/perspective.png)
{chr(10).join(cuts)}

全部图片来自本项目真实Chromium/WebGL渲染。参考方向图复用生产Core、材质、天空和IBL，使用4096太阳阴影；没有用AI图片、照片贴片或后期修图替代建筑几何。密集林冠、照片背景和镜头景深仍与原图有差距。

## 文件与过程

- [图片拆解与设计](01-需求与设计/图片拆解与设计.md) · [DesignDocument](01-需求与设计/DesignDocument.json) · [主体设计投影](01-需求与设计/主体投影.json)
- [重建方式](02-生成脚本/重建说明.md) · [创建日志](03-过程记录/流程日志.md)
- [最终项目校验](04-校验/最终项目校验.json) · [照片特征、交通及来源核对](04-校验/设计落实与交通复核.json)

设计先保存为当前项目DesignDocument，再以独立、确定性的图片作者脚本展开WILD；project_drawing只做主体投影，不冒充详细成品编译。没有运行Agent、RAG或外部模型API，也没有改引擎为某栋建筑增加特例。每轮保留设计、作者脚本、几何工具和WILD，原始失败报告不删除。

## 验证边界

{boundary}

Core编译/重建错误0，未映射材质0，真实浏览器运行时错误0。逐层副本只删遮挡项，保留构件逐项不变，分别通过Schema与Core重建并实际渲染；它们用于查看，不能拿去顶后的屋面检查代替正式文件结论。最终作者编译字节重放一致。楼梯复核包括完整梯宽支承、楼板洞口面积和2米净空采样，并非结构承载或规范认证。
'''
    (base/'README.md').write_text(readme,encoding='utf-8')
    log=['# '+name+'图片复建流程','','## 来源与执行','','来源是用户本轮上传的对应图片；工具没有提供原图本地路径，未伪造保存原图。','',
         '图片拆解 → DesignDocument → 作者装配 → 只读校验 → 真实参考视角看图 → 修订 → 完整四视图 → 交通核对 → 逐层剖切 → 字节重放。','',
         '## 真实修订','',changes,'','各rN目录均是当时实际生成时保存，包含当轮WILD、设计输入、作者源码和几何工具。后续修订保留先前WILD；已有标准四视图后，也会连同修订前实图保存。未发生的验证没有补写成成功记录。','',
         '## 原始命令','','| 开始时间（UTC+8） | 任务 | 退出码 | 完整输出 |','|---|---|---|---|']
    log += [f"| {r['started_at']} | {f.stem} | {r['exit_code']} | [{f.name}](命令记录/{f.name}) |" for f,r in records]
    log += ['','## 最终状态','',boundary,'',f'正式WILD SHA-256：`{sha}`。','',
            '参考方向图与标准四视图各有manifest，均绑定正式文件哈希；本次交付核对记录源代码指纹。审美对照依据实际看图，不把零错误等同于照片效果。']
    (base/'03-过程记录/流程日志.md').write_text('\n'.join(log)+'\n',encoding='utf-8')
    command=f'wild-server/.venv/Scripts/python.exe docs/10月22日/00-公共脚本/完成图片复建.py docs/10月22日/{folder}'
    (base/'02-生成脚本/重建说明.md').write_text(f'''# 重建说明

在仓库根目录按已保存设计重新编译、校验、真实渲染与字节重放：

```powershell
{command}
```

只读核对字节：

```powershell
wild-server/.venv/Scripts/python.exe docs/10月22日/00-公共脚本/编译图片复建.py docs/10月22日/{folder}/01-需求与设计/DesignDocument.json --check
```

重新制作剖切，再渲染剖切：

```powershell
wild-server/.venv/Scripts/python.exe docs/10月22日/00-公共脚本/核对图片复建.py docs/10月22日/{folder}
wild-server/.venv/Scripts/python.exe docs/10月22日/00-公共脚本/渲染图片剖切.py docs/10月22日/{folder}
```

可复查的完整源码：[设计编写器](../../00-公共脚本/编写图片复建设计.py)、[作者编译器](../../00-公共脚本/编译图片复建.py)、[基本几何工具](../../00-公共脚本/构件作者工具.py)、[真实参考视角渲染](../../00-公共脚本/渲染图片复建.mjs)、[设计与交通复核](../../00-公共脚本/核对图片复建.py)。首次设计与历史改稿见本目录rN快照，不需要再次调用模型。
''',encoding='utf-8')
    deliveries.append(dict(name=name,file=target.relative_to(DAY).as_posix(),sha256=sha,design_sha256=audit['design_sha256'],
        elements=len(bp['geometry']['elements']),components=len(bp['geometry']['components']),site_size=audit['site_size_m'],
        project_error_steps=audit['project_error_steps'],project_warning_steps=audit['project_warning_steps'],renderer_warnings=audit['renderer_warnings'],
        geometry_evidence=audit['features'],cuts=len(cuts),runtime_errors=[]))
scripts={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in HERE.iterdir() if '图片' in f.name and f.suffix in ['.py','.mjs']}
(DAY/'图片复建交付核对.json').write_text(json.dumps(dict(deliveries=deliveries,author_script_sha256=scripts),ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(deliveries,ensure_ascii=False,indent=2))
