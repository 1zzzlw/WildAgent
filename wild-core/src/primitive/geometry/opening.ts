import type { OpeningParams, MeshData } from '../types';
import { generateArchitecturalSurfaceAttributes } from './mesh-helper';
import { buildOpeningContour } from './openingContour';

export function buildOpening(params: OpeningParams): MeshData[] {
  const { width, height, material, style } = params;
  const depth = params.depth ?? 0.01;
  if (!Number.isFinite(depth) || depth <= 0) {
    throw new Error('opening.depth 必须是正有限数字');
  }
  const inset = params._leafInset ?? 0;
  const panelWidth = width - 2 * inset;
  const panelHeight = height - inset;
  const hw = panelWidth / 2;
  const hh = height / 2;
  const halfDepth = depth / 2;
  const fullContour = buildOpeningContour(style, hw, panelHeight / 2, panelWidth, panelHeight).map(([x,y]) => [x, y - inset / 2] as [number, number]);
  const double = params._doorLeafDetail?.doubleDoor;
  return (double ? [-1, 1] : [0]).map((leaf, leafIndex) => {
    const centerX = leaf * panelWidth / 4;
    const contour = (leaf ? clipHalf(fullContour, leaf) : fullContour).map(([x,y]) => [x - centerX, y] as [number, number]);
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
        double ? panelWidth / 2 : panelWidth,
        height,
        halfDepth,
        { ...params._doorLeafDetail, doubleDoor: false, columns: 1, hingeSide: leaf ? (leaf < 0 ? 'left' : 'right') : params._doorLeafDetail.hingeSide },
        contour,
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

    return {
      geometry,
      indices,
      normals: attributes.normals,
      uvs: attributes.uvs,
      transform: {
        position: [pos[0] + Math.cos(wallRotation) * centerX, centerY, pos[2] - Math.sin(wallRotation) * centerX],
        rotation: [0, wallRotation, 0],
        scale: [1, 1, 1],
      },
      materialRef: material || 'default',
      interaction: params._leafInteractions?.[leafIndex],
    };
  });
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
  contour: Array<[number, number]>,
): void {
  //  面板凸起深度受**门扇厚度**约束，不是可以随便加深的量级旋钮。
  // `wild-web/scripts/check-component-compiler.mjs` 断言门扇总厚（leafDepth + 两侧细部）
  // 落在 (0.04, 0.08]，即单侧最多 ~20mm。曾把这里改成"按门扇高度取比例"（2.5m 门 → 30mm），
  // 结果总厚算成 0.1168，被那条门禁当场判"门扇细节深度不合理"——它是对的：40mm 的门扇
  // 不可能两侧各凸 38mm。**分节的可见性天花板就是这个厚度上限**，不是这里可调的。
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
        const topAt = (x: number) => {
          const ys: number[] = [];
          for (let i = 0; i < contour.length; i++) {
            const a = contour[i], b = contour[(i + 1) % contour.length];
            if (Math.abs(b[0] - a[0]) > 1e-9 && x >= Math.min(a[0],b[0]) - 1e-9 && x <= Math.max(a[0],b[0]) + 1e-9) ys.push(a[1] + (b[1] - a[1]) * (x - a[0]) / (b[0] - a[0]));
          }
          return Math.max(...ys);
        };
        const maxY = Math.min(minY + panelHeight, topAt(minX) - 0.04, topAt(minX + panelWidth) - 0.04);
        if (maxY <= minY) continue;
        appendBox(
          pushTriangle,
          minX,
          minX + panelWidth,
          minY,
          maxY,
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


/** 将完整拱顶在中线裁为两半，避免把双开门误做成两个小拱或一块大门板。 */
function clipHalf(contour: Array<[number, number]>, sign: number): Array<[number, number]> {
  const result: Array<[number, number]> = [];
  for (let i = 0; i < contour.length; i++) {
    const a = contour[i], b = contour[(i + 1) % contour.length];
    if (a[0] * sign >= 0) result.push(a);
    if ((a[0] < 0 && b[0] > 0) || (a[0] > 0 && b[0] < 0)) result.push([0, a[1] + (b[1] - a[1]) * -a[0] / (b[0] - a[0])]);
  }
  return result;
}
