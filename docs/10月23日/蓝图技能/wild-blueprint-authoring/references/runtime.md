# 工具、环境与验证边界

所有相对路径以技能根目录为基准。`references/blueprint-kit`保留原资料包结构，Core、检查器与必要渲染依赖均在其内部；工具按自身位置定位，不依赖E盘或原仓库。

## 安装与执行

选择已有Python3.10+解释器，优先使用任务自己的虚拟环境；Node22.12+，Chrome/Chromium单独提供。只在准备执行对应工具时安装其依赖，不为纯文本输出启动环境：

```powershell
python -m pip install -r "references/blueprint-kit/工具/requirements.txt"
npm ci --prefix "references/blueprint-kit/核心资料/wild-core" --ignore-scripts --no-audit --no-fund
npm ci --prefix "references/blueprint-kit/核心资料/wild-web" --ignore-scripts --no-audit --no-fund
```

首次安装需要网络或本机缓存，浏览器和node_modules不随技能分发。Node依赖固定在包内lock，Core是相对本地依赖。没有模型API、RAG或完整后端安装步骤。

```powershell
python "scripts/check_wild.py" "交付目录/建筑.wild" --report "交付目录/静态检查.json"
node "scripts/validate_core.mjs" "交付目录/建筑.wild"
node "scripts/render_preview.mjs" "交付目录/建筑.wild" "交付目录/四视图" "C:/本机路径/chrome.exe"
```

可从任意工作目录以脚本绝对路径调用；输入/输出相对路径仍相对该次命令的工作目录。含空格的路径加引号。渲染入口必须提供输入和输出目录；浏览器可由第三个位置参数或CHROMIUM_PATH指定，优先显式给路径，不假定其他机器有本机的Playwright缓存。

Windows若Node子进程因缺少SystemRoot/WINDIR而触发加密初始化错误，恢复为本机真实Windows目录后再执行；不要调整建筑参数。Python读写/命令记录用UTF-8，控制台编码问题与生成失败分别归因。

确认是该环境缺失时，PowerShell可对当前进程设置`$env:SystemRoot=[Environment]::GetFolderPath('Windows')`及`$env:WINDIR=$env:SystemRoot`后重试。不要永久改用户环境，也不要对其他Node错误套用此修复。

## 每个工具证明什么

| 工具 | 执行范围 | 不覆盖 |
| --- | --- | --- |
| check_wild.py | 原始JSON/Schema、ID/直接材质/宿主引用、直墙开口范围、墙尺寸及显式楼梯尺寸链 | 模板展开、全碰撞、空间可达与画面 |
| validate_core.mjs | 真实Core解析、组件编译、网格重建、有限包络/顶点及诊断 | 完整项目后端、真实浏览器画面 |
| render_preview.mjs | 真实Chromium/WebGL，共享编辑器曝光/环境/阴影/后期、局部灯和主水位反射；四视图与manifest | 完整Vue编辑器、天气/内置景观实体、全交互、自动视觉评审 |

Core会兼容归一部分输入，因此原始Schema检查仍有价值。必须检查命令退出码和报告原文；警告不能省略，出图后必须实际查看。默认展示模式可追加--time=day/sunset/night及--quality=low/medium/high；地面位于模型最低处之下。加--baseline才使用原固定几何基线，其地面在−0.02m且没有完整环境/后期，可能挡住下沉池。水面近景、灯光遮挡和门窗动画按任务另验，不能用四张静态图替代。

## 有原WildAgent项目时

先核对当前Schema/类型/编译入口与快照是否一致。优先使用项目当前只读校验与真实显示入口，避免拿过时快照解释已变更功能。正式DesignDocument、Agent和后端完整关系检查只能在原项目具备相应运行环境时使用；本技能只携带相关契约参考，不能独立运行整个后端。

项目代码修复不是创作任务的默认操作。若缺陷明确来自引擎且用户授权修复，沿现有共享入口处理通用根因；单栋作者文件的错误应先修作者设计/参数。不能改校验器来让当前建筑通过。

`DesignDocument.model_validate`只证明设计契约成立。若专用作者脚本消费`decisions`中的扩展布局，要记录实际消费者及设计hash；不能声称后端通用编译器也支持该字段，或把Pydantic通过写成Agent已运行。

## 原始字段与空间复核

先查原始Schema，再进Core，避免兼容归一掩盖错误。当前`primitive.shape=cylinder`的半径写法是`radius`与`radiusTop`+`radiusBottom`二选一；同时写两组违反`oneOf`。`primitive.label`仅有`text/color/fontFamily`，不要推测`fontSize`等显示字段。

空间复核按本稿风险选取：实际重建包络与完整地块比较；泳池/中庭检查所有覆盖层的孔；通行从可达入口到功能空间，计入门框净宽和家具/柜体/固定玻璃。近似网格检查须写明步长、身体半径、门按开启还是关闭处理，以及未覆盖的开门扫掠/人体碰撞。一次案例的0.2m采样不是通用精度要求，更不是建筑规范。

具体失败证据与修订前提见[独立创作验证复盘](independent-authoring.md)。这些检查补充Schema/Core，不将所有作品强制改成该例的平面或设施。

## 记录与修订

文件创作先保存设计事实，展开前后保留作者输入和正式文件。命令记录至少包含command/cwd/起止时间/exit_code/stdout/stderr；文件指纹将设计、校验、实图对应到同一稿。重要修订保留旧WILD和原始失败输出，JSON使用一致序列化/换行以便重放。

剖切只删除遮挡对象，宿主移除时同步处理依附件；记录源hash和删除ID，保留对象与正式文件逐项一致。剖切造成的缺屋面/上层板关系不能改写为完整建筑失败，也不能拿剖切图冒充正式文件内部已无问题。

缺执行条件时先完成可独立进行的设计/输出，准确说明未执行的层级。重复失败先根据原始错误定位环境、字段或空间关系，不循环调用模型、盲目重装或不断增加重试。没有实际出图/看图的成果不能写成已经完成视觉验收。

## 资料与案例

[原工具说明](blueprint-kit/工具/README.md)保留更完整的包内命令和教学重放方法。技能附带原整包审计工具，维护者需要核对快照/案例时可按其说明运行；每次建筑创作不要求重审十二例，也不要运行“整理资料包.py”覆盖原资料。

主语言与十二例是固定参考快照。新建筑写到任务交付目录；用户要求更新技能/语言时才修改本技能文件。已有例子的真实图和报告只证明原文件及原设置，不证明新模型盲测或新建筑质量。
