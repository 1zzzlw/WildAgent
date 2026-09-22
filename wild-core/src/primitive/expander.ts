/**
 * 模板展开器
 * 
 * 将蓝图中 templates + instances 展开为完整的 elements 列表。
 * 实例覆盖模板中的位置、旋转、缩放和材质。
 */

import type { Blueprint, EngineDiagnostic, GeometryElement, Placement } from './types';

export function expandTemplates(bp: Blueprint, diagnostics: EngineDiagnostic[] = []): GeometryElement[] {
  // resolver 会在元素上附加 _cutouts / _worldPos 等仅供本轮重建使用的字段。
  // 必须克隆源元素，避免内部状态泄漏到 Store、自动保存和最终 WILD 文件。
  const elements = (bp.geometry.elements || []).map(
    element => JSON.parse(JSON.stringify(element)) as GeometryElement,
  );
  const templates = bp.geometry.templates || {};
  const instances = bp.geometry.instances || [];

  for (const [instanceIndex, inst] of instances.entries()) {
    const template = templates[inst.ref];
    if (!template) {
      diagnostics.push({
        level: 'error',
        code: 'TEMPLATE_NOT_FOUND',
        message: `实例引用的模板 "${inst.ref}" 不存在`,
        elementId: (inst as any).id,
      });
      continue;
    }

    // 深拷贝模板
    const elem = JSON.parse(JSON.stringify(template)) as GeometryElement;
    elem.id = (inst as any).id || `${inst.ref}_${instanceIndex}`;
    (elem as any)._instanceTransform = {
      position: inst.position,
      rotation: inst.rotation || [0, 0, 0],
      scale: inst.scale || [1, 1, 1],
    };

    // 处理材质覆盖
    if (inst.materialOverride && (elem as any).material) {
      const overrideKey = (elem as any).material;
      if (inst.materialOverride[overrideKey]) {
        (elem as any).material = inst.materialOverride[overrideKey];
      }
    }

    elements.push(elem);
  }

  return elements;
}

/**
 * 在空间关系解析后展开 placements。
 * 此时父构件已获得正确 position，瓦片位置基于父构件世界坐标计算。
 */
export function expandPlacements(
  bp: Blueprint,
  elements: GeometryElement[],
  diagnostics: EngineDiagnostic[] = [],
): void {
  const templates = bp.geometry.templates || {};
  const placements = bp.geometry.placements || [];
  for (const pl of placements) {
    const template = templates[pl.template];
    if (!template) {
      diagnostics.push({
        level: 'error',
        code: 'PLACEMENT_TEMPLATE_NOT_FOUND',
        message: `排布 "${pl.id}" 引用的模板 "${pl.template}" 不存在`,
        elementId: pl.id,
      });
      continue;
    }
    const parent = elements.find(e => e.id === pl.onSurface.parent);
    if (!parent) {
      diagnostics.push({
        level: 'error',
        code: 'PLACEMENT_PARENT_NOT_FOUND',
        message: `排布 "${pl.id}" 的父构件 "${pl.onSurface.parent}" 不存在`,
        elementId: pl.id,
      });
      continue;
    }
    _expandPlacement(pl, template, parent, elements, bp.materials || {}, diagnostics);
  }
}

