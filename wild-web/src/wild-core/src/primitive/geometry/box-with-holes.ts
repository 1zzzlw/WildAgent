/**
 * 在长方体上切出矩形通孔 — 生成带孔的顶点数据
 *
 * 墙体是一个长方体（中心在原点，L 沿 X，H 沿 Y，T 沿 Z）。
 * 洞口是一个矩形通孔，从 Z=-T/2 穿透到 Z=T/2。
 * 本函数使用 2D 矩形分区算法，精确处理多洞口场景：
 *   - 按所有洞口的 X/Y 边界将前/后面划分为网格
 *   - 只输出非洞口区域的网格
 *   - 每个洞口独立生成内壁（Z 方向贯穿）
 */

import { indexTriList } from './mesh-helper';

interface Cutout {
  localX: number;   // 沿墙位置（0 = 墙起点）
  localY: number;   // 底部高度（0 = 地面）
  localW: number;   // 宽度
  localH: number;   // 高度
}

export function boxWithHoles(length: number, height: number, thickness: number, cutouts: Cutout[]): { geometry: Float32Array; indices: Uint16Array } {
  const verts: number[] = [];
  const hl = length / 2;
  const hh = height / 2;
  const ht = thickness / 2;

  // 调试：检查异常情况
  if (length > 20 || cutouts.length > 0) {
    console.log(`📦 boxWithHoles: L=${length.toFixed(2)}, H=${height.toFixed(2)}, T=${thickness.toFixed(2)}`);
    console.log(`  hl=${hl.toFixed(2)}, hh=${hh.toFixed(2)}, ht=${ht.toFixed(2)}`);
    console.log(`  cutouts: ${cutouts.length}`);
    cutouts.forEach((c, i) => {
      console.log(`    [${i}] localX=${c.localX.toFixed(2)}, localY=${c.localY.toFixed(2)}, W=${c.localW.toFixed(2)}, H=${c.localH.toFixed(2)}`);
    });
  }

  // 将 cutout 从墙局部坐标转换到盒体中心坐标
  const holes = cutouts.map(c => ({
    x1: c.localX - c.localW / 2 - hl,
    x2: c.localX + c.localW / 2 - hl,
    y1: c.localY - hh,
    y2: c.localY + c.localH - hh,
  }));
  
  // 调试：检查转换后的洞口坐标
  if (length > 20 || cutouts.length > 0) {
    console.log(`  转换后的holes:`);
    holes.forEach((h, i) => {
      console.log(`    [${i}] x1=${h.x1.toFixed(2)}, x2=${h.x2.toFixed(2)}, y1=${h.y1.toFixed(2)}, y2=${h.y2.toFixed(2)}`);
    });
  }

  // 辅助：推一个三角形
  function tri(x1: number, y1: number, z1: number,
               x2: number, y2: number, z2: number,
               x3: number, y3: number, z3: number) {
    verts.push(x1, y1, z1, x2, y2, z2, x3, y3, z3);
  }

  // 辅助: 四边形拆2个三角形
  function quad(x1: number, y1: number, z1: number,
               x2: number, y2: number, z2: number,
               x3: number, y3: number, z3: number,
               x4: number, y4: number, z4: number) {
    tri(x1, y1, z1, x2, y2, z2, x3, y3, z3);
    tri(x1, y1, z1, x3, y3, z3, x4, y4, z4);
  }

  /** 给定一组 XY 矩形区域，检查 (x,y) 范围是否与任意洞口重叠 */
  function isCovered(x1: number, x2: number, y1: number, y2: number): boolean {
    // 用 AABB 重叠判断而非中心点判断，防止分区格子边缘的几何体漏入洞口区域
    return holes.some(h =>
      h.x1 < x2 && h.x2 > x1 && h.y1 < y2 && h.y2 > y1
    );
  }

  /** 收集所有唯一的 X 或 Y 边界，排序 */
  function collectBoundaries(extent: number, getBound: (h: typeof holes[0]) => [number, number]): number[] {
    const set = new Set<number>();
    set.add(-extent);
    set.add(extent);
    for (const h of holes) {
      const [a, b] = getBound(h);
      set.add(a);
      set.add(b);
    }
    return [...set].sort((a, b) => a - b);
  }

  if (holes.length === 0) {
    // 无洞口：完整盒体，6 个面
    quad(-hl, -hh, ht, hl, -hh, ht, hl, hh, ht, -hl, hh, ht);
    quad(hl, -hh, -ht, -hl, -hh, -ht, -hl, hh, -ht, hl, hh, -ht);
    quad(-hl, hh, ht, hl, hh, ht, hl, hh, -ht, -hl, hh, -ht);
    quad(-hl, -hh, -ht, hl, -hh, -ht, hl, -hh, ht, -hl, -hh, ht);
    quad(hl, -hh, ht, hl, -hh, -ht, hl, hh, -ht, hl, hh, ht);
    quad(-hl, -hh, -ht, -hl, -hh, ht, -hl, hh, ht, -hl, hh, -ht);
    return indexTriList(new Float32Array(verts));
  }

  // ────────────────────────────────────────
  // 二、有洞口时：2D 分区生成前后面 + 独立内壁
  // ────────────────────────────────────────

  // 对所有洞口生成内壁（Z 方向连接前后面）
  for (const h of holes) {
    // 左内壁
    quad(h.x1, h.y1, ht, h.x1, h.y2, ht, h.x1, h.y2, -ht, h.x1, h.y1, -ht);
    // 右内壁
    quad(h.x2, h.y2, ht, h.x2, h.y1, ht, h.x2, h.y1, -ht, h.x2, h.y2, -ht);
    // 上内壁
    quad(h.x1, h.y2, ht, h.x2, h.y2, ht, h.x2, h.y2, -ht, h.x1, h.y2, -ht);
    // 下内壁
    quad(h.x2, h.y1, ht, h.x1, h.y1, ht, h.x1, h.y1, -ht, h.x2, h.y1, -ht);
  }

  // 对前后面做 2D 矩形分区
  const xBounds = collectBoundaries(hl, h => [h.x1, h.x2]);
  const yBounds = collectBoundaries(hh, h => [h.y1, h.y2]);

  for (let xi = 0; xi < xBounds.length - 1; xi++) {
    for (let yi = 0; yi < yBounds.length - 1; yi++) {
      const cx1 = xBounds[xi], cx2 = xBounds[xi + 1];
      const cy1 = yBounds[yi], cy2 = yBounds[yi + 1];
      if (isCovered(cx1, cx2, cy1, cy2)) continue;

      // 前面（z=+ht），逆时针绕向使法线朝 +Z
      quad(cx1, cy1, ht, cx2, cy1, ht, cx2, cy2, ht, cx1, cy2, ht);
      // 后面（z=-ht），顺时针绕向使法线朝 -Z
      quad(cx2, cy1, -ht, cx1, cy1, -ht, cx1, cy2, -ht, cx2, cy2, -ht);
    }
  }

  // 顶面（y=hh）：沿 X 方向分区避开洞口
  const topYBounds = collectBoundaries(hl, h => [h.x1, h.x2]);
  for (let xi = 0; xi < topYBounds.length - 1; xi++) {
    const cx1 = topYBounds[xi], cx2 = topYBounds[xi + 1];
    // 检查这个 X 段顶部是否有洞口贯通到墙顶
    if (holes.some(h => h.x1 < cx2 && h.x2 > cx1 && h.y2 >= hh)) continue;
    quad(cx1, hh, ht, cx2, hh, ht, cx2, hh, -ht, cx1, hh, -ht);
  }

  // 底面（y=-hh）：沿 X 方向分区
  const botYBounds = collectBoundaries(hl, h => [h.x1, h.x2]);
  for (let xi = 0; xi < botYBounds.length - 1; xi++) {
    const cx1 = botYBounds[xi], cx2 = botYBounds[xi + 1];
    if (holes.some(h => h.x1 < cx2 && h.x2 > cx1 && h.y1 <= -hh)) continue;
    quad(cx2, -hh, ht, cx1, -hh, ht, cx1, -hh, -ht, cx2, -hh, -ht);
  }

  // 左面（x=-hl）：沿 Y 方向分区避开洞口
  const leftYBounds = collectBoundaries(hh, h => [h.y1, h.y2]);
  for (let yi = 0; yi < leftYBounds.length - 1; yi++) {
    const cy1 = leftYBounds[yi], cy2 = leftYBounds[yi + 1];
    if (holes.some(h => h.x1 <= -hl && h.y1 < cy2 && h.y2 > cy1)) continue;
    quad(-hl, cy1, -ht, -hl, cy1, ht, -hl, cy2, ht, -hl, cy2, -ht);
  }

  // 右面（x=hl）：沿 Y 方向分区避开洞口
  const rightYBounds = collectBoundaries(hh, h => [h.y1, h.y2]);
  for (let yi = 0; yi < rightYBounds.length - 1; yi++) {
    const cy1 = rightYBounds[yi], cy2 = rightYBounds[yi + 1];
    if (holes.some(h => h.x2 >= hl && h.y1 < cy2 && h.y2 > cy1)) continue;
    quad(hl, cy1, ht, hl, cy1, -ht, hl, cy2, -ht, hl, cy2, ht);
  }

  return indexTriList(new Float32Array(verts));
}
