import type { RoofParams, MeshData } from '../types';
import { generateArchitecturalSurfaceAttributes, indexTriList } from './mesh-helper';

export function buildRoof(params: RoofParams): MeshData[] {
  const { roofType, span, depth, height, thickness, material } = params;
  const hw = span / 2, hd = depth / 2;
  const pos = (params as any).position ?? [0, 0, 0];

  if (roofType === 'chinese_pagoda') return buildPagoda(params, pos);
  if (roofType === 'chinese_curved') return buildChineseCurved(params, pos);

  let geometry: Float32Array;
  switch (roofType) {
    case 'gable':   geometry = buildGable(hw, hd, height, thickness); break;
    case 'hip':     geometry = buildHip(hw, hd, height, thickness); break;
    case 'dome':    geometry = buildDome(hw, hd, height, thickness); break;
    case 'flat':    geometry = buildFlat(hw, hd, thickness); break;
    default:        throw new Error(`Unsupported roofType: ${roofType}`);
  }

  const { geometry: geo, indices } = indexTriList(geometry);
  return [{
    geometry: geo, indices: new Uint32Array(indices),
    transform: { position: [pos[0], pos[1], pos[2]], rotation: [0, 0, 0], scale: [1, 1, 1] },
    materialRef: material || 'default',
  }];
}

