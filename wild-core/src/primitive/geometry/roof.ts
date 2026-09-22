import type { RoofParams, MeshData } from '../types';
import { generateArchitecturalSurfaceAttributes, indexTriList } from './mesh-helper';

/**
 * 屋顶类型登记表 —— 每种屋顶的全部差异都在这里声明一次。
 *
 * 改造前，`roofType === 'gable' || roofType === 'hip'` 这类判断散落在 `roof.ts`
 * 与 `resolver.ts` 里各写一份，且 `chinese_curved` / `chinese_pagoda` 直接在
 * `buildRoof` 顶部早返回、**完全绕过**共享的檐口路径——于是"给所有屋顶加檐口"
 * 这种改进对它们无效，而每新增一种屋顶又要在多处补类型判断。
 *
 * 现在 `buildRoof` 内部**一个 roofType 分支都没有**：主体形状与檐口能力都由本表
 * 提供。新增一种屋顶 = 加一行（主体生成器 + 两项能力声明），檐口代码一行不用碰。
 */
interface RoofCapabilities {
  /** 屋面朝上面有可提取的外边界 → 可挂檐口线脚（封檐板/滴水线/博风板/圈梁） */
  eaveTrim: boolean;
  /** 山墙端需要贴面板（双坡特有；四坡/穹顶/曲面无山墙端面） */
  gableEndPanels: boolean;
}

/** `buildRoof` 传给主体生成器的派生量，避免每个生成器各算一遍。 */
interface RoofBodyContext {
  hw: number;
  hd: number;
  height: number;
  thickness: number;
  pos: number[];
}

/** 主体形状生成器：产出该屋顶类型的主体网格（不含檐口线脚）。 */
type RoofBodyBuilder = (params: RoofParams, ctx: RoofBodyContext) => MeshData[];

interface RoofTypeSpec extends RoofCapabilities {
  body: RoofBodyBuilder;
}

/**
 * 把"顶点汤"生成器包成统一签名：补索引、补法线/UV、补材质与变换。
 *
 * 四类薄壳屋顶（gable/hip/flat/dome）共用这一层；中式两类自带生成器
 * （曲面要产出内外双表面，重檐要逐层产出坡面与檐下底面），直接登记函数。
 */
function tessellatedBody(make: (ctx: RoofBodyContext) => Float32Array): RoofBodyBuilder {
  return (params, ctx) => {
    const { geometry, indices } = indexTriList(make(ctx));
    const attributes = generateArchitecturalSurfaceAttributes(geometry);  // 生成法线和 UV
    return [{
      geometry,
      indices: new Uint32Array(indices),
      normals: attributes.normals,
      uvs: attributes.uvs,
      transform: { position: [ctx.pos[0], ctx.pos[1], ctx.pos[2]], rotation: [0, 0, 0], scale: [1, 1, 1] },
      materialRef: params.material || 'default',
    }];
  };
}

const ROOF_TYPES: Record<string, RoofTypeSpec> = {
  gable: {
    eaveTrim: true, gableEndPanels: true,
    body: tessellatedBody((c) => buildGable(c.hw, c.hd, c.height, c.thickness)),
  },
  hip: {
    eaveTrim: true, gableEndPanels: false,
    body: tessellatedBody((c) => buildHip(c.hw, c.hd, c.height, c.thickness)),
  },
  flat: {
    eaveTrim: true, gableEndPanels: false,
    body: tessellatedBody((c) => buildFlat(c.hw, c.hd, c.thickness)),
  },
  dome: {
    eaveTrim: true, gableEndPanels: false,
    body: tessellatedBody((c) => buildDome(c.hw, c.hd, c.height, c.thickness)),
  },
  chinese_curved: {
    eaveTrim: true, gableEndPanels: false,
    body: (params, ctx) => buildChineseCurved(params, ctx.pos),
  },
  // 重檐每层自成一套坡面 + 檐下底面，屋面朝上面是"环带"（外沿与上层根各成一环），
  // 直接套通用扫掠会在每层顶部也长出一圈线脚。暂不声明该能力，等重檐檐口单独建模。
  chinese_pagoda: {
    eaveTrim: false, gableEndPanels: false,
    body: (params, ctx) => buildPagoda(params, ctx.pos),
  },
};

/** 查询某屋顶类型的能力声明（供门禁与诊断使用）；未登记的类型按"有檐口、无山墙端饰面"处理。 */
export function capabilitiesOf(roofType: string): RoofCapabilities {
  const spec = ROOF_TYPES[roofType];
  return spec
    ? { eaveTrim: spec.eaveTrim, gableEndPanels: spec.gableEndPanels }
    : { eaveTrim: true, gableEndPanels: false };
}

export function buildRoof(params: RoofParams): MeshData[] {
  const { roofType, span, depth, height, thickness } = params;
  const spec = ROOF_TYPES[roofType];
  if (!spec) throw new Error(`Unsupported roofType: ${roofType}`);

  const ctx: RoofBodyContext = {
    hw: span / 2,
    hd: depth / 2,
    height,
    thickness,
    pos: (params as any).position ?? [0, 0, 0],
  };

  // 主体 + 檐口，全部类型走同一条路径：中式两类不再早返回，因此"给所有屋顶加
  // 檐口"这类改动对它们同样生效。
  return appendEaveTrim(spec.body(params, ctx), params, ctx, spec);
}

