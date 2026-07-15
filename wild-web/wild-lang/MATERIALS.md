# 原语材质系统 v1.0

本文档定义原语语言中所有材质和效果层的参数、语义及渲染规则。原语材质不依赖任何外部纹理文件，所有视觉属性都是精确的数值参数，由原语引擎编译为着色器参数，在所有合规客户端上渲染结果完全一致。

---

## 一、基础材质 (Base Material)

基础材质定义了表面在标准光照条件下的核心视觉属性。所有材质都从一组基础参数开始。

### 1.1 字段定义

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `baseColor` | [R, G, B] | 是 | 在标准光照 D65 正午下的漫反射色。范围 0.0–1.0 |
| `roughness` | number | 是 | 微观表面粗糙度，0.0（完全光滑）– 1.0（完全粗糙） |
| `metallic` | number | 是 | 金属度，0.0（非金属）– 1.0（完全金属） |
| `albedo` | number | 是 | 反照率，0.0–1.0。表面总反射率，默认 1.0 |
| `emissive` | [R, G, B] | 否 | 自发光颜色，范围 0.0–1.0。默认 `[0, 0, 0]` |
| `opacity` | number | 否 | 不透明度，0.0（全透明）– 1.0（完全不透明）。默认 1.0 |
| `lightingCondition` | string | 是 | 颜色对应的标准光照条件，固定值 `"D65_noon"` |

### 1.2 光照条件

`lightingCondition` 字段声明了 `baseColor` 是在何种光照条件下定义的。当前唯一合法值为：

| 值 | 说明 |
|----|------|
| `"D65_noon"` | CIE 标准日光 D65，正午（太阳位于天顶），无云遮挡 |

所有合规客户端在渲染时必须先使用标准光照模型（PBR 或 NPR）将实时光照（如黄昏暖光）计算为偏移量，再叠加到 `baseColor` 上。这样确保了标准光照下所有客户端渲染一致，而实际光照下各客户端按各自风格自动调整。

### 1.3 示例

