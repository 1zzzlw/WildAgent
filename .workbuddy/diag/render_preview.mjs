/**
 * 离线软件光栅化预览：把 .wild 蓝图用**真实重建链路**跑一遍，出 PNG。
 *
 * 为什么需要它：本机跑不了真实浏览器/WebGL（Chrome headless exit 21），
 * 而"引擎到底把这份蓝图渲染成什么样"必须能看见。这个脚本不实现任何几何或
 * 材质——它只消费 reconstructWildEntity 的产出（mesh.geometry / mesh.indices /
 * mesh.transform / entity.materialParams），用一台极简软件光栅化器画出来。
 * 所以图上看到的东西，就是引擎的真实产出，不是第二套实现。
 *
 * 用法（工作目录必须是 wild-web，否则解析不到 node_modules）：
 *   cd wild-web
 *   node ../.workbuddy/diag/render_preview.mjs <蓝图> [--out=目录] [--w=1280] [--h=860] [--views=persp,aerial,front]
 * 退出码 0 = 出图成功。
 */
import { writeFile, mkdir } from 'node:fs/promises'
import { deflateSync } from 'node:zlib'
import { resolve, dirname } from 'node:path'

const ROOT = 'E:/AgentProject/WildAgent/wild-web'
const CORE_ROOT = 'E:/AgentProject/WildAgent/wild-core'
const { readFile } = await import('node:fs/promises')
const { createServer } = await import(
  'file:///E:/AgentProject/WildAgent/wild-web/node_modules/vite/dist/node/index.js'
)

// ── 参数 ─────────────────────────────────────────────────────
const argv = process.argv.slice(2)
const target = argv.find((a) => !a.startsWith('--'))
if (!target) {
  console.error('用法: render_preview.mjs <蓝图> [--out=目录] [--w=] [--h=] [--views=]')
  process.exit(2)
}
const opt = (name, dflt) => {
  const hit = argv.find((a) => a.startsWith(`--${name}=`))
  return hit ? hit.slice(name.length + 3) : dflt
}
const OUT_DIR = resolve(opt('out', 'lantu/docs/renders'))
const W = Number(opt('w', 1280))
const H = Number(opt('h', 860))
const VIEWS = opt('views', 'persp,aerial,front').split(',').map((s) => s.trim())

// ── 极简 PNG 编码（zlib + CRC32，不引第三方） ────────────────
const CRC_TABLE = (() => {
  const t = new Int32Array(256)
  for (let n = 0; n < 256; n += 1) {
    let c = n
    for (let k = 0; k < 8; k += 1) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1
    t[n] = c
  }
  return t
})()
function crc32(buf) {
  let c = -1
  for (let i = 0; i < buf.length; i += 1) c = CRC_TABLE[(c ^ buf[i]) & 0xff] ^ (c >>> 8)
  return (c ^ -1) >>> 0
}
function chunk(type, data) {
  const len = Buffer.alloc(4)
  len.writeUInt32BE(data.length, 0)
  const body = Buffer.concat([Buffer.from(type, 'ascii'), data])
  const crc = Buffer.alloc(4)
  crc.writeUInt32BE(crc32(body), 0)
  return Buffer.concat([len, body, crc])
}
function encodePNG(w, h, rgb) {
  const stride = w * 3
  const raw = Buffer.alloc(h * (stride + 1))
  for (let y = 0; y < h; y += 1) {
    raw[y * (stride + 1)] = 0 // filter type 0
    Buffer.from(rgb.buffer, rgb.byteOffset + y * stride, stride).copy(raw, y * (stride + 1) + 1)
  }
  const ihdr = Buffer.alloc(13)
  ihdr.writeUInt32BE(w, 0)
  ihdr.writeUInt32BE(h, 4)
  ihdr[8] = 8 // bit depth
  ihdr[9] = 2 // color type: truecolor
  return Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    chunk('IHDR', ihdr),
    chunk('IDAT', deflateSync(raw, { level: 6 })),
    chunk('IEND', Buffer.alloc(0)),
  ])
}

// ── 向量小工具 ───────────────────────────────────────────────
const sub = (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]]
const cross = (a, b) => [
  a[1] * b[2] - a[2] * b[1],
  a[2] * b[0] - a[0] * b[2],
  a[0] * b[1] - a[1] * b[0],
]
const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
const norm = (a) => {
  const l = Math.hypot(a[0], a[1], a[2]) || 1
  return [a[0] / l, a[1] / l, a[2] / l]
}
const mul = (a, s) => [a[0] * s, a[1] * s, a[2] * s]
const add = (a, b) => [a[0] + b[0], a[1] + b[1], a[2] + b[2]]

/**
 * 元素空间 → 世界空间。**必须应用 rotation**：本项目离线预览曾只加 position
 * 而忽略 rotation，导致左右后墙与全部门窗落在错误位置，基于那些图得出的结论全是错的。
 */