/** 中式曲面屋顶：举折曲线 + 四角飞檐 + 有厚度内表面 */
function buildChineseCurved(params: RoofParams, pos: number[]): MeshData[] {
  const { span, depth, height, thickness, material } = params;
  const hw = span / 2, hd = depth / 2;
  const crossSegments = 18;
  const depthSegments = 12;
  const eaveLift = params.eaveCurveHeight ?? Math.min(height * 0.18, 0.8);
  const profilePower = params.curveProfile === 'steep'
    ? 1.55
    : params.curveProfile === 'gentle' ? 1.15 : 1.32;
  const roofThickness = Math.max(thickness, 0.02);
  const vertices: number[] = [];
  const uvs: number[] = [];

  const profilePoint = (x: number, zRatio: number, inner: boolean): [number, number, number] => {
    const t = Math.min(1, Math.abs(x) / Math.max(hw, 1e-9));
    const cornerLift = eaveLift * Math.pow(Math.abs(zRatio), 4) * Math.pow(t, 4);
    const y = height * Math.pow(1 - t, profilePower) + cornerLift - (inner ? roofThickness : 0);
    return [x, y, zRatio * hd];
  };
  const point = (side: -1 | 1, crossIndex: number, depthIndex: number, inner: boolean): [number, number, number] => {
    const x = side * hw * (crossIndex / crossSegments);
    const zRatio = depthIndex / depthSegments * 2 - 1;
    return profilePoint(x, zRatio, inner);
  };

  const push = (p: number[], uv: [number, number]) => {
    vertices.push(p[0], p[1], p[2]);
    uvs.push(uv[0], uv[1]);
  };
  const quad = (
    a: number[], b: number[], c: number[], d: number[],
    uvA: [number, number], uvB: [number, number], uvC: [number, number], uvD: [number, number],
    reverse = false,
  ) => {
    if (reverse) {
      push(a, uvA); push(c, uvC); push(b, uvB);
      push(a, uvA); push(d, uvD); push(c, uvC);
    } else {
      push(a, uvA); push(b, uvB); push(c, uvC);
      push(a, uvA); push(c, uvC); push(d, uvD);
    }
  };

  for (const side of [-1, 1] as const) {
    for (let ci = 0; ci < crossSegments; ci++) {
      const u0 = ci / crossSegments, u1 = (ci + 1) / crossSegments;
      for (let di = 0; di < depthSegments; di++) {
        const v0 = di / depthSegments, v1 = (di + 1) / depthSegments;
        const a = point(side, ci, di, false);
        const b = point(side, ci + 1, di, false);
        const c = point(side, ci + 1, di + 1, false);
        const d = point(side, ci, di + 1, false);
        quad(a, b, c, d, [u0, v0], [u1, v0], [u1, v1], [u0, v1], side === -1);

        const ai = point(side, ci, di, true);
        const bi = point(side, ci + 1, di, true);
        const ci2 = point(side, ci + 1, di + 1, true);
        const di2 = point(side, ci, di + 1, true);
        quad(ai, bi, ci2, di2, [u0, v0], [u1, v0], [u1, v1], [u0, v1], side === 1);
      }
    }

    // 檐口封边
    for (let di = 0; di < depthSegments; di++) {
      const v0 = di / depthSegments, v1 = (di + 1) / depthSegments;
      quad(
        point(side, crossSegments, di, false),
        point(side, crossSegments, di + 1, false),
        point(side, crossSegments, di + 1, true),
        point(side, crossSegments, di, true),
        [0, v0], [0, v1], [1, v1], [1, v0],
        side === -1,
      );
    }

    // 前后山面封边
    for (const depthIndex of [0, depthSegments]) {
      for (let ci = 0; ci < crossSegments; ci++) {
        quad(
          point(side, ci, depthIndex, false),
          point(side, ci + 1, depthIndex, false),
          point(side, ci + 1, depthIndex, true),
          point(side, ci, depthIndex, true),
          [ci / crossSegments, 0], [(ci + 1) / crossSegments, 0],
          [(ci + 1) / crossSegments, 1], [ci / crossSegments, 1],
          (depthIndex === 0) !== (side === -1),
        );
      }
    }
  }

  const geometry = new Float32Array(vertices);
  const meshes: MeshData[] = [{
    geometry,
    indices: Uint32Array.from({ length: geometry.length / 3 }, (_, index) => index),
    uvs: new Float32Array(uvs),
    transform: { position: [pos[0], pos[1], pos[2]], rotation: [0, 0, 0], scale: [1, 1, 1] },
    materialRef: material || 'default',
  }];

  // 墙体是矩形，而曲面屋顶的内轮廓在屋脊处升高；没有端部填充时，
  // 墙顶与屋面之间会出现可见三角空洞。resolver 只为最高承托墙提供
  // 运行时数据，这里按同一曲线生成两端的实体山墙，并沿墙厚封闭。
  const gableEnds = (params as any)._gableEnds as Array<{
    z: number; xMin: number; xMax: number; thickness: number; material: string;
  }> | undefined;
  for (const end of gableEnds ?? []) {
    const zRatio = Math.max(-1, Math.min(1, (end.z - pos[2]) / Math.max(hd, 1e-9)));
    const xMin = Math.max(-hw, end.xMin - pos[0]);
    const xMax = Math.min(hw, end.xMax - pos[0]);
    if (xMax - xMin <= 0.01) continue;
    const samples = Math.max(2, Math.ceil((xMax - xMin) / (span / crossSegments)));
    const xs = Array.from({ length: samples + 1 }, (_, index) => (
      xMin + (xMax - xMin) * index / samples
    ));
    const halfThickness = Math.max(0.01, end.thickness / 2);
    const zFront = zRatio * hd - halfThickness;
    const zBack = zRatio * hd + halfThickness;
    const gableVertices: number[] = [];
    const pushGableQuad = (a: number[], b: number[], c: number[], d: number[]) => {
      gableVertices.push(...a, ...b, ...c, ...a, ...c, ...d);
    };
    for (let index = 0; index < xs.length - 1; index++) {
      const x0 = xs[index], x1 = xs[index + 1];
      const y0 = Math.max(0, profilePoint(x0, zRatio, true)[1]);
      const y1 = Math.max(0, profilePoint(x1, zRatio, true)[1]);
      // 前后立面和底面形成实体山墙。顶部与屋面内壳贴合，不能再生成
      // 一层共面接触面，否则深度缓冲会在斜边附近产生条纹闪烁。
      pushGableQuad([x0, 0, zFront], [x1, 0, zFront], [x1, y1, zFront], [x0, y0, zFront]);
      pushGableQuad([x1, 0, zBack], [x0, 0, zBack], [x0, y0, zBack], [x1, y1, zBack]);
      pushGableQuad([x0, 0, zBack], [x1, 0, zBack], [x1, 0, zFront], [x0, 0, zFront]);
    }
    if (gableVertices.length === 0) continue;
    const indexed = indexTriList(new Float32Array(gableVertices));
    const attributes = generateArchitecturalSurfaceAttributes(indexed.geometry);
    meshes.push({
      geometry: indexed.geometry,
      indices: new Uint32Array(indexed.indices),
      normals: attributes.normals,
      uvs: attributes.uvs,
      transform: { position: [pos[0], pos[1], pos[2]], rotation: [0, 0, 0], scale: [1, 1, 1] },
      materialRef: end.material || 'default',
    });
  }

  return meshes;
}

