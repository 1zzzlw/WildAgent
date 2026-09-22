export interface StoneBlockPattern { pattern: 'stone_block'; blockSize?: [number, number]; jointWidth?: number; mortarColor?: [number, number, number]; }
export interface RoofTilePattern { pattern: 'roof_tile'; tileSize?: [number, number]; overlap?: number; gapWidth?: number; mortarColor?: [number, number, number]; }
export type FacePattern = StoneBlockPattern | RoofTilePattern;

export function subdivideBoxShared(w:number,h:number,d:number,p?:((FacePattern|null)[])): {
  geometry:Float32Array; indices:Uint32Array; normals:Float32Array; vertexColors?:Float32Array; mortarColor?:[number,number,number]
} {
  const hasStone=p?.some(x=>x?.pattern==='stone_block'), hw=w/2,hh=h/2,hd=d/2;
  const JOINT_W=0.02; // 接缝宽 2cm

  // 计算每面的块参数
  const sizes=[[w,h],[w,h],[w,d],[w,d],[d,h],[d,h]];
  let mortarColor: [number,number,number] | undefined;
  const sps=sizes.map(([fw,fh],i)=>{
    const pat=p?.[i]; if(!pat||pat.pattern!=='stone_block') return null;
    const bw=pat.blockSize?.[0]??0.4, bh=pat.blockSize?.[1]??0.2;
    if (!mortarColor && pat.mortarColor) mortarColor = pat.mortarColor;
    const b=Math.max(1,Math.round(fw/bw)), r=Math.max(1,Math.round(fh/bh));
    const bW=(fw-(b-1)*JOINT_W)/b, bH=(fh-(r-1)*JOINT_W)/r; // 精确块宽/高
    const uSegs:{isJoint:boolean;w:number}[]=[];
    for (let bi=0; bi<b; bi++) {
      if (bi>0) uSegs.push({isJoint:true,w:JOINT_W});
      uSegs.push({isJoint:false,w:bW});
    }
    const vSegs:{isJoint:boolean;h:number}[]=[];
    for (let ri=0; ri<r; ri++) {
      if (ri>0) vSegs.push({isJoint:true,h:JOINT_W});
      vSegs.push({isJoint:false,h:bH});
    }
    return{b,r,bW,bH,uSegs,vSegs,fw,fh};
  });

  // 盒体 6 面
  const Fdefs=[
    [-hw,-hh,hd, w,0,0, 0,h,0, 0,0,1],    // +Z: corner(-hw,-hh,hd), u=+X, v=+Y → normal +Z
    [ hw,-hh,-hd, -w,0,0, 0,h,0, 0,0,-1],  // -Z: corner(hw,-hh,-hd), u=-X, v=+Y → normal -Z
    [ hw, hh,-hd, -w,0,0, 0,0,d, 0,1,0],   // +Y: corner(hw,hh,-hd), u=-X, v=+Z → normal +Y (fixed)
    [-hw,-hh,-hd, w,0,0, 0,0,d, 0,-1,0],   // -Y: corner(-hw,-hh,-hd), u=+X, v=+Z → normal -Y (fixed)
    [ hw,-hh,hd, 0,0,-d, 0,h,0, 1,0,0],    // +X: corner(hw,-hh,hd), u=-Z, v=+Y → normal +X
    [-hw,-hh,-hd, 0,0,d, 0,h,0, -1,0,0],   // -X: corner(-hw,-hh,-hd), u=+Z, v=+Y → normal -X
  ];

  const verts:number[]=[], cols:number[]=[], idx:number[]=[];
  for (let fi=0; fi<6; fi++) {
    const f=Fdefs[fi], sp=sps[fi];
    const [cx,cy,cz,ux,uy,uz,vx,vy,vz,nnx,nny,nnz]=f;
    if (!sp) continue; // 无图案暂不支持
    const uS=sp.uSegs, vS=sp.vSegs;

    // 生成每个四边形
    let uOff=0;
    for (let ui=0; ui<uS.length; ui++) {
      const us=uS[ui];
      let vOff=0;
      for (let vi=0; vi<vS.length; vi++) {
        const vs=vS[vi];
        const u0=uOff/sp.fw, u1=(uOff+us.w)/sp.fw, v0=vOff/sp.fh, v1=(vOff+vs.h)/sp.fh;
        const isJ=us.isJoint||vs.isJoint;
        // 逐顶点判断是否在面边界上：边界顶点不位移（防止相邻面对齐错位）
        const onEdge=(u:number,v:number)=>Math.abs(u)<1e-6||Math.abs(u-1)<1e-6||Math.abs(v)<1e-6||Math.abs(v-1)<1e-6;
        const disp=isJ?-0.008:0.004;
        const off0=onEdge(u0,v0)?0:disp, off1=onEdge(u1,v0)?0:disp;
        const off2=onEdge(u1,v1)?0:disp, off3=onEdge(u0,v1)?0:disp;
        const p=[[cx+ux*u0+vx*v0,cy+uy*u0+vy*v0,cz+uz*u0+vz*v0],
                [cx+ux*u1+vx*v0,cy+uy*u1+vy*v0,cz+uz*u1+vz*v0],
                [cx+ux*u1+vx*v1,cy+uy*u1+vy*v1,cz+uz*u1+vz*v1],
                [cx+ux*u0+vx*v1,cy+uy*u0+vy*v1,cz+uz*u0+vz*v1]];
        const qc=isJ?[0,0,0]:[1,1,1];
        const allP=[p[0],p[1],p[2],p[0],p[2],p[3]];
        const allOff=[off0,off1,off2,off0,off2,off3];
        const base=verts.length/3;
        for (let k=0; k<6; k++) {
          verts.push(allP[k][0]+nnx*allOff[k], allP[k][1]+nny*allOff[k], allP[k][2]+nnz*allOff[k]);
          cols.push(qc[0],qc[1],qc[2]);
          idx.push(base+k);
        }
        vOff+=vs.h;
      }
      uOff+=us.w;
    }
  }

  return {
    geometry: new Float32Array(verts),
    indices: new Uint32Array(idx),
    normals: computeNormals(verts, idx),
    vertexColors: hasStone?new Float32Array(cols):undefined,
    mortarColor,
  };
}