/**
 * 统一追加檐口线脚（全部屋顶类型共用这一条路径）。
 *
 * 只在 resolver 注入了宿主墙上下文（渲染私有字段 `_eave`）时生成；未注入时
 * 输出与历史完全一致，因此对不经过 resolver 的直接调用零影响。
 *
 * 檐口环从**主体第一块网格的朝上面**提取，因此这里不做任何 roofType 判断 ——
 * 是否生成由 `spec.eaveTrim` 声明。
 */
function appendEaveTrim(
  meshes: MeshData[],
  params: RoofParams,
  ctx: RoofBodyContext,
  spec: RoofTypeSpec,
): MeshData[] {
  if (!spec.eaveTrim) return meshes;
  const trimSpec = resolveEaveTrim(params, ctx.hw, ctx.hd, ctx.height, ctx.thickness);
  if (!trimSpec) return meshes;

  const main = meshes[0];
  if (!main) return meshes;
  const geometry = main.geometry;
  const indices = main.indices ?? Uint32Array.from({ length: geometry.length / 3 }, (_, k) => k);

  const trimGeometry = buildEaveTrim(geometry, indices, trimSpec);
  if (spec.gableEndPanels) {
    appendGableEndPanels(trimGeometry, ctx.hw, ctx.hd, ctx.height, Math.max(ctx.thickness, 0.02), trimSpec);
  }
  if (trimGeometry.length === 0) return meshes;

  // 线脚是若干互相独立的闭合实体；合并成一个网格、单独材质。
  // 各实体不共享顶点，闭合性与体积可逐分量校验（见 verify-roof-solid.mjs）。
  const tessellated = indexTriList(new Float32Array(trimGeometry));
  const trimAttributes = generateArchitecturalSurfaceAttributes(tessellated.geometry);
  meshes.push({
    geometry: tessellated.geometry,
    indices: new Uint32Array(tessellated.indices),
    normals: trimAttributes.normals,
    uvs: trimAttributes.uvs,
    transform: { position: [ctx.pos[0], ctx.pos[1], ctx.pos[2]], rotation: [0, 0, 0], scale: [1, 1, 1] },
    materialRef: trimSpec.material,
  });
  return meshes;
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

  // ── 绕序约定（四个 reverse 标志的由来，勿凭直觉改）──
  //
  // 壳体按 side 拆成 x≤0 / x≥0 两半，在屋脊（x=0）处共用一条边。两半的 x 增长
  // 方向相反，所以**必然有一半要反绕**，否则屋脊处会出现"同向共享边"（非流形）。
  // 另一半的绝对朝向由外法线决定：
  //
  //   side=+1：自然绕序法线 ≈ (-x,-y)，朝内且朝下 → 必须反绕
  //   side=-1：自然绕序法线 ≈ (-x,+y)，即朝外朝上   → 保持自然绕序
  //
  // 内表面取与外表面相反的绕序；檐口封边、前后山面封边再各取一次相反，才能保证
  // 每条边恰好被 1 正 1 反两个三角形共享。历史实现四个 reverse 标志**全部取反**，
  // 整个壳体从内向外生成——表现为体积为负、法线一半朝上一半朝下（屋面不受光、
  // 发暗），檐口一圈还留下 52 条同向共享边（不闭合）。
  for (const side of [-1, 1] as const) {
    for (let ci = 0; ci < crossSegments; ci++) {
      const u0 = ci / crossSegments, u1 = (ci + 1) / crossSegments;
      for (let di = 0; di < depthSegments; di++) {
        const v0 = di / depthSegments, v1 = (di + 1) / depthSegments;
        const a = point(side, ci, di, false);
        const b = point(side, ci + 1, di, false);
        const c = point(side, ci + 1, di + 1, false);
        const d = point(side, ci, di + 1, false);
        quad(a, b, c, d, [u0, v0], [u1, v0], [u1, v1], [u0, v1], side === 1);

        const ai = point(side, ci, di, true);
        const bi = point(side, ci + 1, di, true);
        const ci2 = point(side, ci + 1, di + 1, true);
        const di2 = point(side, ci, di + 1, true);
        quad(ai, bi, ci2, di2, [u0, v0], [u1, v0], [u1, v1], [u0, v1], side === -1);
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
          (depthIndex === 0) === (side === -1),
        );
      }
    }
  }

  const geometry = new Float32Array(vertices);
  // 与 gable/hip/dome/flat 走同一条属性生成路径：硬边法线 + 逐面 UV。
  // 壳体此前只给 uvs 不给 normals，渲染端只能回退到 computeVertexNormals；
  // 顶点不共享时两者数值等价，但显式给出才能让法线符号确定地跟随绕序。
  // UV 保留壳体自己的参数化展开——曲面若用逐面投影会在每个分段留下接缝。
  const attributes = generateArchitecturalSurfaceAttributes(geometry);
  const meshes: MeshData[] = [{
    geometry,
    indices: Uint32Array.from({ length: geometry.length / 3 }, (_, index) => index),
    normals: attributes.normals,
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
    //
    // `corners` 按 XZ 平面逆时针排列，因此水平四边形（见下方檐口底面）会得到朝下的
    // 法线——这在底面上是对的，但坡面是朝上的面，必须反绕，否则整圈屋面法线朝下、
    // 不受光而发暗（同时一旦开启背面剔除就会整片消失）。
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
        a[0],a[1],a[2], c[0],c[1],c[2], b[0],b[1],b[2],
        a[0],a[1],a[2], d[0],d[1],d[2], c[0],c[1],c[2],
      ]));
      const slopeAttrs = generateArchitecturalSurfaceAttributes(verts.geometry);
      meshes.push({
        geometry: verts.geometry, indices: new Uint32Array(verts.indices),
        normals: slopeAttrs.normals, uvs: slopeAttrs.uvs,
        transform: { position: [0,0,0], rotation: [0,0,0], scale: [1,1,1] },
        materialRef: mat,
      });
    }

    // 檐口底面（檐口四角围成的矩形）。与坡面相反，这里保留朝下的绕序——
    // 它是檐下的可见面。
    const btmVerts = indexTriList(new Float32Array([
      corners[0][0],corners[0][1],corners[0][2],
      corners[1][0],corners[1][1],corners[1][2],
      corners[2][0],corners[2][1],corners[2][2],
      corners[0][0],corners[0][1],corners[0][2],
      corners[2][0],corners[2][1],corners[2][2],
      corners[3][0],corners[3][1],corners[3][2],
    ]));
    const btmAttrs = generateArchitecturalSurfaceAttributes(btmVerts.geometry);
    meshes.push({
      geometry: btmVerts.geometry, indices: new Uint32Array(btmVerts.indices),
      normals: btmAttrs.normals, uvs: btmAttrs.uvs,
      transform: { position: [0,0,0], rotation: [0,0,0], scale: [1,1,1] },
      materialRef: mat,
    });
  }

  return meshes;
}

