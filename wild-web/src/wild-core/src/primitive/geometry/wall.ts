import type { WallParams, MeshData, Vec3 } from '../types';
import { boxWithHoles } from './box-with-holes';
import { indexTriList } from './mesh-helper';

const TARGET_TEXEL = 0.4;

export function buildWall(params: WallParams): MeshData[] {
  const { from, to, thickness, material } = params;
  const curve = (params as any).curve;
  const cutouts = (params as any)._cutouts;

  if (curve) {
    return buildCurvedWall(from, to, thickness, material || 'default', curve, cutouts);
  }

  const dx = to[0] - from[0];
  const dz = to[2] - from[2];
  const length = Math.sqrt(dx * dx + dz * dz);
  const height = Math.abs(to[1] - from[1]);

  let geometry: Float32Array, indices: Uint16Array;
  if (cutouts?.length) {
    const r = boxWithHoles(length, height, thickness, cutouts);
    geometry = r.geometry; indices = r.indices;
  } else {
    const raw = subdivideBox(length, height, thickness, TARGET_TEXEL);
    const i = indexTriList(raw);
    geometry = i.geometry; indices = i.indices;
  }

  const midX = (from[0] + to[0]) / 2;
  const midZ = (from[2] + to[2]) / 2;
  const midY = (from[1] + to[1]) / 2;
  const angle = Math.atan2(dz, dx);

  return [{
    geometry, indices: new Uint32Array(indices),
    transform: { position: [midX, midY, midZ], rotation: [0, angle, 0], scale: [1, 1, 1] },
    materialRef: material || 'default'
  }];
}

function buildCurvedWall(from: Vec3, to: Vec3, thickness: number, material: string, curve: any, cutouts?: any[]): MeshData[] {
  const height = Math.abs(to[1] - from[1]);
  const baseY = Math.min(from[1], to[1]);

  const segs = Array.isArray(curve) ? curve : [curve];
  if (segs.length !== 1 || segs[0].type !== 'arc') {
    const points = evalCurve(from, to, curve);
    const meshes: MeshData[] = [];
    for (let i = 0; i < points.length - 1; i++) {
      const [x1, z1] = points[i], [x2, z2] = points[i + 1];
      const segLen = Math.sqrt((x2 - x1) ** 2 + (z2 - z1) ** 2);
      if (segLen < 0.001) continue;
      const raw = createBoxGeometry(segLen, height, thickness);
      const { geometry, indices } = indexTriList(raw);
      meshes.push({
        geometry, indices: new Uint32Array(indices),
        transform: { position: [(x1+x2)/2, baseY+height/2, (z1+z2)/2], rotation: [0, Math.atan2(z2-z1, x2-x1), 0], scale: [1,1,1] },
        materialRef: material,
      });
    }
    return meshes;
  }

  // === 连续圆柱面网格，索引三角形（无顶点重复）===
  const arcSegCount = segs[0].segments || 32;
  const center = segs[0].center;
  const startRad = Math.atan2(from[2] - center[2], from[0] - center[0]);
  const sweepRad = segs[0].sweep * Math.PI / 180;
  const radius = Math.sqrt((from[0] - center[0]) ** 2 + (from[2] - center[2]) ** 2);
  const innerR = radius - thickness / 2;
  const outerR = radius + thickness / 2;

  const cutoutAngles = (cutouts || []).map(c => ({
    a1: startRad + (c.localX - c.localW / 2) / radius,
    a2: startRad + (c.localX + c.localW / 2) / radius,
    y1: c.localY, y2: c.localY + c.localH,
  }));

  // 顶点 + 法线（每角度 4 个：内下/内上/外下/外上）
  const verts: number[] = [], normals: number[] = [];
  for (let i = 0; i <= arcSegCount; i++) {
    const t = i / arcSegCount, a = startRad + t * sweepRad;
    const ca = Math.cos(a), sa = Math.sin(a);
    const xi = center[0] + innerR * ca, zi = center[2] + innerR * sa;
    const xo = center[0] + outerR * ca, zo = center[2] + outerR * sa;
    verts.push(xi, baseY, zi, xi, baseY + height, zi, xo, baseY, zo, xo, baseY + height, zo);
    normals.push(-ca, 0, -sa, -ca, 0, -sa, ca, 0, sa, ca, 0, sa);
  }

  // 纯索引三角形
  const idx: number[] = [];
  function addTri(i0: number, i1: number, i2: number) { idx.push(i0, i1, i2); }
  function addQuad(i0: number, i1: number, i2: number, i3: number) { addTri(i0, i1, i2); addTri(i0, i2, i3); }

  for (let i = 0; i < arcSegCount; i++) {
    const a1 = startRad + (i / arcSegCount) * sweepRad;
    const a2 = startRad + ((i + 1) / arcSegCount) * sweepRad;
    if (cutoutAngles.some(co => a2 > co.a1 && a1 < co.a2 && baseY + height > co.y1 + baseY && baseY < co.y2 + baseY)) continue;
    const b0 = i * 4, b1 = (i + 1) * 4;
    addQuad(b0+2, b0+3, b1+3, b1+2); // 外面
    addQuad(b0+1, b0+0, b1+0, b1+1); // 内面
    addQuad(b0+1, b0+3, b1+3, b1+1); // 顶面
    addQuad(b0+2, b0+0, b1+0, b1+2); // 底面
  }

  if (idx.length === 0) return [];
  return [{
    geometry: new Float32Array(verts), normals: new Float32Array(normals),
    indices: new Uint32Array(idx),
    transform: { position: [0, 0, 0], rotation: [0, 0, 0], scale: [1, 1, 1] },
    materialRef: material,
  }];
}