/** 从位移后的三角形计算顶点法线 */
function computeNormals(verts:number[],idx:number[]):Float32Array {
  const n=new Float32Array(verts.length);
  for (let i=0; i<idx.length; i+=3) {
    const ia=idx[i]*3, ib=idx[i+1]*3, ic=idx[i+2]*3;
    const ax=verts[ia],ay=verts[ia+1],az=verts[ia+2];
    const bx=verts[ib],by=verts[ib+1],bz=verts[ib+2];
    const cx=verts[ic],cy=verts[ic+1],cz=verts[ic+2];
    const ux=bx-ax,uy=by-ay,uz=bz-az, vx=cx-ax,vy=cy-ay,vz=cz-az;
    const nn=uy*vz-uz*vy, no=uz*vx-ux*vz, np=ux*vy-uy*vx;
    n[ia]+=nn;n[ia+1]+=no;n[ia+2]+=np;
    n[ib]+=nn;n[ib+1]+=no;n[ib+2]+=np;
    n[ic]+=nn;n[ic+1]+=no;n[ic+2]+=np;
  }
  for (let i=0; i<n.length; i+=3) {
    const l=Math.sqrt(n[i]*n[i]+n[i+1]*n[i+1]+n[i+2]*n[i+2]);
    if (l>1e-6) {n[i]/=l;n[i+1]/=l;n[i+2]/=l;}
  }
  return n;
}