function makeTransformer(position, rotation, scale) {
  const [cx, cy, cz] = rotation
  const [sx, sy, sz] = scale
  const cosx = Math.cos(cx), sinx = Math.sin(cx)
  const cosy = Math.cos(cy), siny = Math.sin(cy)
  const cosz = Math.cos(cz), sinz = Math.sin(cz)
  const m = [
    cosy * cosz, -cosy * sinz, siny,
    cosx * sinz + sinx * siny * cosz, cosx * cosz - sinx * siny * sinz, -sinx * cosy,
    sinx * sinz - cosx * siny * cosz, sinx * cosz + cosx * siny * sinz, cosx * cosy,
  ]
  return (vx, vy, vz) => {
    const x = vx * sx, y = vy * sy, z = vz * sz
    return [
      m[0] * x + m[1] * y + m[2] * z + position[0],
      m[3] * x + m[4] * y + m[5] * z + position[1],
      m[6] * x + m[7] * y + m[8] * z + position[2],
    ]
  }
}

// ── 软件光栅化 ───────────────────────────────────────────────
const SKY_TOP = [0.42, 0.62, 0.88]
const SKY_BOTTOM = [0.86, 0.90, 0.95]
// 主光方向按**照片的光照**取，不照抄查看器的灯：
// 照片里正立面接近过曝、右侧面偏暗 → 光从左前上方来（−X、−Z，即拍摄者那一侧）。
// 早期用了查看器的 [+1, +1.5, +0.75]，导致正立面彻底背光、白墙渲染成中灰。
const SUN_DIR = norm([-0.55, 1.5, -1.05])
const AMBIENT = 0.4
const SUN_INTENSITY = 1.05
const GAMMA = 1 / 2.2

