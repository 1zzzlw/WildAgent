import type { OpeningParams, MeshData } from '../types';

export function buildOpening(params: OpeningParams): MeshData[] {
  const { width, height, material, style } = params;
  const hw = width / 2;
  const hh = height / 2;

  const vertices: number[] = [];
  const uvs: number[] = [];
  const pushTriangle = (a: [number, number], b: [number, number], c: [number, number]) => {
    for (const point of [a, b, c]) {
      vertices.push(point[0], point[1], 0);
      uvs.push(point[0] / width + 0.5, point[1] / height + 0.5);
    }
  };

  if (style === 'circular') {
    const radius = Math.min(width, height) / 2;
    const segments = 32;
    for (let i = 0; i < segments; i++) {
      const a0 = i / segments * Math.PI * 2;
      const a1 = (i + 1) / segments * Math.PI * 2;
      pushTriangle(
        [0, 0],
        [Math.cos(a0) * radius, Math.sin(a0) * radius],
        [Math.cos(a1) * radius, Math.sin(a1) * radius],
      );
    }
  } else if (style === 'arched') {
    const radius = Math.min(hw, height * 0.45);
    const springY = hh - radius;
    pushTriangle([-hw, -hh], [hw, -hh], [hw, springY]);
    pushTriangle([-hw, -hh], [hw, springY], [-hw, springY]);
    const segments = 18;
    for (let i = 0; i < segments; i++) {
      const a0 = Math.PI * (i / segments);
      const a1 = Math.PI * ((i + 1) / segments);
      pushTriangle(
        [0, springY],
        [Math.cos(a1) * radius, springY + Math.sin(a1) * radius],
        [Math.cos(a0) * radius, springY + Math.sin(a0) * radius],
      );
    }
  } else if (style === 'gothic') {
    const springY = hh - Math.min(height * 0.38, hw);
    pushTriangle([-hw, -hh], [hw, -hh], [hw, springY]);
    pushTriangle([-hw, -hh], [hw, springY], [-hw, springY]);
    pushTriangle([-hw, springY], [hw, springY], [0, hh]);
  } else {
    pushTriangle([-hw, -hh], [hw, -hh], [hw, hh]);
    pushTriangle([-hw, -hh], [hw, hh], [-hw, hh]);
  }
  const geometry = new Float32Array(vertices);
  const indices = Uint32Array.from({ length: geometry.length / 3 }, (_, index) => index);

  // 使用 resolver 算好的世界位置和旋转
  const worldPos = (params as any)._worldPos;
  const wallRotation = (params as any)._wallRotation ?? 0;
  
  // worldPos 已经是开口底部的世界坐标，需要加上半高度使开口中心对齐
  // 开口几何体是以中心为原点的，所以 position 应该是开口中心点
  const centerY = worldPos ? worldPos[1] + hh : params.from[1] + hh;
  const pos = worldPos || [params.from[0], params.from[1], params.from[2]];

  return [{
    geometry,
    indices,
    uvs: new Float32Array(uvs),
    transform: {
      position: [pos[0], centerY, pos[2]],
      rotation: [0, wallRotation, 0],
      scale: [1, 1, 1]
    },
    materialRef: material || 'default'
  }];
}