/** 展开一条 placement 为瓦片网格（单个元素，批处理生成所有瓦片）*/
function _expandPlacement(
  pl: Placement,
  template: GeometryElement,
  parent: GeometryElement,
  elements: GeometryElement[],
  bpMaterials: Record<string, any>,
  diagnostics: EngineDiagnostic[],
): void {
  const faces = typeof pl.onSurface.face === 'string' ? [pl.onSurface.face] : pl.onSurface.face;
  const l = pl.layout;
  let faceIndex = 0;
  const parentPos = (parent as any).position ?? [0, 0, 0];
  const gapW = l.gapWidth ?? 0.008;
  const overlap = l.overlap ?? 0;
  const tileThickness = (template as any).dimensions?.height ?? 0.05;
  const mat = (template as any).material ?? 'roof_tile';

  for (const face of faces) {
    const surface = getSurfaceCorners(parent, face);
    if (!surface) {
      diagnostics.push({
        level: 'warning',
        code: 'PLACEMENT_SURFACE_UNSUPPORTED',
        message: `排布 "${pl.id}" 无法解析 "${pl.onSurface.parent}" 的 "${face}" 表面`,
        elementId: pl.id,
        elementType: parent.type,
      });
      continue;
    }
    const { corners, normal } = surface;
    const [bl, br, tr, tl] = corners;
    const uVec = [br[0]-bl[0], br[1]-bl[1], br[2]-bl[2]];
    const vVec = [tl[0]-bl[0], tl[1]-bl[1], tl[2]-bl[2]];
    const quadW = Math.sqrt(uVec[0]**2+uVec[1]**2+uVec[2]**2);
    const quadH = Math.sqrt(vVec[0]**2+vVec[1]**2+vVec[2]**2);
    const uAxis = [uVec[0]/quadW, uVec[1]/quadW, uVec[2]/quadW];
    const vAxis = [vVec[0]/quadH, vVec[1]/quadH, vVec[2]/quadH];

    const cols = Math.min(l.columns, Math.max(1, Math.floor((quadW + gapW) / (l.colSpacing))));
    const rows = Math.min(l.rows, Math.max(1, Math.floor((quadH + overlap) / (l.rowSpacing + overlap))));
    const aTileH = (quadH + (rows - 1) * overlap) / rows;
    const aTileW = (quadW - (cols - 1) * gapW) / cols;

    // 创建单个元素携带完整瓦片网格数据，由 buildTile 批处理生成合并几何
    const elem = JSON.parse(JSON.stringify(template)) as any;
    elem.id = `${pl.id}_${faceIndex}`;
    elem.position = [0, 0, 0];
    elem.rotation = [0, 0, 0];
    elem._tileGrid = { bl, uAxis, vAxis, normal, cols, rows, aTileW, aTileH, gapW, overlap, tileThickness, parentPos, cellMaterials: (l as any).cellMaterials, bpMaterials };
    elem.material = mat;
    elements.push(elem);
    faceIndex++;
  }
}

/** 获取父构件指定面的四角和法线（当前支持 roof gable 的 left/right） */
function getSurfaceCorners(parent: GeometryElement, face: string): { corners: number[][]; normal: number[] } | null {
  if (parent.type === 'roof' && (parent as any).roofType === 'gable') {
    const p = parent as any;
    const hw = p.span / 2, hd = p.depth / 2, h = p.height;
    if (face === 'left') return getGableLeftSurface(hw, hd, h);
    if (face === 'right') return getGableRightSurface(hw, hd, h);
  }
  // TODO: 支持 floor/wall/beam 等构件的 face 查询
  return null;
}

function getGableLeftSurface(hw: number, hd: number, h: number) {
  const ridge = h, eaves = 0;
  const corners = [[-hw, eaves, hd], [-hw, eaves, -hd], [0, ridge, -hd], [0, ridge, hd]];
  const u = [corners[1][0]-corners[0][0], corners[1][1]-corners[0][1], corners[1][2]-corners[0][2]];
  const v = [corners[3][0]-corners[0][0], corners[3][1]-corners[0][1], corners[3][2]-corners[0][2]];
  const n = [v[1]*u[2]-v[2]*u[1], v[2]*u[0]-v[0]*u[2], v[0]*u[1]-v[1]*u[0]];
  const nl = Math.sqrt(n[0]**2+n[1]**2+n[2]**2);
  return { corners, normal: [n[0]/nl, n[1]/nl, n[2]/nl] };
}

function getGableRightSurface(hw: number, hd: number, h: number) {
  const ridge = h, eaves = 0;
  const corners = [[hw, eaves, -hd], [hw, eaves, hd], [0, ridge, hd], [0, ridge, -hd]];
  const u = [corners[1][0]-corners[0][0], corners[1][1]-corners[0][1], corners[1][2]-corners[0][2]];
  const v = [corners[3][0]-corners[0][0], corners[3][1]-corners[0][1], corners[3][2]-corners[0][2]];
  const n = [v[1]*u[2]-v[2]*u[1], v[2]*u[0]-v[0]*u[2], v[0]*u[1]-v[1]*u[0]];
  const nl = Math.sqrt(n[0]**2+n[1]**2+n[2]**2);
  return { corners, normal: [n[0]/nl, n[1]/nl, n[2]/nl] };
}
