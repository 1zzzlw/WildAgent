/**
 * 原语引擎参考实现 v1.0 — 内部类型定义
 * 
 * 引擎内部类型定义。
 * 语言规范类型从 ../../types 导入（纯类型，使用 import type）。
 */

import type {
  Vec3, Color, Meta, GeometryElement, MaterialDef,
  PhysicsData, ScriptData, AnimationParams, Blueprint, Placement,
  WallParams, FloorParams, ColumnParams, BeamParams, RoofParams,
  OpeningParams, StairParams, FurnitureParams, DenseBrickParams, BodyParams,
  WeatheringEffect, MossEffect, EdgeWearEffect, EffectLayer,
  ConstraintData, HingeConstraint, SliderConstraint,
  ScriptCondition, ActionData,
  InstanceRef
} from '../../types.ts';

// 重新导出语言规范类型,供引擎其他模块使用
export type {
  Vec3, Color, Meta, GeometryElement, MaterialDef, PhysicsData, ScriptData, AnimationParams, Blueprint, Placement,
  WallParams, FloorParams, ColumnParams, BeamParams, RoofParams, OpeningParams, StairParams,
  FurnitureParams, DenseBrickParams, BodyParams,
  WeatheringEffect, MossEffect, EdgeWearEffect, EffectLayer,
  ConstraintData, HingeConstraint, SliderConstraint,
  ScriptCondition, ActionData,
  InstanceRef
};

/** 引擎输出的网格数据 */
export interface MeshData {
  geometry: Float32Array;
  indices?: Uint32Array;
  /** 法线（逐顶点，同 geometry 长度） */
  normals?: Float32Array;
  /** 逐顶点颜色 [R,G,B,...]，用于程序化纹理 */
  vertexColors?: Float32Array;
  transform: {
    position: Vec3;
    rotation: Vec3;
    scale: Vec3;
  };
  /** 该网格来自哪个原始构件（如 "front_door"、"main_roof"） */
  elementId?: string;
  materialRef: string;
  /** stone_block 图案的缝隙颜色（来自蓝图 surface.mortarColor） */
  patternMortarColor?: [number, number, number];
  /**
   * 引擎标记该网格是否可交互（门、开关等可点击构件）。
   * 由引擎根据 behaviors.physics.constraints 中的 hinge/slider 自动推导，
   * viewer 无需猜测。
   */
  interactive?: boolean;
}

/** 引擎输出的材质参数 */
export interface MaterialParams {
  baseColor: Color;
  roughness: number;
  metallic: number;
  albedo: number;
  emissive: Color;
  opacity: number;
  effects: import('../../types').EffectLayer[];
  lightingCondition: string;
  embeddedImage?: import('../../types').EmbeddedImageData;
}

/** 轴对齐包围盒 */
export interface AABB {
  min: Vec3;
  max: Vec3;
}

/** 引擎重建后的完整实体 */
export interface ReconstructedEntity {
  meshes: MeshData[];
  materialParams: MaterialParams[];
  boundingBox: AABB;  // 所有网格在世界空间中的轴对齐包围盒
  physics?: PhysicsData;
  scripts?: ScriptData[];
  animation?: AnimationParams;
}

/** 空间索引：快速查找相邻构件 */
export interface SpatialIndex {
  // 按构件 ID 索引
  byId: Map<string, GeometryElement>;
  // 按三维空间网格索引（每个单元存储其内的构件 ID 集合）
  grid: Map<string, Set<string>>;
  // 网格单元大小（米）
  cellSize: number;
}