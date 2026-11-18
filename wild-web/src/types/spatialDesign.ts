/** design/1.0空间契约；字段语义以服务端spatial_contracts.py为准。 */
export type Point2 = [number, number]
export type Point3 = [number, number, number]

/** 所有长度为米、旋转为弧度，右手系Y向上，平面使用XZ。 */
export interface DesignCoordinateSystem {
  length_unit: 'm'
  angle_unit: 'rad'
  up_axis: 'y'
  plan_axes: ['x', 'z']
  handedness: 'right'
}

/** 楼面或屋面的世界标高，index只用于主要楼层。 */
export interface DesignLevel {
  id: string
  kind: 'storey' | 'roof' | 'mezzanine' | 'platform'
  index?: number | null
  elevation: number
}
export interface ElevationReference { level: string; offset?: number }

/** 有向线段；圆弧遵循绕+Y的右手旋转，Bezier有四个控制点。 */
export type DesignCurveSegment = { id: string } & (
  | { type: 'line'; from: Point2; to: Point2 }
  | { type: 'arc'; center: Point2; radius: number; start_angle: number; sweep_angle: number }
  | { type: 'cubic_bezier'; points: [Point2, Point2, Point2, Point2] }
)

/** 可复用闭合轮廓；holes引用其他轮廓ID，不包含世界坐标。 */
export type DesignProfile = { id: string; holes?: string[] } & (
  | { type: 'rectangle'; width: number; depth: number }
  | { type: 'circle'; radius: number; seam_angle?: number }
  | { type: 'ellipse'; radius_x: number; radius_z: number; seam_angle?: number }
  | { type: 'polygon'; vertices: Array<{ id: string; point: Point2 }>; edges: Array<{ id: string; from: string; to: string }> }
  | { type: 'curve_loop'; segments: DesignCurveSegment[] }
)

/** 放样在截面间线性插值；截面位移、转角和缩放表达倾斜、扭转、收分。 */
export type DesignVolumeGeometry =
  | { type: 'extrusion'; profile: string; bottom: ElevationReference; top: ElevationReference }
  | { type: 'section_loft'; interpolation?: 'linear'; sections: Array<{ at: ElevationReference; profile: string; offset_xz?: Point2; yaw?: number; scale?: Point2 }> }
  | { type: 'sweep' | 'revolve' | 'surface_patches' | 'boolean'; [key: string]: unknown }

/** 实际区域来自轮廓变换或指定标高处的体量截面并集。 */
export type DesignRegion =
  | { type: 'profile_region'; profile: string; frame?: string; origin_xz?: Point2; yaw?: number }
  | { type: 'volume_union_section'; volumes: string[]; level: string }

/** 共享构造参数；墙和板必须给厚度。 */
export interface DesignSystem {
  kind: string
  thickness?: number | null
  reference?: 'centerline'
  material_role?: string | null
  construction?: Record<string, unknown>
  [key: string]: unknown
}

/** 门窗引用此逻辑墙ID；渲染细分不会改变其身份。 */
export interface DesignWall {
  id: string
  role: 'exterior' | 'interior' | 'curtain_wall'
  system: string
  geometry: { bottom: ElevationReference; top: ElevationReference } & (
    | { type: 'volume_boundary'; volume: string; edge: string }
    | { type: 'path'; frame?: string; segments: DesignCurveSegment[] }
  )
}

export interface DesignSlab {
  id: string
  system: string
  /** 完成面标高；板底由厚度推导。 */
  top: ElevationReference
  region: DesignRegion
  /** 需要扣除的voids ID。 */
  holes?: string[]
}
export interface DesignVoid { id: string; purpose?: string; level: string; region: DesignRegion }
export interface DesignRoof { id: string; host: string; support: ElevationReference; geometry: { type: string; [key: string]: unknown }; material_role?: string | null }
export interface DesignRelation { id: string; type: 'supported_by' | 'connects_spaces' | 'aligned'; subject: string; targets?: string[]; target?: string | null; [key: string]: unknown }

/** 房间只声明功能区域，不自动生成实体墙；数字level/bounds仅兼容旧稿。 */
export interface DesignFloorLayout {
  level?: string | number | null
  floor?: number | null
  rooms: Array<{ id: string; name?: string; region?: DesignRegion | null; bounds?: Record<string, number> | null; void?: boolean }>
  walls?: Array<Record<string, unknown>>
}

/** wall模式的offset沿有向路径计量；elevation是锚点世界标高。 */
export interface DesignPlacement {
  mode?: 'world' | 'wall' | 'anchor' | 'surface' | null
  anchor?: string | null
  position?: number[]
  offset?: number
  normal_offset?: number
  elevation?: ElevationReference | null
  rotation?: Point3
  mounting?: 'conform' | 'tangent_plane'
  host_anchor?: string | null
  self_anchor?: string | null
  anchor_offset?: Point3
  chart?: string | null
  uv?: Point2 | null
  orientation?: 'surface_frame'
  /** 历史四向立面字段，新设计使用逻辑墙宿主。 */
  face?: 'front' | 'back' | 'left' | 'right' | null
  floor?: number | null
  sill_height?: number
  [key: string]: unknown
}