/**
 * 追加一个三角面，跳过退化三角形。
 *
 * 零面积三角形（例如四坡顶在 ridgeHalf=0 时的梯形塌缩）会让 renderer 的
 * computeVertexNormals 归一化 0 向量得到 NaN，进而整块屋面变黑。这里提前
 * 剔除，保证输出始终是可安全计算法线的实体。
 */
function pushSolidTriangle(out: number[], a: number[], b: number[], c: number[]): void {
  const ux = b[0] - a[0], uy = b[1] - a[1], uz = b[2] - a[2];
  const vx = c[0] - a[0], vy = c[1] - a[1], vz = c[2] - a[2];
  const nx = uy * vz - uz * vy, ny = uz * vx - ux * vz, nz = ux * vy - uy * vx;
  if (nx * nx + ny * ny + nz * nz < 1e-16) return;
  out.push(a[0], a[1], a[2], b[0], b[1], b[2], c[0], c[1], c[2]);
}

/**
 * 双坡屋顶实体（含真实板厚、闭合檐口与封闭山墙）。
 *
 * 生成实心楔形体（三角柱），而非空心框架。
 * - 屋面外表面：檐口 y=0 → 屋脊 y=height
 * - 板厚向下：底面 y=-thickness
 * - 檐口立板：X=±hw 处的竖直面（厚度可见）
 * - 山墙端面：Z=±hd 处封闭
 */
function buildGable(hw: number, hd: number, h: number, t: number): Float32Array {
  const thick = Math.max(t, 0.02);
  const v: number[] = [];
  const pushTri = (a: number[], b: number[], c: number[]) => pushSolidTriangle(v, a, b, c);
  const pushQuad = (a: number[], b: number[], c: number[], d: number[]) => {
    pushTri(a, b, c); pushTri(a, c, d);
  };

  const eaveTop = 0, ridgeTop = h, eaveBot = -thick;

  // ── 外壳：屋面 + 底板 + 檐口立板 ──
  // 左坡屋面（外表面）
  pushQuad([-hw, eaveTop, -hd], [-hw, eaveTop, hd], [0, ridgeTop, hd], [0, ridgeTop, -hd]);
  // 右坡屋面（外表面）
  pushQuad([0, ridgeTop, -hd], [0, ridgeTop, hd], [hw, eaveTop, hd], [hw, eaveTop, -hd]);
  
  // 板底（水平面，法线朝下）
  pushQuad([-hw, eaveBot, hd], [-hw, eaveBot, -hd], [hw, eaveBot, -hd], [hw, eaveBot, hd]);
  
  // 左檐口立板（X=-hw）
  pushQuad([-hw, eaveBot, -hd], [-hw, eaveBot, hd], [-hw, eaveTop, hd], [-hw, eaveTop, -hd]);
  // 右檐口立板（X=+hw）
  pushQuad([hw, eaveBot, hd], [hw, eaveBot, -hd], [hw, eaveTop, -hd], [hw, eaveTop, hd]);

  // ── 端面封闭：Z=±hd 处的五边形截面 ──
  // 这是实心楔形体的前后端面，必须完整填充
  const pushEndCap = (z: number, facePositiveZ: boolean) => {
    const p0 = [-hw, eaveBot, z];    // 左下
    const p1 = [hw, eaveBot, z];     // 右下
    const p2 = [hw, eaveTop, z];     // 右檐口
    const p3 = [0, ridgeTop, z];     // 屋脊
    const p4 = [-hw, eaveTop, z];    // 左檐口
    
    // 五边形扇形剖分（从 p0 出发）
    const fan: number[][][] = [
      [p0, p1, p2],  // 底部矩形的下三角
      [p0, p2, p3],  // 右侧屋面三角
      [p0, p3, p4],  // 左侧屋面三角
    ];
    
    for (const tri of fan) {
      if (facePositiveZ) pushTri(tri[0], tri[1], tri[2]);
      else pushTri(tri[2], tri[1], tri[0]);  // 翻转法线
    }
  };
  
  pushEndCap(-hd, false);  // 后端面（法线朝 -Z）
  pushEndCap(hd, true);    // 前端面（法线朝 +Z）

  return new Float32Array(v);
}