/** 中式重檐屋顶 */
function buildPagoda(params: RoofParams, pos: number[]): MeshData[] {
  const p = params as any;
  const tiers = p.tiers || 3;
  const tierH = p.tierHeight || (p.height / tiers);
  const eave = p.eaveOutset ?? 0.5;
  const shrink = p.shrinkFactor ?? 0.7;
  const thick = p.thickness || 0.2;
  const hw = p.span / 2, hd = p.depth / 2;
  const mat = p.material || 'default';
  const meshes: MeshData[] = [];

  // 每层生成 4 个坡面 + 檐口底面
  for (let t = 0; t < tiers; t++) {
    const scale = Math.pow(shrink, t); // 当前层缩放比
    const nextScale = Math.pow(shrink, t + 1);
    const yBase = pos[1] + t * tierH;
    const yTop = pos[1] + (t + 1) * tierH;
    const cw = hw * scale, cd = hd * scale;
    const nw = hw * nextScale, nd = hd * nextScale;
    const ew = cw + eave, ed = cd + eave; // 檐口外扩

    // 4 个坡面（檐口四角 → 上层四角）
    const corners: [number,number,number][] = [
      [-ew, yBase, -ed], [ ew, yBase, -ed], [ ew, yBase,  ed], [-ew, yBase,  ed]
    ];
    const topCorners: [number,number,number][] = [
      [-nw, yTop, -nd], [ nw, yTop, -nd], [ nw, yTop,  nd], [-nw, yTop,  nd]
    ];
    for (let i = 0; i < 4; i++) {
      const j = (i + 1) % 4;
      const a = corners[i], b = corners[j], c = topCorners[j], d = topCorners[i];
      const verts = indexTriList(new Float32Array([
        a[0],a[1],a[2], b[0],b[1],b[2], c[0],c[1],c[2],
        a[0],a[1],a[2], c[0],c[1],c[2], d[0],d[1],d[2],
      ]));
      meshes.push({
        geometry: verts.geometry, indices: new Uint32Array(verts.indices),
        transform: { position: [0,0,0], rotation: [0,0,0], scale: [1,1,1] },
        materialRef: mat,
      });
    }

    // 檐口底面（檐口四角围成的矩形）
    const btmVerts = indexTriList(new Float32Array([
      corners[0][0],corners[0][1],corners[0][2],
      corners[1][0],corners[1][1],corners[1][2],
      corners[2][0],corners[2][1],corners[2][2],
      corners[0][0],corners[0][1],corners[0][2],
      corners[2][0],corners[2][1],corners[2][2],
      corners[3][0],corners[3][1],corners[3][2],
    ]));
    meshes.push({
      geometry: btmVerts.geometry, indices: new Uint32Array(btmVerts.indices),
      transform: { position: [0,0,0], rotation: [0,0,0], scale: [1,1,1] },
      materialRef: mat,
    });
  }

  return meshes;
}

function buildGable(hw: number, hd: number, h: number, t: number): Float32Array {
  const ridge = h, eaves = 0;
  return new Float32Array([
    // 前坡
    -hw,eaves,hd, hw,eaves,hd, 0,ridge,hd,
    // 后坡
    -hw,eaves,-hd, 0,ridge,-hd, hw,eaves,-hd,
    // 左坡
    0,ridge,hd, 0,ridge,-hd, -hw,eaves,-hd,
    -hw,eaves,hd, 0,ridge,hd, -hw,eaves,-hd,
    // 右坡
    hw,eaves,-hd, 0,ridge,-hd, 0,ridge,hd,
    hw,eaves,-hd, 0,ridge,hd, hw,eaves,hd,
    // 底面（封口，朝下）
    -hw,eaves,-hd, hw,eaves,hd, hw,eaves,-hd,
    -hw,eaves,-hd, -hw,eaves,hd, hw,eaves,hd,
  ]);
}

