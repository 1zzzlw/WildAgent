import type { RoofParams, MeshData } from '../types';
import { indexTriList } from './mesh-helper';

export function buildRoof(params: RoofParams): MeshData[] {
  const { roofType, span, depth, height, thickness, material } = params;
  const hw = span / 2, hd = depth / 2;
  const pos = (params as any).position ?? [0, 0, 0];

  if (roofType === 'chinese_pagoda') return buildPagoda(params, pos);

  let geometry: Float32Array;
  switch (roofType) {
    case 'gable':   geometry = buildGable(hw, hd, height, thickness); break;
    case 'hip':     geometry = buildHip(hw, hd, height, thickness); break;
    case 'dome':    geometry = buildDome(hw, hd, height, thickness); break;
    case 'flat':    geometry = buildFlat(hw, hd, thickness); break;
    default:        geometry = buildGable(hw, hd, height, thickness);
  }

  const { geometry: geo, indices } = indexTriList(geometry);
  return [{
    geometry: geo, indices: new Uint32Array(indices),
    transform: { position: [pos[0], pos[1], pos[2]], rotation: [0, 0, 0], scale: [1, 1, 1] },
    materialRef: material || 'default',
  }];
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
    -hw,eaves,hd, hw,eaves,hd, 0,ridge,hd,
    -hw,eaves,-hd, 0,ridge,-hd, hw,eaves,-hd,
    0,ridge,hd, 0,ridge,-hd, -hw,eaves,-hd,
    -hw,eaves,hd, 0,ridge,hd, -hw,eaves,-hd,
    hw,eaves,-hd, 0,ridge,-hd, 0,ridge,hd,
    hw,eaves,-hd, 0,ridge,hd, hw,eaves,hd,
    -hw,eaves,-hd, hw,eaves,-hd, hw,eaves,hd,
    -hw,eaves,-hd, hw,eaves,hd, -hw,eaves,hd,
  ]);
}

function buildHip(hw: number, hd: number, h: number, t: number): Float32Array {
  const v: number[] = [];
  const peak: [number,number,number] = [0,h,0];
  const corners: [number,number,number][] = [[-hw,0,-hd],[hw,0,-hd],[hw,0,hd],[-hw,0,hd]];
  for (let i=0;i<4;i++){const j=(i+1)%4;const a=corners[i],b=corners[j];v.push(a[0],a[1],a[2],b[0],b[1],b[2],peak[0],peak[1],peak[2]);}
  return new Float32Array(v);
}

function buildDome(hw: number, hd: number, h: number, t: number): Float32Array {
  const seg=16,v:number[]=[],r=Math.min(hw,hd);
  for(let i=0;i<seg;i++){const a1=i/seg*Math.PI*2,a2=(i+1)/seg*Math.PI*2;for(let j=0;j<seg/2;j++){const p1=j/(seg/2)*Math.PI/2,p2=(j+1)/(seg/2)*Math.PI/2;const r1=r*Math.cos(p1),r2=r*Math.cos(p2),y1=h*Math.sin(p1),y2=h*Math.sin(p2);v.push(Math.cos(a1)*r1,y1,Math.sin(a1)*r1,Math.cos(a2)*r1,y1,Math.sin(a2)*r1,Math.cos(a1)*r2,y2,Math.sin(a1)*r2);}}
  return new Float32Array(v);
}

function buildFlat(hw: number, hd: number, t: number): Float32Array {
  return new Float32Array([-hw,0,-hd,hw,0,-hd,hw,0,hd,-hw,0,-hd,hw,0,hd,-hw,0,hd]);
}