function renderTriangleView(tris, groundY, eye, targetPt, fovDeg, W, H) {
  const fov = (fovDeg * Math.PI) / 180
  const f = 1 / Math.tan(fov / 2)
  const forward = norm(sub(targetPt, eye))
  const right = norm(cross(forward, [0, 1, 0]))
  const up = cross(right, forward)

  const color = new Float32Array(W * H * 3)
  const depth = new Float32Array(W * H).fill(Infinity)
  const DBG = process.env.PREVIEW_DEBUG === '1'
  const rasterStat = { dbg: 0, nullProj: 0, degenerate: 0, rasterized: 0 }

  // 背景：天空渐变（线性空间下算，最后统一 gamma）
  for (let y = 0; y < H; y += 1) {
    const t = y / (H - 1)
    const c = [
      SKY_TOP[0] * (1 - t) + SKY_BOTTOM[0] * t,
      SKY_TOP[1] * (1 - t) + SKY_BOTTOM[1] * t,
      SKY_TOP[2] * (1 - t) + SKY_BOTTOM[2] * t,
    ]
    for (let x = 0; x < W; x += 1) {
      const i = (y * W + x) * 3
      color[i] = c[0]
      color[i + 1] = c[1]
      color[i + 2] = c[2]
    }
  }

  const project = (p) => {
    const rel = sub(p, eye)
    const camX = dot(rel, right)
    const camY = dot(rel, up)
    const camZ = dot(rel, forward) // 前方为正；写反过一版，整栋建筑被判成在相机背后
    if (camZ <= 0.05) return null
    return [
      (camX * f) / camZ,
      (camY * f) / camZ,
      camZ,
    ]
  }

  const shade = (base, n, isGlass) => {
    const nn = norm(n)
    // 双面：法线永远朝向相机
    const facing = nn[2] !== 0 || true
    const ndl = Math.max(0, dot(nn, SUN_DIR))
    // 半球环境：法线朝上偏天光，朝下偏地面反照
    const hemi = 0.5 + 0.5 * nn[1]
    const amb = AMBIENT * (0.55 + 0.45 * hemi)
    let light = amb + ndl * SUN_INTENSITY
    if (isGlass) light = amb + ndl * SUN_INTENSITY * 0.35 + 0.18
    return [base[0] * light, base[1] * light, base[2] * light]
  }

  // 不透明一遍（写深度），玻璃一遍（读深度做混合）——避免透明体量互相遮挡时穿帮
  const opaque = tris.filter((t) => !t.glass)
  const glassTris = tris.filter((t) => t.glass)

  const rasterize = (list, isGlassPass) => {
    for (const tri of list) {
      const pts = tri.v.map(project)
      if (DBG && rasterStat.dbg++ < 3) {
        console.log(
          `[dbg] world v0=${tri.v[0].map((v) => v.toFixed(2)).join(',')}` +
            ` pts=${pts.map((p) => (p ? p.map((v) => v.toFixed(1)).join('/') : 'null')).join(' | ')}`,
        )
      }
      if (pts.some((p) => p === null)) {
        rasterStat.nullProj += 1
        continue
      }
      const [a, b, c] = pts

      // 面法线（世界空间） —— flat shading，体量转折一眼可辨
      const wn = cross(sub(tri.v[1], tri.v[0]), sub(tri.v[2], tri.v[0]))
      let n = norm(wn)
      // 双面光照：让法线朝向相机
      const toEye = norm(sub(eye, tri.v[0]))
      if (dot(n, toEye) < 0) n = mul(n, -1)

      const ax = (a[0] * 0.5 + 0.5) * W
      const ay = (1 - (a[1] * 0.5 + 0.5)) * H
      const bx = (b[0] * 0.5 + 0.5) * W
      const by = (1 - (b[1] * 0.5 + 0.5)) * H
      const cx2 = (c[0] * 0.5 + 0.5) * W
      const cy2 = (1 - (c[1] * 0.5 + 0.5)) * H

      // ⚠️ area 必须用**屏幕坐标**算。NDC → 屏幕在 y 轴做了翻转，若用 NDC 算 area
      //    却用屏幕坐标算重心坐标，两者符号相反 → 每个像素都被判成在三角形外，
      //    整幅图 0 覆盖（这个 bug 吃过一次，画面只剩天空）。
      const area = (bx - ax) * (cy2 - ay) - (cx2 - ax) * (by - ay)
      if (Math.abs(area) < 1e-9) {
        rasterStat.degenerate += 1
        continue
      }
      rasterStat.rasterized += 1
      const minX = Math.max(0, Math.floor(Math.min(ax, bx, cx2)))
      const maxX = Math.min(W - 1, Math.ceil(Math.max(ax, bx, cx2)))
      const minY = Math.max(0, Math.floor(Math.min(ay, by, cy2)))
      const maxY = Math.min(H - 1, Math.ceil(Math.max(ay, by, cy2)))
      if (minX > maxX || minY > maxY) continue

      const col = shade(tri.color, n, tri.glass)

      for (let py = minY; py <= maxY; py += 1) {
        for (let px = minX; px <= maxX; px += 1) {
          const x0 = px + 0.5, y0 = py + 0.5
          rasterStat.pxTested = (rasterStat.pxTested || 0) + 1
          // 重心坐标
          const w0 = ((bx - x0) * (cy2 - y0) - (cx2 - x0) * (by - y0)) / area
          const w1 = ((cx2 - x0) * (ay - y0) - (ax - x0) * (cy2 - y0)) / area
          const w2 = 1 - w0 - w1
          if (w0 < 0 || w1 < 0 || w2 < 0) continue
          rasterStat.pxInside = (rasterStat.pxInside || 0) + 1
          // 透视校正深度
          const inv = w0 / a[2] + w1 / b[2] + w2 / c[2]
          if (inv <= 0) continue
          const z = 1 / inv
          const di = py * W + px
          if (z >= depth[di]) continue
          if (isGlassPass) {
            const alpha = 0.30
            const ci = di * 3
            color[ci] = color[ci] * (1 - alpha) + col[0] * alpha
            color[ci + 1] = color[ci + 1] * (1 - alpha) + col[1] * alpha
            color[ci + 2] = color[ci + 2] * (1 - alpha) + col[2] * alpha
          } else {
            depth[di] = z
            const ci = di * 3
            color[ci] = col[0]
            color[ci + 1] = col[1]
            color[ci + 2] = col[2]
          }
        }
      }
    }
  }

  rasterize(opaque, false)
  rasterize(glassTris, true)
  if (DBG) {
    let covered = 0
    for (let i = 0; i < depth.length; i += 1) if (depth[i] !== Infinity) covered += 1
    console.log(
      `[dbg] eye=${eye.map((v) => v.toFixed(2)).join(',')} target=${targetPt
        .map((v) => v.toFixed(2))
        .join(',')} fov=${fovDeg} 统计=${JSON.stringify(rasterStat)}`,
    )
    console.log(`[dbg] 被几何覆盖的像素 ${covered} / ${depth.length}（${((covered / depth.length) * 100).toFixed(1)}%）`)
  }

  // gamma 编码 + clamp
  const out = new Uint8Array(W * H * 3)
  for (let i = 0; i < out.length; i += 1) {
    const v = Math.pow(Math.max(0, color[i]), GAMMA)
    out[i] = Math.max(0, Math.min(255, Math.round(v * 255)))
  }
  return out
}