/**
 * 四坡屋顶实体（含真实板厚与闭合檐口）。
 *
 * 与双坡共用同一约定：参考面（檐口 y=0 → 屋脊 y=height）是屋面外表面，
 * 板厚向下增厚，檐口四周用 thickness 高的立板封闭。
 */
function buildHip(hw: number, hd: number, h: number, t: number): Float32Array {
  const thick = Math.max(t, 0.02);
  const v: number[] = [];
  const pushTri = (a: number[], b: number[], c: number[]) => pushSolidTriangle(v, a, b, c);
  const pushQuad = (a: number[], b: number[], c: number[], d: number[]) => {
    pushTri(a, b, c); pushTri(a, c, d);
  };

  const alongZ = hd >= hw;
  const ridgeHalf = Math.max(0, (alongZ ? hd : hw) - (alongZ ? hw : hd));
  const c: number[][] = [[-hw, 0, -hd], [hw, 0, -hd], [hw, 0, hd], [-hw, 0, hd]];
  const r: number[][] = alongZ
    ? [[0, h, -ridgeHalf], [0, h, ridgeHalf]]
    : [[-ridgeHalf, h, 0], [ridgeHalf, h, 0]];

  // 每个坡面的顶点序（均按外法线朝上给出）。
  // 屋脊走向改变时，三角坡与梯形坡的归属也随之互换，必须分开列举：
  //   alongZ：山面在 ±Z（三角），坡面在 ±X（梯形）
  //   alongX：山面在 ±X（三角），坡面在 ±Z（梯形）
  const topFaces: number[][][] = alongZ
    ? [
        [c[1], c[0], r[0]], [c[3], c[2], r[1]],
        [c[2], c[1], r[0], r[1]], [c[0], c[3], r[1], r[0]],
      ]
    : [
        [c[2], c[1], r[1]], [c[0], c[3], r[0]],
        [c[1], c[0], r[0], r[1]], [c[3], c[2], r[1], r[0]],
      ];
  const drop = (p: number[]) => [p[0], p[1] - thick, p[2]];
  const emitSurface = (faces: number[][][], flip: boolean) => {
    for (const face of faces) {
      const ordered = flip ? [...face].reverse() : face;
      if (ordered.length === 3) pushTri(ordered[0], ordered[1], ordered[2]);
      else pushQuad(ordered[0], ordered[1], ordered[2], ordered[3]);
    }
  };

  emitSurface(topFaces, false);                                   // 屋面（法线朝上）
  emitSurface(topFaces.map(face => face.map(drop)), true);         // 底面（整体下移并翻转绕序）

  // ── 檐口四周封边：矩形周圈的板厚立面 ──
  pushQuad([-hw, -thick, hd], [hw, -thick, hd], [hw, 0, hd], [-hw, 0, hd]);       // +Z
  pushQuad([hw, -thick, -hd], [-hw, -thick, -hd], [-hw, 0, -hd], [hw, 0, -hd]);   // -Z
  pushQuad([-hw, -thick, -hd], [-hw, -thick, hd], [-hw, 0, hd], [-hw, 0, -hd]);   // -X
  pushQuad([hw, -thick, hd], [hw, -thick, -hd], [hw, 0, -hd], [hw, 0, hd]);       // +X

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
    // 顶面（朝上，法线 +Y）。
    // 绕序约定：俯视 XZ 平面时，(x,z) 逆时针走一圈得到的是 -Y 法线，所以朝上面
    // 必须按**顺时针**给点。这里曾经给反了 —— 结果薄板顶面法线朝下，开背面剔除
    // 后可见顶面被剔掉、实体也不水密（`.workbuddy/diag/verify-roof-solid.mjs` 的
    // flat 用例会抓到"未配对边 8 / 体积 8 ≠ 24"）。
    -hw, yTop, -hd,   hw, yTop,  hd,   hw, yTop, -hd,
    -hw, yTop, -hd,  -hw, yTop,  hd,   hw, yTop,  hd,
    // 底面（朝下，法线 -Y）
    -hw, yBot,  hd,   hw, yBot, -hd,   hw, yBot,  hd,
    -hw, yBot,  hd,  -hw, yBot, -hd,   hw, yBot, -hd,
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

// ══════════════════════════════════════════════════════════════════════
// 檐口线脚（封檐板 / 滴水线 / 博风板 / 山墙饰面）
//
// 设计约束（改动前必读）：
//  1. 全部输出为**互相独立的闭合实体**（各实体不共享顶点），因此可以逐分量
//     校验水密性、欧拉示性数与体积（`verify-roof-solid.mjs`）。
//  2. 每一个实体都必须外法线朝外、无退化三角形；`audit-winding.mjs` 会全量检查。
//  3. 不得与屋面自身的外表面**共面**（否则 Z-fighting）：
//     封檐板一律向屋面内侧 `embed` 一段，饰面板与山墙端面之间留 `panelGap` 间隙。
//  4. 尺寸必须随形体尺度缩放，避免小体量屋顶被巨型线脚压垮。
//
// 触发条件：`params._eave` 存在（由 `resolver.ts` 依据承托墙注入的渲染私有字段）。
// 未注入时完全不生成，历史行为不变。
// ══════════════════════════════════════════════════════════════════════

/** 檐口线脚尺寸（局部坐标，屋顶原点为檐口基准高度 y=0） */
interface EaveTrimSpec {
  material: string;
  /** 封檐板在檐口线以下的可见高度（= 用户看到的"屋檐厚度"） */
  drop: number;
  /** 相对屋面外沿的水平挑出 */
  outset: number;
  /** 嵌入屋面内侧的深度（消除共面 Z-fighting） */
  embed: number;
  /** 高出檐口线的封边量（把屋面边沿包住） */
  top: number;
  /** 滴水线：额外挑出与下垂 */
  lipProtrusion: number;
  lipDrop: number;
  /** 山墙饰面板厚度与离屋面端面的间隙 */
  panelThickness: number;
  panelGap: number;
}

const EAVE_MIN_DROP = 0.10;
const EAVE_MAX_DROP = 0.34;

function clampRange(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

/** 依据形体尺度推导线脚尺寸；`_eave` 里给出的数值可逐项覆盖。 */
function resolveEaveTrim(
  params: RoofParams,
  hw: number,
  hd: number,
  _height: number,
  thickness: number,
): EaveTrimSpec | null {
  const raw = (params as any)._eave;
  if (!raw || typeof raw !== 'object') return null;
  const thick = Math.max(thickness, 0.02);
  const num = (key: string, fallback: number): number => {
    const value = Number((raw as any)[key]);
    return Number.isFinite(value) && value > 0 ? value : fallback;
  };
  // 实测：既有蓝图跨度 2.4～60m，0.04×短边 + 双端钳制后落在 0.10～0.34m
  const scaled = clampRange(Math.min(hw, hd) * 2 * 0.04, EAVE_MIN_DROP, EAVE_MAX_DROP);
  const drop = num('drop', Math.max(thick * 1.5, scaled));
  const outset = num('outset', clampRange(drop * 0.4, 0.05, 0.16));
  const material = typeof (raw as any).material === 'string' && (raw as any).material
    ? (raw as any).material
    : (params.material || 'default');
  return {
    material,
    drop,
    outset,
    embed: num('embed', 0.03),
    top: num('top', 0.02),
    lipProtrusion: num('lipProtrusion', 0.035),
    lipDrop: num('lipDrop', 0.05),
    panelThickness: num('panelThickness', 0.02),
    panelGap: num('panelGap', 0.002),
  };
}

/** 追加一个三角面并保持外法线朝外；退化三角形跳过（沿用 pushSolidTriangle 的判据）。 */
function pushSolidQuad(out: number[], a: number[], b: number[], c: number[], d: number[]): void {
  pushSolidTriangle(out, a, b, c);
  pushSolidTriangle(out, a, c, d);
}

// ══════════════════════════════════════════════════════════════════════
// 檐口通用算子：从屋面自身提取"檐口环"，沿环扫掠线脚截面
//
// 旧实现按 roofType 分 gable / hip 两支，手写轴对齐长方体拼封檐板 + 滴水线，
// gable 再额外拼 Λ 形博风板与山墙饰面。问题有二：
//
//   1. 只认 gable|hip —— 曲面屋顶 / 穹顶 / 平屋顶一律没有檐口，而且每加一种
//      屋顶就要再写一支，渲染引擎随类型数线性膨胀；
//   2. 拼装式的"四条盒子"在转角处靠 `endOverhang` 互相重叠遮挡，转角处理
//      和尺寸耦合在一起，改一处尺寸要同时改七八处数字。
//
// 通用写法：**檐口就是屋面"朝上面"的外边界**。把该边界提取成一圈折线，
// 沿它扫掠同一个截面，就同时得到
//   · 水平段 → 封檐板 + 滴水线
//   · 斜段   → 博风板
//   · 圆环段 → 穹顶 / 曲面屋顶的圈梁
// 一个算子覆盖全部屋顶类型，新增屋顶类型不必再碰檐口代码。
//
// 输出方向不靠手推绕序（那正是 chinese_curved 壳体出过错的地方），而是每个
// 构件算一次有向体积，为负就整体反绕 —— 由构造保证外法线朝外。
// ══════════════════════════════════════════════════════════════════════

type Pt3 = [number, number, number];

/** 朝上面判据：法线 y 分量占比高于该值才算屋面（竖直面 / 朝下面排除在外）。 */
const EAVE_UP_MIN_NY = 0.05;

/** 折线转角超过该角度就断成独立构件：转角处直接端封，避免斜接尖刺（屋脊尖端近 180° 反转）。 */
const EAVE_RUN_BREAK_COS = Math.cos((75 * Math.PI) / 180);

/**
 * 提取屋面"朝上面"的外边界环（局部坐标，与传入几何同一坐标系）。
 *
 * 做法：只取向上朝天的三角形，按无向边统计使用次数；只被用到一次的边就是
 * 该面片集合的边界，再首尾相接串成环。轮廓是矩形就得到 4 条直边，是圆形就
 * 得到一圈折线，是曲面屋顶就得到那条起翘的檐口线——无需按类型分支。
 *
 * 导出供离线探针（`.workbuddy/diag/probe-*.mjs`）调用真实实现：此前探针各自
 * 抄了一份同样的判据，算子改了探针不跟着改，会拿旧结论误导判断——本项目的
 * 文档里记过这类漂移坑，直接从源头导出即可根除。
 */
export function extractEaveLoops(geometry: Float32Array, indices: Uint32Array): Pt3[][] {
  // 键必须把 -0 归一到 0：`(-0).toFixed(4)` 得到 "-0.0000"，与 "0.0000" 既不相等
  // 也不会在 Map 上命中同一条边。穹顶一圈赤道线里有 cos(π/2)=6.1e-17 反号后的
  // -0 顶点，配不上对就被误判成边界，于是线脚顺着经线一路爬到极点。这一步归一
  // 是"朝上面边界"能被正确识别的前提。
  const coord = (v: number) => {
    const s = v.toFixed(4);
    return /^-0\.0*$/.test(s) ? s.slice(1) : s;
  };
  const vk = (i: number) => `${coord(geometry[i * 3])},${coord(geometry[i * 3 + 1])},${coord(geometry[i * 3 + 2])}`;
  const pt = (i: number): Pt3 => [geometry[i * 3], geometry[i * 3 + 1], geometry[i * 3 + 2]];

  const uses = new Map<string, Array<[number, number]>>();
  for (let t = 0; t + 2 < indices.length; t += 3) {
    const a = indices[t], b = indices[t + 1], c = indices[t + 2];
    const p = pt(a), q = pt(b), r = pt(c);
    const ux = q[0] - p[0], uy = q[1] - p[1], uz = q[2] - p[2];
    const vx = r[0] - p[0], vy = r[1] - p[1], vz = r[2] - p[2];
    const nx = uy * vz - uz * vy;
    const ny = uz * vx - ux * vz;
    const nz = ux * vy - uy * vx;
    const len = Math.hypot(nx, ny, nz);
    if (len < 1e-12 || ny / len <= EAVE_UP_MIN_NY) continue;
    for (const [i, j] of [[a, b], [b, c], [c, a]] as Array<[number, number]>) {
      const ki = vk(i), kj = vk(j);
      const und = ki < kj ? `${ki}|${kj}` : `${kj}|${ki}`;
      const bucket = uses.get(und);
      if (bucket) bucket.push([i, j]);
      else uses.set(und, [[i, j]]);
    }
  }

  const boundary: Array<{ i: number; j: number; used: boolean }> = [];
  for (const dirs of uses.values()) {
    if (dirs.length === 1) boundary.push({ i: dirs[0][0], j: dirs[0][1], used: false });
  }
  const byStart = new Map<string, number[]>();
  boundary.forEach((edge, index) => {
    const k = vk(edge.i);
    const bucket = byStart.get(k);
    if (bucket) bucket.push(index);
    else byStart.set(k, [index]);
  });

  const loops: Pt3[][] = [];
  for (let s = 0; s < boundary.length; s++) {
    if (boundary[s].used) continue;
    const loop: Pt3[] = [];
    let cursor = s;
    while (cursor >= 0 && !boundary[cursor].used) {
      boundary[cursor].used = true;
      loop.push(pt(boundary[cursor].i));
      const candidates = byStart.get(vk(boundary[cursor].j));
      cursor = candidates ? (candidates.find((x) => !boundary[x].used) ?? -1) : -1;
    }
    if (loop.length >= 3) loops.push(loop);
  }
  return loops;
}

/** 把一圈折线按转角切段；平滑闭合环整体保留（closed=true，扫掠时首尾相接、不做端封）。 */
export function splitEaveRuns(loop: Pt3[]): Array<{ pts: Pt3[]; closed: boolean }> {
  const n = loop.length;
  const breaks: number[] = [];
  for (let i = 0; i < n; i++) {
    const prev = loop[(i - 1 + n) % n], cur = loop[i], next = loop[(i + 1) % n];
    const inX = cur[0] - prev[0], inZ = cur[2] - prev[2];
    const outX = next[0] - cur[0], outZ = next[2] - cur[2];
    const lin = Math.hypot(inX, inZ), lout = Math.hypot(outX, outZ);
    if (lin < 1e-9 || lout < 1e-9) { breaks.push(i); continue; }
    const cos = (inX * outX + inZ * outZ) / (lin * lout);
    if (cos < EAVE_RUN_BREAK_COS) breaks.push(i);
  }
  if (breaks.length === 0) return [{ pts: loop, closed: true }];

  const runs: Array<{ pts: Pt3[]; closed: boolean }> = [];
  for (let b = 0; b < breaks.length; b++) {
    const from = breaks[b];
    const to = breaks[(b + 1) % breaks.length];
    const pts: Pt3[] = [];
    for (let i = from; ; i = (i + 1) % n) {
      pts.push(loop[i]);
      if (i === to) break;
    }
    if (pts.length >= 2) runs.push({ pts, closed: false });
  }
  return runs;
}

/** 有向体积为负则整体反绕，保证构件外法线朝外。 */
function orientSolidOutward(tris: number[]): number[] {
  let volume = 0;
  for (let o = 0; o + 8 < tris.length; o += 9) {
    const ax = tris[o], ay = tris[o + 1], az = tris[o + 2];
    const bx = tris[o + 3], by = tris[o + 4], bz = tris[o + 5];
    const cx = tris[o + 6], cy = tris[o + 7], cz = tris[o + 8];
    volume += (ax * (by * cz - bz * cy) - ay * (bx * cz - bz * cx) + az * (bx * cy - by * cx)) / 6;
  }
  if (volume >= 0) return tris;
  const flipped: number[] = [];
  for (let o = 0; o + 8 < tris.length; o += 9) {
    flipped.push(
      tris[o], tris[o + 1], tris[o + 2],
      tris[o + 6], tris[o + 7], tris[o + 8],
      tris[o + 3], tris[o + 4], tris[o + 5],
    );
  }
  return flipped;
}

/**
 * 沿一段檐口折线扫掠线脚截面，返回闭合实体的三角面。
 *
 * 截面定义在 (u=水平外挑, v=竖直) 平面里：封檐板 + 外下方滴水线，合成一个
 * 6 边形。逐点取"背离檐口环质心"的水平方向作为外挑方向，转角处自然形成斜接。
 */
function sweepEaveRun(
  pts: Pt3[],
  closed: boolean,
  spec: EaveTrimSpec,
  centroid: [number, number],
): number[] {
  // 截面（局部原点在檐口线上，u 向外、v 向上）：
  //   封檐板主体 [-embed, outset] × [-drop, top]，外下方再挂一道滴水线。
  //   滴水线向板内侧塞进 embed、只在板实体内部相接，避免同一平面上两个面共面闪烁。
  const profile: Array<[number, number]> = [
    [-spec.embed, spec.top],
    [spec.outset, spec.top],
    [spec.outset, -spec.drop],
    [spec.outset + spec.lipProtrusion, -spec.drop],
    [spec.outset + spec.lipProtrusion, -spec.drop - spec.lipDrop],
    [spec.outset - spec.embed, -spec.drop - spec.lipDrop],
    [spec.outset - spec.embed, -spec.drop],
    [-spec.embed, -spec.drop],
  ];
  const m = profile.length;
  const count = pts.length;
  const out: number[] = [];

  // 逐点外挑方向：相邻两条水平边的法线平均（转角处即斜接方向）
  const outward: Array<[number, number]> = [];
  for (let i = 0; i < count; i++) {
    const prev = pts[(i - 1 + count) % count], cur = pts[i], next = pts[(i + 1) % count];
    const dirs: Array<[number, number]> = [];
    const push = (ax: number, az: number, bx: number, bz: number) => {
      const dx = bx - ax, dz = bz - az;
      const len = Math.hypot(dx, dz);
      if (len > 1e-9) dirs.push([dz / len, -dx / len]);
    };
    if (closed || i > 0) push(prev[0], prev[2], cur[0], cur[2]);
    if (closed || i < count - 1) push(cur[0], cur[2], next[0], next[2]);
    let ux = 0, uz = 0;
    for (const d of dirs) { ux += d[0]; uz += d[1]; }
    const len = Math.hypot(ux, uz);
    if (len < 1e-9) {
      ux = cur[0] - centroid[0];
      uz = cur[2] - centroid[1];
      const l2 = Math.hypot(ux, uz) || 1;
      ux /= l2; uz /= l2;
    } else { ux /= len; uz /= len; }
    // 统一朝外：背离檐口环质心
    if (ux * (cur[0] - centroid[0]) + uz * (cur[2] - centroid[1]) < 0) { ux = -ux; uz = -uz; }
    outward.push([ux, uz]);
  }

  const section = (i: number): Pt3[] => profile.map(([u, v]) => (
    [pts[i][0] + outward[i][0] * u, pts[i][1] + v, pts[i][2] + outward[i][1] * u] as Pt3
  ));

  const segments = closed ? count : count - 1;
  for (let i = 0; i < segments; i++) {
    const a = section(i);
    const b = section((i + 1) % count);
    for (let k = 0; k < m; k++) {
      const k2 = (k + 1) % m;
      pushSolidQuad(out, a[k], a[k2], b[k2], b[k]);
    }
  }

  if (!closed) {
    // 两端端封（端面是截面多边形，凸六边形用扇形剖分即可）
    const first = section(0), last = section(count - 1);
    for (let k = 1; k + 1 < m; k++) {
      pushSolidTriangle(out, first[0], first[k + 1], first[k]);
      pushSolidTriangle(out, last[0], last[k], last[k + 1]);
    }
  }

  return orientSolidOutward(out);
}

/** 生成檐口线脚实体的三角面列表（外法线朝外）。 */
function buildEaveTrim(
  geometry: Float32Array,
  indices: Uint32Array,
  spec: EaveTrimSpec,
): number[] {
  const out: number[] = [];
  for (const loop of extractEaveLoops(geometry, indices)) {
    let cx = 0, cz = 0;
    for (const p of loop) { cx += p[0]; cz += p[2]; }
    const centroid: [number, number] = [cx / loop.length, cz / loop.length];
    for (const run of splitEaveRuns(loop)) {
      out.push(...sweepEaveRun(run.pts, run.closed, spec, centroid));
    }
  }
  return out;
}

function polygonSignedArea(poly: Array<[number, number]>): number {
  let sum = 0;
  for (let i = 0; i < poly.length; i++) {
    const a = poly[i], b = poly[(i + 1) % poly.length];
    sum += a[0] * b[1] - b[0] * a[1];
  }
  return sum / 2;
}

const EAR_EPS = 1e-9;

function pointInTriangle(
  p: [number, number],
  a: [number, number],
  b: [number, number],
  c: [number, number],
): boolean {
  const d1 = (p[0] - b[0]) * (a[1] - b[1]) - (a[0] - b[0]) * (p[1] - b[1]);
  const d2 = (p[0] - c[0]) * (b[1] - c[1]) - (b[0] - c[0]) * (p[1] - c[1]);
  const d3 = (p[0] - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (p[1] - a[1]);
  const negative = d1 < -EAR_EPS || d2 < -EAR_EPS || d3 < -EAR_EPS;
  const positive = d1 > EAR_EPS || d2 > EAR_EPS || d3 > EAR_EPS;
  return !(negative && positive);
}

/**
 * 耳切三角化（输入必须是 CCW 简单多边形，允许凹点）。
 *
 * 博风板的 Λ 形带有一个凹点（内侧脊点），扇形剖分会出界，必须用耳切。
 * 返回的是对输入点下标的三元组，绕序与输入一致（CCW）。
 */
function earClipTriangles(poly: Array<[number, number]>): Array<[number, number, number]> {
  const triangles: Array<[number, number, number]> = [];
  const indices = poly.map((_, index) => index);
  const cross = (a: [number, number], b: [number, number], c: [number, number]): number => (
    (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
  );
  let guard = 0;
  while (indices.length > 3 && guard++ < 4096) {
    let clipped = false;
    for (let i = 0; i < indices.length; i++) {
      const prev = indices[(i + indices.length - 1) % indices.length];
      const current = indices[i];
      const next = indices[(i + 1) % indices.length];
      const a = poly[prev], b = poly[current], c = poly[next];
      if (cross(a, b, c) <= EAR_EPS) continue;      // 凹点或退化，不是耳朵
      const hasInside = indices.some((index) => (
        index !== prev && index !== current && index !== next
        && pointInTriangle(poly[index], a, b, c)
      ));
      if (hasInside) continue;
      triangles.push([prev, current, next]);
      indices.splice(i, 1);
      clipped = true;
      break;
    }
    if (!clipped) break;                             // 自交/退化输入：放弃剩余部分
  }
  if (indices.length === 3) {
    triangles.push([indices[0], indices[1], indices[2]]);
  }
  return triangles;
}

/**
 * 把 XY 平面的简单多边形沿 Z 拉伸成闭合棱柱（外法线朝外）。
 *
 * 侧面按 CCW 邻边生成；端盖用耳切结果，+Z 面保持 CCW、-Z 面反向。
 */
function pushPrismZ(
  out: number[],
  profile: Array<[number, number]>,
  z0: number,
  z1: number,
): void {
  if (z1 - z0 <= 1e-6 || profile.length < 3) return;
  const poly = polygonSignedArea(profile) < 0 ? [...profile].reverse() : profile;
  const n = poly.length;
  for (let i = 0; i < n; i++) {
    const a = poly[i], b = poly[(i + 1) % n];
    pushSolidQuad(out, [a[0], a[1], z0], [b[0], b[1], z0], [b[0], b[1], z1], [a[0], a[1], z1]);
  }
  for (const [i, j, k] of earClipTriangles(poly)) {
    pushSolidTriangle(out, [poly[i][0], poly[i][1], z1], [poly[j][0], poly[j][1], z1], [poly[k][0], poly[k][1], z1]);
    pushSolidTriangle(out, [poly[k][0], poly[k][1], z0], [poly[j][0], poly[j][1], z0], [poly[i][0], poly[i][1], z0]);
  }
}

/**
 * 双坡屋顶的山墙端饰面板（**唯一保留的类型专有装饰**）。
 *
 * 博风板不必再手写：通用扫掠算子沿屋面斜边扫掠时，那里正好是"转角"，
 * 会被切成独立构件并端封，形态就是博风板。所以这里只剩一件事——把山墙端面
 * 刷成墙体色。屋面端面由屋顶实体自身封闭（不能拆走，否则屋顶漏水），
 * 面板只是向外偏移 `panelGap` 的贴面。
 *
 * 是否生成由 `ROOF_CAPABILITIES.gableEndPanels` 声明，不再散落类型判断。
 */
function appendGableEndPanels(
  out: number[],
  hw: number,
  hd: number,
  height: number,
  thickness: number,
  spec: EaveTrimSpec,
): void {
  const panel: Array<[number, number]> = [
    [-hw, -thickness], [hw, -thickness], [hw, 0], [0, height], [-hw, 0],
  ];
  pushPrismZ(out, panel, hd + spec.panelGap, hd + spec.panelGap + spec.panelThickness);
  pushPrismZ(out, panel, -hd - spec.panelGap - spec.panelThickness, -hd - spec.panelGap);
}