/** 在四边形平面上生成 3D 叠瓦——每个瓦片是有厚度的凸起盒子，下行顶部被上行底部覆盖 */
export function subdivideQuad(
  corners: [number[], number[], number[], number[]],
  normal: [number, number, number],
  pattern: RoofTilePattern
): { geometry: Float32Array; indices: Uint32Array; normals: Float32Array; vertexColors: Float32Array; mortarColor?: [number,number,number] } {
  const [tileW, tileH] = pattern.tileSize ?? [0.3, 0.18];
  const gapW = pattern.gapWidth ?? 0.008;
  const gapH = 0.003; // 行间细缝 3mm
  const tileT = 0.012; // 瓦片厚度 1.2cm
  const mc = pattern.mortarColor ?? [0.3, 0.25, 0.22];

  const [bl, br, tr, tl] = corners;
  const [nnx, nny, nnz] = normal;

  // 四边形局部坐标轴
  const uVec = [br[0]-bl[0], br[1]-bl[1], br[2]-bl[2]];
  const vVec = [tl[0]-bl[0], tl[1]-bl[1], tl[2]-bl[2]];
  const quadW = Math.sqrt(uVec[0]**2 + uVec[1]**2 + uVec[2]**2);
  const quadH = Math.sqrt(vVec[0]**2 + vVec[1]**2 + vVec[2]**2);
  const uAxis = [uVec[0]/quadW, uVec[1]/quadW, uVec[2]/quadW];
  const vAxis = [vVec[0]/quadH, vVec[1]/quadH, vVec[2]/quadH];

  // 行列数
  const numCols = Math.max(1, Math.floor((quadW + gapW) / (tileW + gapW)));
  const numRows = Math.max(1, Math.floor((quadH + gapH) / (tileH + gapH)));
  const aTileW = (quadW - (numCols - 1) * gapW) / numCols;
  const aTileH = (quadH - (numRows - 1) * gapH) / numRows;

  // 辅助：在四边形上定位 3D 点
  const pt = (u:number, v:number) =>
    [bl[0] + u*uAxis[0] + v*vAxis[0], bl[1] + u*uAxis[1] + v*vAxis[1], bl[2] + u*uAxis[2] + v*vAxis[2]];
  const addFace = (list: number[][], verts:number[], cols:number[], idx:number[], c:[number,number,number]) => {
    let base = verts.length / 3;
    for (const p of list) { verts.push(p[0],p[1],p[2]); cols.push(c[0],c[1],c[2]); idx.push(base++); }
  };

  const verts: number[] = [], cols: number[] = [], idx: number[] = [];

  let uOff = 0;
  for (let ui = 0; ui < 2*numCols-1; ui++) {
    const isJointU = ui % 2 === 1;
    const usw = isJointU ? gapW : aTileW;
    let vOff = 0;
    for (let vi = 0; vi < 2*numRows-1; vi++) {
      const isJointV = vi % 2 === 1;
      const vsh = isJointV ? gapH : aTileH;

      if (isJointU || isJointV) {
        // 缝隙四边形（无凸起）
        const p0 = pt(uOff, vOff);
        const p1 = pt(uOff+usw, vOff);
        const p2 = pt(uOff+usw, vOff+vsh);
        const p3 = pt(uOff, vOff+vsh);
        addFace([p0,p1,p2, p0,p2,p3], verts, cols, idx, [0,0,0]);
      } else {
        // 瓦片 3D 盒子：前表面凸起 + 底部接缝面（左右接缝被相邻瓦片遮挡，顶部被上行覆盖）
        const p0 = pt(uOff, vOff);      // roof 平面四角
        const p1 = pt(uOff+usw, vOff);
        const p2 = pt(uOff+usw, vOff+vsh);
        const p3 = pt(uOff, vOff+vsh);
        // 前表面（沿法线外移 tileT）
        const q0 = [p0[0]+nnx*tileT, p0[1]+nny*tileT, p0[2]+nnz*tileT];
        const q1 = [p1[0]+nnx*tileT, p1[1]+nny*tileT, p1[2]+nnz*tileT];
        const q2 = [p2[0]+nnx*tileT, p2[1]+nny*tileT, p2[2]+nnz*tileT];
        const q3 = [p3[0]+nnx*tileT, p3[1]+nny*tileT, p3[2]+nnz*tileT];
        // 前表面（瓦片色）
        addFace([q0,q1,q2, q0,q2,q3], verts, cols, idx, [1,1,1]);
        // 底部接缝面（q3-q2 到 p3-p2，投射阴影，缝隙色）
        addFace([q3,q2,p2, q3,p2,p3], verts, cols, idx, [0,0,0]);
      }
      vOff += vsh;
    }
    uOff += usw;
  }

  return {
    geometry: new Float32Array(verts),
    indices: new Uint32Array(idx),
    normals: computeNormals(verts, idx),
    vertexColors: new Float32Array(cols),
    mortarColor: mc,
  };
}