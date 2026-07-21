import type { OpeningParams, MeshData } from '../types';
import { indexTriList } from './mesh-helper';

export function buildOpening(params: OpeningParams): MeshData[] {
  const { width, height, material } = params;
  const hw = width / 2;
  const hh = height / 2;

  // 开口平面（XY 平面，法线朝 +Z）
  const { geometry, indices } = indexTriList(new Float32Array([
    -hw, -hh, 0,  hw, -hh, 0,  hw,  hh, 0,
    -hw, -hh, 0,  hw,  hh, 0, -hw,  hh, 0
  ]));

  // 使用 resolver 算好的世界位置和旋转
  const worldPos = (params as any)._worldPos;
  const wallRotation = (params as any)._wallRotation ?? 0;
  
  // worldPos 已经是开口底部的世界坐标，需要加上半高度使开口中心对齐
  // 开口几何体是以中心为原点的，所以 position 应该是开口中心点
  const centerY = worldPos ? worldPos[1] + hh : params.from[1] + hh;
  const pos = worldPos || [params.from[0], params.from[1], params.from[2]];

  return [{
    geometry,
    indices: new Uint32Array(indices),
    transform: {
      position: [pos[0], centerY, pos[2]],
      rotation: [0, wallRotation, 0],
      scale: [1, 1, 1]
    },
    materialRef: material || 'default'
  }];
}