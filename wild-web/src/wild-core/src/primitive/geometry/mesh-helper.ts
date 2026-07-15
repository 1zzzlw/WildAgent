/**
 * 几何体索引辅助 — 统一将各类顶点格式转为带索引的三角面列表
 */

/** 为三角面列表顶点数据添加顺序索引（每 3 个顶点 = 1 个三角形） */
export function indexTriList(vertices: Float32Array): { geometry: Float32Array; indices: Uint16Array } {
  const n = vertices.length / 3;
  const triCount = Math.floor(n / 3) * 3;
  const indices = new Uint16Array(triCount);
  for (let i = 0; i < triCount; i++) indices[i] = i;
  return { geometry: vertices, indices };
}

/** 将三角条带转为带索引的三角面列表 */
export function stripToTriList(vertices: Float32Array): { geometry: Float32Array; indices: Uint16Array } {
  const n = vertices.length / 3;
  const idx: number[] = [];
  for (let i = 0; i < n - 2; i++) {
    if (i % 2 === 0) idx.push(i, i + 1, i + 2);
    else idx.push(i + 1, i, i + 2);
  }
  return { geometry: vertices, indices: new Uint16Array(idx) };
}

/**
 * 圆柱/锥体顶点数据（条带侧表面 + 两个环面）补圆心后转为完整索引三角面
 *
 * 输入布局（总顶点数 = (seg+1) * 4）：
 *   [0, (seg+1)*2)          = 侧表面，三角条带，bottom/top 交替
 *   [(seg+1)*2, (seg+1)*3)  = 顶面外圈顶点（需补圆心）
 *   [(seg+1)*3, (seg+1)*4)  = 底面外圈顶点（需补圆心）
 */
export function finalizeCylinder(vertices: Float32Array, seg: number): { geometry: Float32Array; indices: Uint16Array } {
  const arr = Array.from(vertices);
  const stripEnd = (seg + 1) * 2;
  const topStart = stripEnd;
  const botStart = (seg + 1) * 3;

  // 取顶面/底面外圈第一个顶点计算圆心（同 Y，XZ 为 0）
  const topY = arr[topStart * 3 + 1];
  const botY = arr[botStart * 3 + 1];

  // 在末尾追加圆心顶点
  const ciTop = arr.length / 3;
  arr.push(0, topY, 0);
  const ciBot = arr.length / 3;
  arr.push(0, botY, 0);

  const idx: number[] = [];

  // 侧表面：三角条带 → 索引三角形
  for (let i = 0; i < stripEnd - 2; i++) {
    if (i % 2 === 0) idx.push(i, i + 1, i + 2);
    else idx.push(i + 1, i, i + 2);
  }

  // 顶面：扇形，法线朝 +Y
  for (let i = 0; i < seg; i++) {
    idx.push(ciTop, topStart + i + 1, topStart + i);
  }

  // 底面：扇形，法线朝 -Y
  for (let i = 0; i < seg; i++) {
    idx.push(ciBot, botStart + i, botStart + i + 1);
  }

  return { geometry: new Float32Array(arr), indices: new Uint16Array(idx) };
}