// ── 主流程 ───────────────────────────────────────────────────
const server = await createServer({
  root: ROOT,
  appType: 'custom',
  logLevel: 'silent',
  server: { middlewareMode: true },
  resolve: {
    alias: {
      'wild-core/compiler': `${CORE_ROOT}/src/compiler/index.ts`,
      'wild-core/materials': `${CORE_ROOT}/src/materials/index.ts`,
      'wild-core/world': `${CORE_ROOT}/src/world/index.ts`,
      'wild-core/primitive': `${CORE_ROOT}/src/primitive/index.ts`,
      'wild-core/types': `${CORE_ROOT}/types.ts`,
      'wild-core': `${CORE_ROOT}/src/index.ts`,
    },
  },
})

try {
  const { parseWildBlueprint, reconstructWildEntity } = await server.ssrLoadModule(
    '/src/renderer/wildCoreAdapter.ts',
  )
  const text = await readFile(target, 'utf8')
  const bp = parseWildBlueprint(text)
  const entity = await reconstructWildEntity(bp)

  // 收集三角形
  const tris = []
  for (let i = 0; i < entity.meshes.length; i += 1) {
    const mesh = entity.meshes[i]
    const mat = entity.materialParams[i] || {}
    const base = mat.baseColor || [0.8, 0.8, 0.8]
    const isGlass = (mat.transmission || 0) > 0.5 || (mat.opacity ?? 1) < 0.99
    const g = mesh.geometry
    if (!g || g.length < 9) continue
    const t = mesh.transform || {}
    const transform = makeTransformer(t.position || [0, 0, 0], t.rotation || [0, 0, 0], t.scale || [1, 1, 1])
    const nv = Math.floor(g.length / 3)
    const world = new Array(nv)
    for (let v = 0; v < nv; v += 1) {
      world[v] = transform(g[v * 3], g[v * 3 + 1], g[v * 3 + 2])
    }
    const idx = mesh.indices
    if (i < 4) {
      console.log(
        `[dbg] mesh[${i}] ${mesh.elementId}: verts=${nv} ` +
          `indices=${idx ? `${idx.constructor?.name} len=${idx.length}` : String(idx)}`,
      )
    }
    if (idx && idx.length) {
      for (let k = 0; k + 2 < idx.length; k += 3) {
        const a = idx[k], b = idx[k + 1], c = idx[k + 2]
        if (a >= nv || b >= nv || c >= nv) continue
        tris.push({ v: [world[a], world[b], world[c]], color: base, glass: isGlass })
      }
    } else {
      for (let k = 0; k + 2 < nv; k += 3) {
        tris.push({ v: [world[k], world[k + 1], world[k + 2]], color: base, glass: isGlass })
      }
    }
  }

  const bb = entity.boundingBox
  const center = [
    (bb.min[0] + bb.max[0]) / 2,
    (bb.min[1] + bb.max[1]) / 2,
    (bb.min[2] + bb.max[2]) / 2,
  ]
  const size = [bb.max[0] - bb.min[0], bb.max[1] - bb.min[1], bb.max[2] - bb.min[2]]
  const radius = Math.hypot(size[0], size[1], size[2]) * 0.5 || 10

  console.log(`蓝图：${target}`)
  console.log(`网格 ${entity.meshes.length} → 三角形 ${tris.length}（其中玻璃 ${tris.filter((t) => t.glass).length}）`)
  console.log(`包围盒 ${size.map((v) => v.toFixed(2)).join(' × ')} m，取景中心 (${center.map((v) => v.toFixed(2)).join(', ')})`)

  const VIEW_DEFS = {
    // 与照片同机位：观察者在泳池侧（−Z）、建筑左侧（−X），略仰
    persp: { dir: [-0.52, 0.40, -1.0], fov: 42, distFactor: 1.30, name: 'view_perspective' },
    // 鸟瞰：看体量错落关系
    aerial: { dir: [0.85, 0.95, -1.25], fov: 40, distFactor: 1.32, name: 'view_aerial' },
    // 正立面：看幕墙分格与阳台
    front: { dir: [0.0, 0.22, -1.0], fov: 38, distFactor: 1.24, name: 'view_front' },
  }

  await mkdir(OUT_DIR, { recursive: true })
  const basename = target.split(/[\\/]/).pop().replace(/\.wild$/, '')

  for (const key of VIEWS) {
    const def = VIEW_DEFS[key]
    if (!def) continue
    const dir = norm(def.dir)
    const dist = (radius / Math.sin((def.fov * Math.PI) / 360)) * def.distFactor
    const eye = add(center, mul(dir, dist))
    const px = renderTriangleView(tris, bb.min[1], eye, center, def.fov, W, H)
    const png = encodePNG(W, H, px)
    const outPath = resolve(OUT_DIR, `${basename}.${def.name}.png`)
    await writeFile(outPath, png)
    console.log(`  ✅ ${outPath}  (${(png.length / 1024).toFixed(0)} KB)`)
  }
  console.log('— 结果：PASS')
} catch (err) {
  console.error('❌ 出图失败：', err?.stack ?? err)
  process.exitCode = 1
} finally {
  await server.close()
}
