/**
 * 原语语言规范 v1.0 — TypeScript 类型定义
 * 
 * 本文件提供原语蓝图的完整类型定义，供引擎实现和编辑器开发者参考。
 * 语言规范 (SPEC.md) 为唯一权威来源，本文件仅为辅助工具。
 */

// ========== 基础向量与颜色 ==========

/** 三维向量 [x, y, z] */
export type Vec3 = [number, number, number];

/** RGB 颜色值，范围 0.0–1.0 */
export type Color = [number, number, number];

/** 路径曲线类型（用于 wall、beam 等线性构件） */
export type CurveSegment = LineCurve | ArcCurve | EllipseCurve | CatenaryCurve;

export interface LineCurve { type: 'line' }
export interface ArcCurve {
  type: 'arc';
  center: Vec3;
  /** 扫过角度（度），正值逆时针 */
  sweep: number;
  /** 分段数，默认 24 */
  segments?: number;
}
export interface EllipseCurve {
  type: 'ellipse';
  center: Vec3;
  radiusX: number;
  radiusZ: number;
  startAngle?: number;
  sweep?: number;
  segments?: number;
}
export interface CatenaryCurve {
  type: 'catenary';
  /** 拱起高度（米） */
  rise: number;
  segments?: number;
}

/** 所有几何构件的联合类型 */
export type GeometryElement =
  | WallParams
  | FloorParams
  | ColumnParams
  | BeamParams
  | RoofParams
  | OpeningParams
  | StairParams
  | FurnitureParams
  | DenseBrickParams
  | BodyParams
  | PrimitiveParams;

/**
 * 组合构件不是新的渲染原语。它们会在进入 wild-core 前被编译为
 * GeometryElement[]，因此 renderer 不需要为 door/window/railing 注册 builder。
 */
export type ComponentSpec = (
  | DoorComponent
  | WindowComponent
  | RailingComponent
  | CanopyComponent
  | BalconyComponent
  | RampComponent
  | BayWindowComponent
  | CorniceComponent
  | ChimneyComponent
  | LightComponent
) & {
  /** 编辑器中是否允许通过三轴控件拖动；关闭时只允许属性面板编辑。 */
  draggable?: boolean;
};

/** 门窗静态蓝图中持久化的交互配置；实际动画进度只存在于前端运行时。 */
export interface OpeningInteractionSpec {
  mode: 'swing' | 'slide';
  hingeSide?: 'left' | 'right';
  /** swing 模式的最大开角，单位为度。 */
  openAngle?: number;
  /** slide 模式的位移，单位为米；省略时按构件宽度计算。 */
  openDistance?: number;
  initiallyOpen?: boolean;
}

/** 编译器写入基础元素、Core 透传给 renderer 的内部交互描述。 */
export interface OpeningElementBehavior {
  kind: 'opening';
  mode: 'swing' | 'slide';
  pivot: Vec3;
  closedPosition: Vec3;
  closedRotation: Vec3;
  openRotation?: Vec3;
  openOffset?: Vec3;
  initiallyOpen: boolean;
}

/** 灯具静态蓝图中持久化的光源参数；右键循环状态只存在于前端运行时。 */
export interface LightComponent {
  type: 'light';
  id: string;
  position: Vec3;
  /** 灯具业务外观；与 point/spot 光源算法分开表达。 */
  fixtureType?: 'bulb' | 'table_lamp';
  lightType?: 'point' | 'spot';
  color?: Color;
  lowIntensity?: number;
  highIntensity?: number;
  distance?: number;
  /** 聚光灯锥角，单位为度。 */
  angle?: number;
  initiallyOn?: boolean;
  bulbRadius?: number;
  baseHeight?: number;
  height?: number;
  shadeRadius?: number;
  material?: string;
  baseMaterial?: string;
  shadeMaterial?: string;
}

/** 编译器写入灯泡网格、Core 透传给 renderer 的灯光交互描述。 */
export interface LightElementBehavior {
  kind: 'light';
  lightType: 'point' | 'spot';
  color: Color;
  lowIntensity: number;
  highIntensity: number;
  distance: number;
  angle: number;
  initiallyOn: boolean;
}

export type InteractiveElementBehavior = OpeningElementBehavior | LightElementBehavior;

export interface DoorComponent {
  type: 'door';
  id: string;
  parentWall: string;
  /** [沿父墙距离, 底部世界 Y, 墙体法向偏移] */
  from: Vec3;
  width: number;
  height: number;
  frameWidth?: number;
  frameDepth?: number;
  frameMaterial?: string;
  leafMaterial?: string;
  interaction?: OpeningInteractionSpec;
}