function buildHip(hw: number, hd: number, h: number, t: number): Float32Array {
  const v: number[] = [];
  const corners: [number,number,number][] = [[-hw,0,-hd],[hw,0,-hd],[hw,0,hd],[-hw,0,hd]];
  const pushTri = (a:number[],b:number[],c:number[]) => v.push(...a,...b,...c);
  const pushQuad = (a:number[],b:number[],c:number[],d:number[]) => {
    pushTri(a,b,c); pushTri(a,c,d);
  };

  if (hd >= hw) {
    const ridgeHalf = Math.max(0, hd - hw);
    const r0: [number,number,number] = [0,h,-ridgeHalf];
    const r1: [number,number,number] = [0,h,ridgeHalf];
    pushTri(corners[0], corners[1], r0);
    pushQuad(corners[1], corners[2], r1, r0);
    pushTri(corners[2], corners[3], r1);
    pushQuad(corners[3], corners[0], r0, r1);
  } else {
    const ridgeHalf = Math.max(0, hw - hd);
    const r0: [number,number,number] = [-ridgeHalf,h,0];
    const r1: [number,number,number] = [ridgeHalf,h,0];
    pushQuad(corners[0], corners[1], r1, r0);
    pushTri(corners[1], corners[2], r1);
    pushQuad(corners[2], corners[3], r0, r1);
    pushTri(corners[3], corners[0], r0);
  }
  // 底面封口（朝下，顶点顺序翻转）
  const [c0, c1, c2, c3] = corners;
  v.push(c0[0],c0[1],c0[2], c2[0],c2[1],c2[2], c1[0],c1[1],c1[2]);
  v.push(c0[0],c0[1],c0[2], c3[0],c3[1],c3[2], c2[0],c2[1],c2[2]);
  return new Float32Array(v);
}

function buildDome(hw: number, hd: number, h: number, t: number): Float32Array {
  const seg=16,v:number[]=[],r=Math.min(hw,hd);
  for(let i=0;i<seg;i++){
    const a1=i/seg*Math.PI*2,a2=(i+1)/seg*Math.PI*2;
    for(let j=0;j<seg/2;j++){
      const p1=j/(seg/2)*Math.PI/2,p2=(j+1)/(seg/2)*Math.PI/2;
      const r1=r*Math.cos(p1),r2=r*Math.cos(p2),y1=h*Math.sin(p1),y2=h*Math.sin(p2);
      const p00=[Math.cos(a1)*r1,y1,Math.sin(a1)*r1],p10=[Math.cos(a2)*r1,y1,Math.sin(a2)*r1];
      const p11=[Math.cos(a2)*r2,y2,Math.sin(a2)*r2],p01=[Math.cos(a1)*r2,y2,Math.sin(a1)*r2];
      v.push(...p00,...p11,...p10,...p00,...p01,...p11);
    }
  }
  return new Float32Array(v);
}

function buildFlat(hw: number, hd: number, t: number): Float32Array {
  // position.y 表示屋顶支承标高。实体必须从墙顶向上增厚；旧实现向下增厚并
  // 把可见顶面留在墙顶标高，会与实体墙的顶面共面产生 Z-fighting。
  const thick = t > 0.01 ? t : 0;
  const yBot = 0;
  const yTop = thick;

  if (thick <= 0) {
    // 无厚度：单面朝上（原行为）
    return new Float32Array([
      -hw, 0, -hd,  hw, 0, -hd,  hw, 0,  hd,
      -hw, 0, -hd,  hw, 0,  hd, -hw, 0,  hd,
    ]);
  }

  return new Float32Array([
    // 顶面（朝上，法线 +Y）
    -hw, yTop, -hd,   hw, yTop, -hd,   hw, yTop,  hd,
    -hw, yTop, -hd,   hw, yTop,  hd,  -hw, yTop,  hd,
    // 底面（朝下，法线 -Y，顶点顺序翻转）
    -hw, yBot,  hd,   hw, yBot,  hd,   hw, yBot, -hd,
    -hw, yBot,  hd,   hw, yBot, -hd,  -hw, yBot, -hd,
    // 前侧面（Z+）
    -hw, yBot,  hd,   hw, yBot,  hd,   hw, yTop,  hd,
    -hw, yBot,  hd,   hw, yTop,  hd,  -hw, yTop,  hd,
    // 后侧面（Z-）
     hw, yBot, -hd,  -hw, yBot, -hd,  -hw, yTop, -hd,
     hw, yBot, -hd,  -hw, yTop, -hd,   hw, yTop, -hd,
    // 左侧面（X-）
    -hw, yBot, -hd,  -hw, yBot,  hd,  -hw, yTop,  hd,
    -hw, yBot, -hd,  -hw, yTop,  hd,  -hw, yTop, -hd,
    // 右侧面（X+）
     hw, yBot,  hd,   hw, yBot, -hd,   hw, yTop, -hd,
     hw, yBot,  hd,   hw, yTop, -hd,   hw, yTop,  hd,
  ]);
}
