import type { StairParams, MeshData } from '../types';
import { indexTriList } from './mesh-helper';

export function buildStair(params: StairParams): MeshData[] {
  const { from, to, stepCount, stepDepth, stepHeight, width, material } = params;
  const count = stepCount || 10;
  const sDepth = stepDepth || 0.3;
  const sHeight = stepHeight || 0.18;
  const hw = width / 2;

  const dx = (to[0] - from[0]) / count;
  const dz = (to[2] - from[2]) / count;
  const meshes: MeshData[] = [];

  // 楼梯走向方向角（XZ 平面）
  const dirX = to[0] - from[0];
  const dirZ = to[2] - from[2];
  const angle = Math.atan2(dirZ, dirX);

  for (let i = 0; i < count; i++) {
    const x = from[0] + dx * i;
    const y = from[1] + sHeight * i;
    const z = from[2] + dz * i;
    const { geometry, indices } = indexTriList(createStepGeometry(sDepth, sHeight, width));

    meshes.push({
      geometry,
      indices: new Uint32Array(indices),
      transform: {
        position: [x, y + sHeight / 2, z],
        rotation: [0, angle, 0],  // 旋转使踏步朝向楼梯走向（与墙体旋转约定一致）
        scale: [1, 1, 1]
      },
      materialRef: material || 'default'
    });
  }

  return meshes;
}

function createStepGeometry(d: number, h: number, w: number): Float32Array {
  const hd = d / 2, hh = h / 2, hw = w / 2;
  return new Float32Array([
    -hd, -hh, -hw,  hd, -hh, -hw,  hd,  hh, -hw,
    -hd, -hh, -hw,  hd,  hh, -hw, -hd,  hh, -hw,
     hd, -hh,  hw, -hd, -hh,  hw, -hd,  hh,  hw,
     hd, -hh,  hw, -hd,  hh,  hw,  hd,  hh,  hw,
    -hd,  hh, -hw, -hd,  hh,  hw,  hd,  hh,  hw,
    -hd,  hh, -hw,  hd,  hh,  hw,  hd,  hh, -hw,
    -hd, -hh, -hw, -hd, -hh,  hw,  hd, -hh,  hw,
    -hd, -hh, -hw,  hd, -hh,  hw,  hd, -hh, -hw,
     hd, -hh, -hw,  hd, -hh,  hw,  hd,  hh,  hw,
     hd, -hh, -hw,  hd,  hh,  hw,  hd,  hh, -hw,
    -hd, -hh,  hw, -hd, -hh, -hw, -hd,  hh, -hw,
    -hd, -hh,  hw, -hd,  hh, -hw, -hd,  hh,  hw
  ]);
}