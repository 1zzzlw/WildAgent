# 核心资料与能力边界

快照日期：2026-10-23，已同步楼板孔洞、扫掠端盖及共享展示渲染。复制内容来自本地当前工作树，可能包含尚未提交的实现；以文件SHA-256识别，不假称正式发布版本。逐文件来源见 [核心源码来源](../验证与来源/核心源码来源.json)。快照不会随项目自动更新。

## 实际包含

| 目录 | 内容 | 是否可以独立运行 |
| --- | --- | --- |
| [wild-core](wild-core/package.json) | 完整src、types.ts、schema.json、package/lock、tsconfig.json | 含Earcut三角剖分依赖；先安装Core依赖，TS通过随包Vite加载 |
| [wild-web](wild-web/package.json) | 几何显示、材质、文字、水、共享光照/环境/后期及其相对导入闭包；检查/四视图脚本 | 安装依赖并提供Chromium后可运行固定基线或展示模式；不含Vue编辑器及完整交互 |
| [设计契约](wild-server/app/design/contracts.py) | 当前DesignDocument后端模型 | 源码参考；需Pydantic等完整项目环境才可接入后端，不是独立服务 |
| [设计编译边界](wild-server/app/design/compilation.py) | compile_document与project_drawing的原始边界 | 源码参考；其相对依赖未全量打包，不能单独执行 |

`wild-core`和上述渲染源码/两份脚本均原样复制。`wild-web/package.json`、lock和包外独立检查器是本次新建的运行包装；依赖锁定为本机实际验证的版本。快照来源清单不把新包装伪装成原项目文件。

## 查什么文件

- 格式和枚举：[schema.json](wild-core/schema.json)。它是Draft2020-12；纯文本指南是它的常用创作子集，不是新DSL。
- 字段语义：[types.ts](wild-core/types.ts)。类型注释可能保留历史版本文字，实际结合Schema与实现判断。
- 解析与归一：[parser.ts](wild-core/src/primitive/parser.ts)。它会兼容部分简写、将1.1归一1.0；作者仍应输出规范形式，不依赖自动猜错坐标。
- 组合编译：[compiler/index.ts](wild-core/src/compiler/index.ts)、[附墙坐标](wild-core/src/compiler/components/attachedToWall.ts)。
- 几何：[floor](wild-core/src/primitive/geometry/floor.ts)、[stair](wild-core/src/primitive/geometry/stair.ts)、[roof](wild-core/src/primitive/geometry/roof.ts)、[primitive](wild-core/src/primitive/geometry/primitive.ts)。
- 吸附/接头/开口：[resolver.ts](wild-core/src/primitive/resolver.ts)。
- 真实显示：[renderEntity](wild-web/src/renderer/renderEntity.ts)、[materialAdapter](wild-web/src/renderer/materialAdapter.ts)、[textLabel](wild-web/src/renderer/textLabel.ts)、[waterSurfaceMaterial](wild-web/src/renderer/waterSurfaceMaterial.ts)。

## 设计和执行的边界

```text
AI依据需求作设计
  → 直接输出完整WILD，或用作者脚本展开
  → 原始Schema / 引用与尺寸检查
  → parseBlueprint / compileBlueprintComponents
  → reconstructEntity（网格/材质/包络）
  → renderEntity / materialAdapter
  → Chromium WebGL四视图
  → 实际看图、关系复核和修订
```

图中步骤都要按实际执行报告。包内静态工具在Core归一前检查原始JSON，避免自动纠错掩盖作者错误。Core能把组件展开成网格，不负责设计空间或生成施工图。

原项目另有正式DesignDocument→任务规划/执行→编译的Agent流程；本包不要求接入。`project_drawing`只绘设计示意，不运行WILD编译器；正式`compile_document`要调用完整后端。作者脚本读取`authoring`扩展是本批显式装配策略，不意味着任意DesignDocument额外字段都会被通用编译器执行。

## 当前不应扩张承诺的能力

- 原语仅box、sphere、cylinder、profile_sweep；没有公开的任意三角网格/通用布尔字段。楼板孔靠拆板。
- 当前部分屋面/曲面是外观表达；原生gable/hip内部不能自动当作空心阁楼。profile_sweep不自动生成端盖。
- 本包基线显示透射材质、招牌和光源，但没有完整编辑器的天空环境、后期和UI。案例日夜/图片参考图使用其各自记录的更丰富显示环境，不能认为基线一条命令会复现所有图片效果。
- 水面不是流体仿真或场景SSR；局部光源不投影，不能保证真实遮挡光照。
- 动画字段支持不等于新建筑的逐帧专项验收；本包教学图是静态图。
- 完整后端屋面检查曾对老虎窗、多段木构承托、原语梁柱和露天护墙有识别边界。保留问题，不能复制一个“全绿”结论用于所有新稿。
- 几何接触、净空采样和实际图不能替代结构/消防/无障碍/设备/施工审查。

复制整个资料包即可带走相对依赖。不要只复制`renderEntity.ts`，它依赖材质、文字、世界材质状态和Core。不要手改快照某处后仍沿用旧来源hash；需要变更时另记录版本和本次修改，并重新检查示例。