export interface WindowComponent {
  type: 'window';
  id: string;
  parentWall: string;
  /** [沿父墙距离, 底部世界 Y, 墙体法向偏移] */
  from: Vec3;
  width: number;
  height: number;
  frameWidth?: number;
  frameDepth?: number;
  verticalMullions?: number;
  horizontalMullions?: number;
  frameMaterial?: string;
  glassMaterial?: string;
  interaction?: OpeningInteractionSpec;
}

export interface RailingComponent {
  type: 'railing';
  id: string;
  /** 栏杆基线的世界坐标路径，允许水平或随楼梯升降。 */
  path: Vec3[];
  height: number;
  postSpacing?: number;
  postRadius?: number;
  railRadius?: number;
  /** 横杆相对栏杆高度的比例，范围 (0, 1]，默认只有顶部扶手。 */
  railLevels?: number[];
  material?: string;
  /** 指定后，path 使用父楼板左下角和顶面作为局部原点。 */
  parentFloor?: string;
}

export interface CanopyComponent {
  type: 'canopy';
  id: string;
  parentWall: string;
  /** [沿父墙距离, 安装高度, 墙体法向偏移] */
  from: Vec3;
  width: number;
  depth: number;
  thickness: number;
  supportCount?: number;
  supportSize?: number;
  material?: string;
  supportMaterial?: string;
}

export interface BalconyComponent {
  type: 'balcony';
  id: string;
  parentWall: string;
  /** [沿父墙距离, 楼板顶面高度, 墙体法向偏移] */
  from: Vec3;
  width: number;
  depth: number;
  slabThickness: number;
  railingHeight?: number;
  postSpacing?: number;
  material?: string;
  railingMaterial?: string;
}

export interface RampComponent {
  type: 'ramp';
  id: string;
  from: Vec3;
  to: Vec3;
  width: number;
  thickness: number;
  railingSides?: 'none' | 'left' | 'right' | 'both';
  railingHeight?: number;
  postSpacing?: number;
  material?: string;
  railingMaterial?: string;
  /** 指定后，from/to 使用父楼板左下角和顶面作为局部原点。 */
  parentFloor?: string;
}

export interface BayWindowComponent {
  type: 'bay_window';
  id: string;
  parentWall: string;
  /** [沿父墙距离, 窗洞底部高度, 墙体法向偏移] */
  from: Vec3;
  width: number;
  height: number;
  projectionDepth: number;
  frameWidth?: number;
  frameDepth?: number;
  frameMaterial?: string;
  glassMaterial?: string;
}

export interface CorniceComponent {
  type: 'cornice';
  id: string;
  path: Vec3[];
  profile: Array<[number, number]>;
  closedProfile?: boolean;
  material?: string;
  /** 指定后，path 使用屋顶中心和计算后的屋面高度作为局部坐标。 */
  parentRoof?: string;
}

export interface ChimneyComponent {
  type: 'chimney';
  id: string;
  position: Vec3;
  width: number;
  depth: number;
  height: number;
  wallThickness?: number;
  capHeight?: number;
  material?: string;
  capMaterial?: string;
  /** 指定后，position 使用屋顶中心和计算后的屋面高度作为局部坐标。 */
  parentRoof?: string;
}

// ========== 几何构件 ==========
export interface WallParams {
  type: 'wall';
  id: string;
  from: Vec3;
  to: Vec3;
  thickness: number;
  material?: string;
  /** 路径曲线。不指定为直线。单段对象或多段数组 */
  curve?: CurveSegment | CurveSegment[];
  /** 内部使用：开孔信息（由resolver填充） */
  _cutouts?: Array<{
    localX: number;
    localY: number;
    localW: number;
    localH: number;
  }>;
}

export interface FloorParams {
  type: 'floor';
  id: string;
  from: Vec3;
  to?: Vec3;
  thickness: number;
  material?: string;
  /** "rect"（默认）或 "circle" */
  shape?: 'rect' | 'circle';
  /** 圆形半径，shape="circle" 时必需 */
  radius?: number;
  /** 圆形分段数，默认 32 */
  segments?: number;
}

export interface ColumnParams {
  type: 'column';
  id: string;
  base: Vec3;
  height: number;
  bottomRadius: number;
  topRadius: number;
  style: 'doric' | 'ionic' | 'corinthian' | 'modern' | 'chinese_wooden';
  flutes?: number;
  entasis?: number;
  inclination?: number;
  material?: string;
}

export interface BeamParams {
  type: 'beam';
  id: string;
  from: Vec3;
  to: Vec3;
  crossSection: 'rect' | 'circular' | 'i-beam';
  width: number;
  height: number;
  material?: string;
  /** 路径曲线。不指定为直线 */
  curve?: CurveSegment | CurveSegment[];
}

