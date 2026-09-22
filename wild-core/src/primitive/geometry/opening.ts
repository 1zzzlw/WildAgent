import type { OpeningParams, MeshData } from '../types';
import { generateArchitecturalSurfaceAttributes } from './mesh-helper';

export function buildOpening(params: OpeningParams): MeshData[] {
  const { width, height, material, style } = params;
  const depth = params.depth ?? 0.01;
  if (!Number.isFinite(depth) || depth <= 0) {
    throw new Error('opening.depth 必须是正有限数字');
  }
  const hw = width / 2;
  const hh = height / 2;
  const halfDepth = depth / 2;
  const contour = buildOpeningContour(style, hw, hh, width, height);
  const vertices: number[] = [];
  const pushTriangle = (
    a: [number, number, number],
    b: [number, number, number],
    c: [number, number, number],
  ) => vertices.push(...a, ...b, ...c);

  for (let index = 0; index < contour.length; index++) {
    const current = contour[index];
    const next = contour[(index + 1) % contour.length];
    pushTriangle(
      [0, 0, halfDepth],
      [current[0], current[1], halfDepth],
      [next[0], next[1], halfDepth],
    );
    pushTriangle(
      [0, 0, -halfDepth],
      [next[0], next[1], -halfDepth],
      [current[0], current[1], -halfDepth],
    );
    pushTriangle(
      [current[0], current[1], halfDepth],
      [current[0], current[1], -halfDepth],
      [next[0], next[1], -halfDepth],
    );
    pushTriangle(
      [current[0], current[1], halfDepth],
      [next[0], next[1], -halfDepth],
      [next[0], next[1], halfDepth],
    );
  }

  if (params._doorLeafDetail) {
    appendDoorLeafDetails(
      pushTriangle,
      width,
      height,
      halfDepth,
      params._doorLeafDetail,
    );
  }

  const geometry = new Float32Array(vertices);
  const indices = Uint32Array.from({ length: geometry.length / 3 }, (_, index) => index);
  const attributes = generateArchitecturalSurfaceAttributes(geometry);

  // 使用 resolver 算好的世界位置和旋转
  const worldPos = (params as any)._worldPos;
  const wallRotation = (params as any)._wallRotation ?? 0;

  // worldPos 已经是开口底部的世界坐标，需要加上半高度使开口中心对齐
  const centerY = worldPos ? worldPos[1] + hh : params.from[1] + hh;
  const pos = worldPos || [params.from[0], params.from[1], params.from[2]];

  return [{
    geometry,
    indices,
    normals: attributes.normals,
    uvs: attributes.uvs,
    transform: {
      position: [pos[0], centerY, pos[2]],
      rotation: [0, wallRotation, 0],
      scale: [1, 1, 1],
    },
    materialRef: material || 'default',
  }];
}

type TriangleWriter = (
  a: [number, number, number],
  b: [number, number, number],
  c: [number, number, number],
) => number;

function appendDoorLeafDetails(
  pushTriangle: TriangleWriter,
  width: number,
  height: number,
  halfDepth: number,
  detail: NonNullable<OpeningParams['_doorLeafDetail']>,
): void {
  const panelRelief = 0.008;
  const handleRelief = 0.018;
  const horizontalMargin = Math.max(0.06, Math.min(0.14, width * 0.14));
  const verticalMargin = Math.max(0.16, Math.min(0.24, height * 0.1));
  const gap = Math.max(0.04, Math.min(0.07, width * 0.06));
  const usableWidth = width - horizontalMargin * 2 - gap * (detail.columns - 1);
  const usableHeight = height - verticalMargin * 2 - gap * (detail.rows - 1);
  const panelWidth = usableWidth / detail.columns;
  const panelHeight = usableHeight / detail.rows;
  if (panelWidth <= 0.04 || panelHeight <= 0.04) return;

  for (const side of [-1, 1] as const) {
    const panelMinZ = side > 0 ? halfDepth : -halfDepth - panelRelief;
    const panelMaxZ = side > 0 ? halfDepth + panelRelief : -halfDepth;
    for (let column = 0; column < detail.columns; column++) {
      for (let row = 0; row < detail.rows; row++) {
        const minX = -width / 2 + horizontalMargin + column * (panelWidth + gap);
        const minY = -height / 2 + verticalMargin + row * (panelHeight + gap);
        appendBox(
          pushTriangle,
          minX,
          minX + panelWidth,
          minY,
          minY + panelHeight,
          panelMinZ,
          panelMaxZ,
        );
      }
    }

    const handleXs = detail.doubleDoor
      ? [-gap * 0.65, gap * 0.65]
      : [
          detail.hingeSide === 'left'
            ? width / 2 - horizontalMargin * 0.65
            : -width / 2 + horizontalMargin * 0.65,
        ];
    const handleMinZ = side > 0 ? halfDepth : -halfDepth - handleRelief;
    const handleMaxZ = side > 0 ? halfDepth + handleRelief : -halfDepth;
    for (const handleX of handleXs) {
      appendBox(
        pushTriangle,
        handleX - 0.018,
        handleX + 0.018,
        -0.12,
        0.12,
        handleMinZ,
        handleMaxZ,
      );
    }
  }
}

function appendBox(
  pushTriangle: TriangleWriter,
  minX: number,
  maxX: number,
  minY: number,
  maxY: number,
  minZ: number,
  maxZ: number,
): void {
  const corners: Array<[number, number, number]> = [
    [minX, minY, minZ], [maxX, minY, minZ],
    [maxX, maxY, minZ], [minX, maxY, minZ],
    [minX, minY, maxZ], [maxX, minY, maxZ],
    [maxX, maxY, maxZ], [minX, maxY, maxZ],
  ];
  for (const [a, b, c, d] of [
    [0, 3, 2, 1], [4, 5, 6, 7],
    [0, 1, 5, 4], [3, 7, 6, 2],
    [0, 4, 7, 3], [1, 2, 6, 5],
  ]) {
    pushTriangle(corners[a], corners[b], corners[c]);
    pushTriangle(corners[a], corners[c], corners[d]);
  }
}

function buildOpeningContour(
  style: OpeningParams['style'],
  hw: number,
  hh: number,
  width: number,
  height: number,
): Array<[number, number]> {
  if (style === 'circular') {
    const radius = Math.min(width, height) / 2;
    return Array.from({ length: 32 }, (_, index) => {
      const angle = index / 32 * Math.PI * 2;
      return [Math.cos(angle) * radius, Math.sin(angle) * radius] as [number, number];
    });
  }
  if (style === 'arched') {
    const radius = Math.min(hw, height * 0.45);
    const springY = hh - radius;
    const contour: Array<[number, number]> = [[-hw, -hh], [hw, -hh], [hw, springY]];
    if (radius < hw - 1e-9) contour.push([radius, springY]);
    for (let index = 0; index <= 18; index++) {
      const angle = Math.PI * index / 18;
      const point: [number, number] = [
        Math.cos(angle) * radius,
        springY + Math.sin(angle) * radius,
      ];
      const previous = contour[contour.length - 1];
      if (Math.hypot(previous[0] - point[0], previous[1] - point[1]) > 1e-9) {
        contour.push(point);
      }
    }
    if (radius < hw - 1e-9) contour.push([-hw, springY]);
    return contour;
  }
  if (style === 'gothic') {
    const springY = hh - Math.min(height * 0.38, hw);
    return [[-hw, -hh], [hw, -hh], [hw, springY], [0, hh], [-hw, springY]];
  }
  return [[-hw, -hh], [hw, -hh], [hw, hh], [-hw, hh]];
}