```json
{
  "stone_wall": {
    "baseColor": [0.68, 0.65, 0.62],
    "roughness": 0.9,
    "metallic": 0.0,
    "albedo": 1.0,
    "emissive": [0, 0, 0],
    "opacity": 1.0,
    "lightingCondition": "D65_noon"
  }
}
二、效果层 (Effect Layers)
效果层叠加在基础材质之上，提供风化、苔藓、边缘磨损等表面变化。一个材质可以有零个或多个效果层，按数组顺序从前到后叠加。

每个效果层独立定义自己的视觉参数，所有参数均由创作者预设为固定值，不由客户端动态推断。

2.1 weathering — 风化与蒙尘
模拟长期暴露于自然环境中产生的表面变化。

字段	类型	必需	说明
type	string	是	固定值 "weathering"
dustColor	[R, G, B]	是	蒙尘的颜色，范围 0.0–1.0
dustOpacity	number	是	蒙尘覆盖强度，0.0–1.0
crackIntensity	number	是	裂纹强度，0.0（无裂纹）– 1.0（大量裂纹）
colorFade	number	是	褪色程度，0.0（无褪色）– 1.0（严重褪色）
示例：

json
{
  "type": "weathering",
  "dustColor": [0.3, 0.25, 0.2],
  "dustOpacity": 0.6,
  "crackIntensity": 0.15,
  "colorFade": 0.2
}
渲染说明：

dustColor 与基础 baseColor 按 dustOpacity 强度混合。

colorFade 使 baseColor 向灰色偏移（饱和度降低）。

crackIntensity 控制裂纹生成密度：
- **0.0–0.7**：表面色裂纹。裂纹颜色 = dustColor 加深 + 表面底色混合。仅影响着色，几何不变。
- **0.7–1.0**：几何贯穿型裂纹。当 `crackIntensity ≥ 0.7` 时，裂纹穿透材质厚度，在几何层面将构件沿随机平面切分为两块。裂纹断面露出 dustColor 加深后的颜色。该效果对薄片类构件（瓦片、砖块）尤其显著，整块可能裂为两半。

2.2 moss — 苔藓与植被覆盖
模拟潮湿环境中的苔藓、地衣或藤蔓生长。

字段	类型	必需	说明
type	string	是	固定值 "moss"
mossColor	[R, G, B]	是	苔藓的颜色，范围 0.0–1.0
coverage	number	是	覆盖率，0.0–1.0
pattern	string	是	分布模式，见下方枚举
pattern 枚举：

值	说明
"base_up"	从底部向上蔓延，覆盖底部区域
"patchy"	随机斑块
"edge"	沿边缘和缝隙生长
示例：

json
{
  "type": "moss",
  "mossColor": [0.22, 0.38, 0.15],
  "coverage": 0.3,
  "pattern": "base_up"
}
渲染说明：

mossColor 按 coverage 强度与基础表面颜色混合。

pattern 控制分布："base_up" 在建筑底部附近增强覆盖率；"patchy" 使用全局均匀的随机斑块。

2.3 edgeWear — 边缘磨损
模拟棱角处的磨损，露出底层的新鲜材质色。

字段	类型	必需	说明
type	string	是	固定值 "edgeWear"
wearColor	[R, G, B]	是	磨损处露出的底色，范围 0.0–1.0
intensity	number	是	磨损强度，0.0（无磨损）– 1.0（严重磨损）
示例：

json
{
  "type": "edgeWear",
  "wearColor": [0.6, 0.4, 0.2],
  "intensity": 0.3
}
渲染说明：

边缘检测基于网格的几何法线变化（梯度 > 阈值）。

wearColor 按 intensity 强度与边缘处表面颜色混合。

2.4 效果层叠加顺序

效果层按数组顺序从前到后叠加。此顺序是语言规范的一部分，所有合规引擎必须严格按照用户指定的数组顺序逐层叠加，不得重排、合并或跳过任何效果层。

合规引擎的责任是忠实地按顺序执行每层效果。用户应按照物理直觉组织顺序（如先风化再长苔藓、最后磨边），但语言的语义保证的是"顺序执行"而非"某种顺序更正确"。

完整材质示例（三层叠加）：

json
{
  "aged_stone": {
    "baseColor": [0.6, 0.58, 0.52],
    "roughness": 0.9,
    "metallic": 0.0,
    "albedo": 1.0,
    "lightingCondition": "D65_noon",
    "effects": [
      {
        "type": "weathering",
        "dustColor": [0.48, 0.45, 0.38],
        "dustOpacity": 0.6,
        "crackIntensity": 0.15,
        "colorFade": 0.2
      },
      {
        "type": "moss",
        "mossColor": [0.22, 0.38, 0.15],
        "coverage": 0.25,
        "pattern": "base_up"
      },
      {
        "type": "edgeWear",
        "wearColor": [0.68, 0.65, 0.6],
        "intensity": 0.3
      }
    ]
  }
}
三、嵌入式图像数据块 (Embedded Image)
对于不适合用体积砖块直接编码的复杂图像（如真实照片、手绘壁画），材质可包含一个不透明的图像数据块。此数据块不由原语引擎解析，而是由客户端原样映射到指定表面上。

3.1 字段定义
字段	类型	必需	说明
embeddedImage	object	否	嵌入式图像数据
embeddedImage.encoding	string	是	编码方式，固定 "base64"
embeddedImage.mimeType	string	是	MIME 类型（如 "image/png"）
embeddedImage.data	string	是	base64 编码的图像数据
3.2 示例
json
{
  "painted_mural": {
    "baseColor": [0.8, 0.75, 0.7],
    "roughness": 0.6,
    "metallic": 0.0,
    "albedo": 1.0,
    "lightingCondition": "D65_noon",
    "embeddedImage": {
      "encoding": "base64",
      "mimeType": "image/png",
      "data": "iVBORw0KGgoAAAANSUhEUg..."
    }
  }
}
3.3 渲染说明
客户端将嵌入式图像解码后映射到构件的指定表面上。

图像作为不透明数据块，不由原语引擎解析。

使用此方式会损失风格化能力（不同客户端无法重绘图像），仅作为兜底方案。

体积砖块携带体素 RGBA 时，优先使用体积砖块的原生颜色表达。

四、标准光照模型
所有合规客户端在渲染基础材质时，必须以 baseColor 在 D65_noon 光照下为基准。实时光照（如黄昏暖光、夜晚月光）作为偏移量叠加到 baseColor 上，以确保所有客户端在标准光照下渲染一致，在实时光照下按各自客户端的渲染风格自然偏移。

五、版本兼容
本文件定义的所有材质字段和效果层类型均为 v1.0 标准。未来版本可能增加新的效果层类型、新字段或新的 pattern 枚举值，但不会删除或修改任何已有定义。v1.0 中合法的材质在 v2.0 中继续有效且语义不变。

许可
本材质系统定义以 MIT 协议开源。任何原语引擎实现可自由引用本文档定义的材质参数和语义。