export interface RoofParams {
  type: 'roof';
  id: string;
  roofType: 'gable' | 'hip' | 'dome' | 'flat' | 'chinese_curved' | 'chinese_pagoda';
  span: number;
  depth: number;
  height: number;
  thickness: number;
  eaveCurveHeight?: number;
  curveProfile?: string;
  /** 重檐层数（chinese_pagoda），默认 3 */
  tiers?: number;
  /** 每层垂直高度，默认 height/tiers */
  tierHeight?: number;
  /** 每层出檐外挑量（米），默认 0.5 */
  eaveOutset?: number;
  /** 每层缩比 0-1，默认 0.7 */
  shrinkFactor?: number;
  position?: Vec3;
  material?: string;
}

// 墙体开口与覆盖面；门窗开合由组合组件的 interaction 编译为运行时行为。
export interface OpeningParams {
  type: 'opening';
  id: string;
  parentWall: string;
  from: Vec3;
  width: number;
  height: number;
  style: 'rectangular' | 'arched' | 'gothic' | 'circular';
  material?: string;
  /** 仅供组合编译器和 renderer 使用，不属于可手写的 WILD opening 字段。 */
  _interaction?: InteractiveElementBehavior;
}

// 楼梯参数
export interface StairParams {
  type: 'stair';
  id: string;
  from: Vec3;
  to: Vec3;
  stepCount?: number;
  stepDepth?: number;
  stepHeight?: number;
  width: number;
  material?: string;
}

// 家具参数
export interface FurnitureParams {
  type: 'furniture';
  id: string;
  subtype: 'table' | 'chair' | 'bookshelf' | 'bed' | 'lamp' | 'tile';
  position: Vec3;
  style?: string;
  dimensions: { width: number; depth: number; height: number };
  material?: string;
}

// 致密砖的参数
export interface DenseBrickParams {
  type: 'dense_brick';
  id: string;
  /** [x体素数, y体素数, z体素数]，各维 ≥ 8，必须为整数 */
  resolution: [number, number, number];
  origin: Vec3;
  data: string;
  material?: string;
  method?: 'marching_cubes' | 'dual_contouring';
  attachment?: { parent: string; mapping: 'planar' | 'cylindrical' | 'spherical' };
}

// 肢体参数
export interface BodyParams {
  type: 'body';
  id: string;
  height: number;
  build: 'lean' | 'athletic' | 'stout';
  headShape: 'round' | 'oval' | 'angular';
  armLength: number;
  legLength: number;
  cloakLength: number;
  hoodUp: boolean;
  position?: Vec3;
  material?: string;
}

/**
 * 通用参数化形体（WILD v1.1）。
 *
 * 用少量可组合的数学形体表达篮球、檐口线脚等对象，避免为每个现实
 * 名词增加一个专用 element type。
 */
export interface PrimitiveParams {
  type: 'primitive';
  id: string;
  shape: 'box' | 'sphere' | 'cylinder' | 'profile_sweep';
  position?: Vec3;
  rotation?: Vec3;
  scale?: Vec3;
  material?: string;

  /** box: [宽, 高, 深] */
  dimensions?: Vec3;

  /** sphere / cylinder / profile_sweep 默认截面半径 */
  radius?: number;
  radiusTop?: number;
  radiusBottom?: number;
  height?: number;
  segments?: number;
  heightSegments?: number;

  /** profile_sweep: 二维截面点 [u, v] 与三维路径点 */
  profile?: Array<[number, number]>;
  path?: Vec3[];
  closedProfile?: boolean;
  /** 仅供组合编译器和 renderer 使用。 */
  _interaction?: InteractiveElementBehavior;
}

// ========== 材质系统 ==========
export interface WeatheringEffect {
  type: 'weathering';
  dustColor: Color;
  dustOpacity: number;
  crackIntensity: number;
  colorFade: number;
}

export interface MossEffect {
  type: 'moss';
  mossColor: Color;
  coverage: number;
  pattern: 'base_up' | 'patchy' | 'edge';
}

export interface EdgeWearEffect {
  type: 'edgeWear';
  wearColor: Color;
  intensity: number;
}

export interface GrainEffect {
  type: 'grain';
  intensity: number;
  scale: number;
}

export type EffectLayer = WeatheringEffect | MossEffect | EdgeWearEffect | GrainEffect;

export interface EmbeddedImageData {
  encoding: 'base64';
  mimeType: string;
  data: string;
}

