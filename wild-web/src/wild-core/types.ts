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
  | BodyParams;

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
  to: Vec3;
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
  material?: string;
}

// 管理门的开闭状态
export interface OpeningParams {
  type: 'opening';
  id: string;
  parentWall: string;
  from: Vec3;
  width: number;
  height: number;
  style: 'rectangular' | 'arched' | 'gothic' | 'circular';
  material?: string;
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
  material?: string;
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

export type EffectLayer = WeatheringEffect | MossEffect | EdgeWearEffect;

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
  type: 'building' | 'avatar';
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