export function createBoxGeometry(w: number, h: number, d: number): Float32Array {
  const hw=w/2, hh=h/2, hd=d/2;
  return new Float32Array([
    -hw,-hh,hd,hw,-hh,hd,hw,hh,hd,-hw,-hh,hd,hw,hh,hd,-hw,hh,hd,
    hw,-hh,-hd,-hw,-hh,-hd,-hw,hh,-hd,hw,-hh,-hd,-hw,hh,-hd,hw,hh,-hd,
    -hw,hh,hd,-hw,hh,-hd,hw,hh,-hd,-hw,hh,hd,hw,hh,-hd,hw,hh,hd,
    -hw,-hh,-hd,-hw,-hh,hd,hw,-hh,hd,-hw,-hh,-hd,hw,-hh,hd,hw,-hh,-hd,
    hw,-hh,hd,hw,-hh,-hd,hw,hh,-hd,hw,-hh,hd,hw,hh,-hd,hw,hh,hd,
    -hw,-hh,-hd,-hw,-hh,hd,-hw,hh,hd,-hw,-hh,-hd,-hw,hh,hd,-hw,hh,-hd
  ]);
}

export function subdivideBox(w: number, h: number, d: number, step: number): Float32Array {
  const hw=w/2, hh=h/2, hd=d/2;
  const nx=Math.max(1,Math.round(w/step)), ny=Math.max(1,Math.round(h/step)), nz=Math.max(1,Math.round(d/step));
  const verts: number[]=[];
  function face(cx:number,cy:number,cz:number,ux:number,uy:number,uz:number,vx:number,vy:number,vz:number,nu:number,nv:number){
    for(let j=0;j<nv;j++) for(let i=0;i<nu;i++){
      const fui=i/nu,fuj=(i+1)/nu,fvi=j/nv,fvj=(j+1)/nv;
      const x0=cx+ux*fui+vx*fvi,y0=cy+uy*fui+vy*fvi,z0=cz+uz*fui+vz*fvi;
      const x1=cx+ux*fuj+vx*fvi,y1=cy+uy*fuj+vy*fvi,z1=cz+uz*fuj+vz*fvi;
      const x2=cx+ux*fuj+vx*fvj,y2=cy+uy*fuj+vy*fvj,z2=cz+uz*fuj+vz*fvj;
      const x3=cx+ux*fui+vx*fvj,y3=cy+uy*fui+vy*fvj,z3=cz+uz*fui+vz*fvj;
      verts.push(x0,y0,z0,x1,y1,z1,x2,y2,z2); verts.push(x0,y0,z0,x2,y2,z2,x3,y3,z3);
    }
  }
  face(0,0,hd,w,0,0,0,h,0,nx,ny); face(0,0,-hd,-w,0,0,0,h,0,nx,ny);
  face(0,hh,0,w,0,0,0,0,d,nx,nz); face(0,-hh,0,w,0,0,0,0,-d,nx,nz);
  face(hw,0,0,0,0,-d,0,h,0,nz,ny); face(-hw,0,0,0,0,d,0,h,0,nz,ny);
  return new Float32Array(verts);
}

export function evalCurve(from: Vec3, to: Vec3, curve: any): [number, number][] {
  const segs = Array.isArray(curve) ? curve : [curve];
  const points: [number, number][] = [];
  for (const seg of segs) {
    const t = seg.type || 'line', sn = seg.segments || 24;
    if (t === 'line') {
      const sx=points.length?points[points.length-1][0]:from[0], sz=points.length?points[points.length-1][1]:from[2];
      for(let i=0;i<=sn;i++) points.push([sx+(to[0]-sx)*i/sn,sz+(to[2]-sz)*i/sn]);
    } else if (t === 'arc') {
      const c=seg.center, sw=seg.sweep*Math.PI/180, r=Math.sqrt((from[0]-c[0])**2+(from[2]-c[2])**2);
      const sa=points.length?Math.atan2(points[points.length-1][1]-c[2],points[points.length-1][0]-c[0]):Math.atan2(from[2]-c[2],from[0]-c[0]);
      for(let i=0;i<=sn;i++){const a=sa+i/sn*sw;points.push([c[0]+r*Math.cos(a),c[2]+r*Math.sin(a)]);}
    } else if (t === 'ellipse') {
      const c=seg.center, rx=seg.radiusX, rz=seg.radiusZ, sa=(seg.startAngle??0)*Math.PI/180, sw=(seg.sweep??360)*Math.PI/180;
      for(let i=0;i<=sn;i++){const a=sa+i/sn*sw;points.push([c[0]+rx*Math.cos(a),c[2]+rz*Math.sin(a)]);}
    } else if (t === 'catenary') {
      const rise=seg.rise, sx=points.length?points[points.length-1][0]:from[0], sz=points.length?points[points.length-1][1]:from[2];
      const len=Math.sqrt((to[0]-sx)**2+(to[2]-sz)**2), dx=(to[0]-sx)/len, dz=(to[2]-sz)/len;
      for(let i=0;i<=sn;i++){const p=i/sn,a=p*len,ar=rise*Math.sin(p*Math.PI);points.push([sx+a*dx+ar*(-dz),sz+a*dz+ar*dx]);}
    } else {
      points.push([points.length?points[points.length-1][0]:from[0],points.length?points[points.length-1][1]:from[2]],[to[0],to[2]]);
    }
  }
  const r=[points[0]];for(let i=1;i<points.length;i++){const dx=points[i][0]-r[r.length-1][0],dz=points[i][1]-r[r.length-1][1];if(dx*dx+dz*dz>0.0001)r.push(points[i]);}
  return r;
}