export interface MaterialDef {
  baseColor: Color;
  roughness: number;
  metallic: number;
  albedo: number;
  emissive?: Color;
  opacity?: number;
  lightingCondition: 'D65_noon';
  effects?: EffectLayer[];
  embeddedImage?: EmbeddedImageData;
  /** WILD v1.1：可选的内嵌 PBR 纹理通道 */
  textures?: {
    baseColor?: EmbeddedImageData;
    normal?: EmbeddedImageData;
    roughness?: EmbeddedImageData;
    metalness?: EmbeddedImageData;
    ambientOcclusion?: EmbeddedImageData;
  };
  normalScale?: number;
  uvScale?: [number, number];
}

// ========== 动态系统 ==========
export interface PhysicsData {
  mass: number;
  collisionShape: 'box' | 'sphere' | 'capsule' | 'mesh';
  constraints?: ConstraintData[];
}

export type ConstraintData = HingeConstraint | SliderConstraint;

export interface HingeConstraint {
  type: 'hinge';
  target: string;
  axis: 'x' | 'y' | 'z';
  limit?: [number, number];
}

export interface SliderConstraint {
  type: 'slider';
  target: string;
  axis: 'x' | 'y' | 'z';
  limit?: [number, number];
}

export interface AnimationParams {
  walkStyle?: number;
  posture?: number;
  clothStiffness?: number;
  clothDamping?: number;
  windResponse?: number;
}

export interface ScriptData {
  on_click?: ScriptCondition;
  on_enter?: ScriptCondition;
  on_leave?: ScriptCondition;
}

export interface ScriptCondition {
  condition?: string;
  actions: ActionData[];
}

export interface ActionData {
  type: 'toggle_hinge' | 'play_sound' | 'set_material' | 'show_text' | 'teleport';
  target?: string;
  sound?: string;
  material?: string;
  text?: string;
  destination?: Vec3;
}

// ========== 元数据 ==========
export interface Meta {
  version: string;           // "1.0"
  // 场景类型："building"（建筑）或 "avatar"（虚拟角色）
  type: 'building' | 'avatar' | 'asset' | 'scene';
  // 	场景名称，如 "中式凉亭"
  name: string;
  // 作者名（可选）
  author?: string;
  // 创建时间戳（可选）
  createdAt?: number;
  // 	风格标签，如 "chinese_classical"（可选）
  style?: string;
  // 随机种子，用于程序化生成的可复现性
  seed?: number;
}

// ========== 蓝图顶层结构 ==========
export interface Blueprint {
  // 元数据
  meta: Meta;
  // 几何定义
  geometry: {
    // 直接构件数组。存放场景中每个独立物体（墙、柱、地板、房顶、家具等），每个元素是一个 GeometryElement 联合类型，必须带唯一的 id。这是一般场景最主要的填充内容
    elements?: GeometryElement[];
    // 高级组合构件。渲染前由 wild-compiler 展开为现有 GeometryElement。
    components?: ComponentSpec[];
    // 构件模板字典。key → GeometryElement 的映射。模板本身不直接渲染，它定义了一个"原型构件"。与 instances 组合使用：同一模板可被多个实例引用，类似于"定义了一个柱子原型，然后在地图上放置 20 个"。避免重复定义相同的构件参数
    templates?: Record<string, GeometryElement>;
    // 模板实例数组。每个 InstanceRef 通过 ref 指向 templates 中的某个模板，并指定自己的 position/rotation/scale 和可选的 materialOverride（对模板中的某些材质做替换）。由 expander 展开为实际构件后交给几何构建器
    instances?: InstanceRef[];
    // 批量放置规则。定义如何在某个父构件的表面上按网格（grid）自动排布模板实例。例如："在这面墙（parent）的正面（face）上用 3 列 × 4 行的网格放置窗户模板"。比手动写 instances 更高效，也是由 expander 展开
    placements?: Placement[];
  };
  // 材质定义
  materials?: Record<string, MaterialDef>;
  // 动态行为，定义场景的物理、脚本和动画行为，不属于几何本身，但附加在场景上：
  behaviors?: {
    // 物理属性
    physics?: PhysicsData;
    // 交互脚本数组
    scripts?: ScriptData[];
    // 动画参数
    animation?: AnimationParams;
  };
}

export interface InstanceRef {
  id?: string;
  ref: string;
  position: Vec3;
  rotation?: Vec3;
  scale?: Vec3;
  materialOverride?: Record<string, string>;
}

/** 布局放置 — 用数学规则在父构件表面批量生成实例 */
export interface Placement {
  id: string;
  template: string;
  onSurface: {
    parent: string;
    face: string | string[];
  };
  layout: {
    type: 'grid';
    columns: number;
    rows: number;
    rowSpacing: number;
    colSpacing: number;
    overlap?: number;
    gapWidth?: number;
    /** 按格子覆盖材质。键为 "{行}_{列}"，值为材质名 */
    cellMaterials?: Record<string, string>;
  };
}
