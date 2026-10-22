# 检查、重建与真实出图

以下命令都在**资料包根目录**（即含主语言的目录）执行。源码使用包内相对路径；不需要原项目的E盘路径、Python虚拟环境或模型配置。环境：Python3.10+，Node22.12+，可运行的Chromium/Chrome。已实测Node22.21.1、jsonschema4.26.0、Vite8.1.4、Three0.160.1；原始浏览器版本在渲染清单中。

## 1. Python只读检查

首次安装依赖：

```powershell
python -m pip install -r "工具/requirements.txt"
```

检查一份或多份文件：

```powershell
python "工具/检查WILD.py" "示例/听风茶室.wild" --report "验证结果/静态检查.json"
```

工具实际检查：严格JSON数字、原始Schema、重复ID、直接元素/组件的显式材质引用、宿主引用、直墙开口范围、墙尺寸、显式楼梯N×步高/步深。原文件只读；输出sha256、errors、warnings；有错误退出码1，否则0。它没有展开模板，没有做全碰撞/可达性/美观检查；曲墙、嵌套灯body等由Core再检查。省略的可选材料可能由编译器默认值补充，不是本工具证明已显式定义。

## 2. 安装随包Node运行依赖

```powershell
npm ci --prefix "核心资料/wild-web" --ignore-scripts --no-audit --no-fund
```

`wild-core`使用`file:../wild-core`，Vite与Three版本固定，lock已附带。首次安装需要npm网络或本机缓存；运行示例不需联网资产。依赖安装在包内核心资料/wild-web/node_modules，不要将它当成应发送给大模型的资料或分发到压缩包。

## 3. Core编译与重建

```powershell
node "核心资料/wild-web/scripts/validate-generated.mjs" "示例/听风茶室.wild"
```

它使用原项目Core解析、组件展开和真实网格重建，输出诊断、网格数量、材质数、包络、有限值检查；不是浏览器渲染。原始脚本会做输入归一，所以前一步的原始Schema检查仍有价值。

## 4. Chromium/WebGL真实四视图

```powershell
node "核心资料/wild-web/scripts/render-baseline.mjs" "示例/听风茶室.wild" "验证结果/四视图" "C:/你的路径/chrome.exe"
```

第三个参数必须换成本机浏览器可执行文件路径，或用环境变量CHROMIUM_PATH；不填时原脚本采用其历史Windows默认位置，别假设别的电脑也有该路径。输出目录显式传入，不使用原脚本的项目默认输出目录。可使用绝对WILD路径；含空格路径加引号。

Linux/macOS同样显式给浏览器路径；命令本身是跨平台Node程序。本次独立运行验证发生在Windows，未另做Linux/macOS实测。Windows子进程若缺少SystemRoot/WINDIR引发Node加密初始化失败，恢复为该机器真实Windows目录；不要把固定C盘路径当跨平台要求。

输出front/side/top/perspective.png与render_manifest.json，包含输入hash、引擎/显示摘要、浏览器版本、网格/材质、错误数。请实际打开图片。固定地面位于−0.02m、固定背景/灯光，不包含完整编辑器的天空/后期；下沉池体可能受外部地面遮挡。需要环境水面/夜景/特定相机时使用完整项目显示能力并另存设置，不能误说基线已验证这些场景。

脚本使用独立临时浏览器profile和本地Vite服务器，不连接用户现有浏览器。部分系统会保留临时profile；按机器自身临时目录策略处理，不随包发送。工具没有自动启动模型、RAG或Agent。

## 5. 教学例的确定性展开

```powershell
python "示例/展开最小茶室.py" --output "验证结果/重放.wild"
```

固定输出格式UTF-8/LF，脚本没有时间戳和随机数。逐字节比较该文件与示例/听风茶室.wild以检查重放。它只会建一个教学茶室，不是通用自然语言建筑生成器。

## 6. 仅资料包维护者使用

`整理资料包.py --project-root <原项目根>`读取项目并复制Core/必要渲染模块，按正式WILD建立十二例索引、案例副本和来源hash；它依赖完整原项目。**创作新建筑不需要运行它。** 它会更新本包同名快照/索引，故只在明确需要刷新资料包时运行，不在每次生成前运行。

`核对资料包.py`用于本包内部链接、JSON示例、来源hash和独立检查器的有限反例回归。执行方法见验证说明；它也不设计建筑。

## 7. 需要完整项目的可选验证

本包没有完整后端关系检查、Agent任务图和全部专用日夜渲染脚本。若有原项目，可运行其中`校验蓝图.py`的Schema+pipeline(auto_fix=False)，再补楼板面积/交通/承托等关系检查。命令、解释器和目录以项目当前入口为准，不能把本包可运行Core误说成后端18项已经执行。

剖切只删遮挡层，宿主被删时同步删依附组件，保留对象逐项与正式文件一致；副本的“缺屋面/缺上层承托”报告按删除范围解释。不要调用旧脚本里的固定楼层高阈值处理所有建筑。
