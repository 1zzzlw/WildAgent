/**
 * 零依赖 PNG 解码 + 图像量化统计。
 *
 * ── 为什么自己写解码器 ──────────────────────────────────────────
 * 本机没有装 `sharp` / `pngjs`，而"曝光标定"这类活儿**必须**靠数字收口：
 * 肉眼看"是不是亮了"在饱和区完全失效（37% 像素已经打到 240+ 时，
 * 再亮 10% 与再亮 30% 看起来一样白）。所以宁可按 PNG 规范解一遍。
 *
 * 只支持 Chromium `Page.captureScreenshot` 实际会产出的形态：
 * 8bit、非交错、colorType 2(RGB) / 6(RGBA) / 0(灰度) / 4(灰度+A)。
 *
 * ── 三个指标各自的用途 ──────────────────────────────────────────
 *   meanY        整体曝光。太低=发闷，太高+过曝比高=洗白。
 *   overexposure 亮度 ≥240 的像素占比。**这是"细节有没有被洗掉"的主判据**：
 *                像素一旦进饱和区，其上的所有材质/几何细节都被压成同一个白。
 *   detailEnergy 相邻像素亮度差的平均绝对值（内部像素）。它是"画面里还剩多少
 *                可见细节"的直接度量 —— 过曝会把 detailEnergy 打下去，
 *                材质族加特征会把它顶上来。改前改后看这一个数最诚实。
 */

import { readFileSync, writeFileSync } from 'node:fs'
import { inflateSync, deflateSync } from 'node:zlib'

const PNG_SIGNATURE = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a])

/** Paeth 预测器（PNG 规范 9.4）。 */
function paeth(a, b, c) {
  const p = a + b - c
  const pa = Math.abs(p - a)
  const pb = Math.abs(p - b)
  const pc = Math.abs(p - c)
  if (pa <= pb && pa <= pc) return a
  return pb <= pc ? b : c
}

/**
 * 解出一张 PNG 的 RGBA 像素。
 * @returns {{width:number,height:number,data:Uint8Array}}
 */
export function decodePng(file) {
  const buf = readFileSync(file)
  if (!buf.subarray(0, 8).equals(PNG_SIGNATURE)) {
    throw new Error(`不是 PNG：${file}`)
  }

  let offset = 8
  let width = 0
  let height = 0
  let bitDepth = 0
  let colorType = 0
  let interlace = 0
  let palette = null
  const idat = []

  while (offset + 8 <= buf.length) {
    const length = buf.readUInt32BE(offset)
    const type = buf.toString('ascii', offset + 4, offset + 8)
    const data = buf.subarray(offset + 8, offset + 8 + length)
    offset += 12 + length

    if (type === 'IHDR') {
      width = data.readUInt32BE(0)
      height = data.readUInt32BE(4)
      bitDepth = data[8]
      colorType = data[9]
      interlace = data[12]
    } else if (type === 'PLTE') {
      palette = data
    } else if (type === 'IDAT') {
      idat.push(data)
    } else if (type === 'IEND') {
      break
    }
  }

  if (bitDepth !== 8) throw new Error(`只支持 8bit PNG（实际 ${bitDepth}）：${file}`)
  if (interlace !== 0) throw new Error(`不支持 Adam7 交错 PNG：${file}`)

  // colorType → 每像素通道数（索引色在 PLTE 展开前算 1 通道）
  const channelsOf = { 0: 1, 2: 3, 3: 1, 4: 2, 6: 4 }[colorType]
  if (!channelsOf) throw new Error(`不支持的 colorType=${colorType}：${file}`)

  const raw = inflateSync(Buffer.concat(idat))
  const stride = width * channelsOf
  const out = new Uint8Array(width * height * 4)
  const line = new Uint8Array(stride)
  const prev = new Uint8Array(stride)

  let cursor = 0
  for (let y = 0; y < height; y++) {
    const filter = raw[cursor++]
    for (let i = 0; i < stride; i++) line[i] = raw[cursor + i]
    cursor += stride

    for (let i = 0; i < stride; i++) {
      const a = i >= channelsOf ? line[i - channelsOf] : 0
      const b = prev[i]
      const c = i >= channelsOf ? prev[i - channelsOf] : 0
      let value = line[i]
      if (filter === 1) value += a
      else if (filter === 2) value += b
      else if (filter === 3) value += (a + b) >> 1
      else if (filter === 4) value += paeth(a, b, c)
      line[i] = value & 0xff
    }

    const rowBase = y * width * 4
    for (let x = 0; x < width; x++) {
      const s = x * channelsOf
      const d = rowBase + x * 4
      if (colorType === 6) {
        out[d] = line[s]; out[d + 1] = line[s + 1]; out[d + 2] = line[s + 2]; out[d + 3] = line[s + 3]
      } else if (colorType === 2) {
        out[d] = line[s]; out[d + 1] = line[s + 1]; out[d + 2] = line[s + 2]; out[d + 3] = 255
      } else if (colorType === 0) {
        out[d] = out[d + 1] = out[d + 2] = line[s]; out[d + 3] = 255
      } else if (colorType === 4) {
        out[d] = out[d + 1] = out[d + 2] = line[s]; out[d + 3] = line[s + 1]
      } else {
        const p = line[s] * 3
        const r = palette ? palette[p] : 0
        const g = palette ? palette[p + 1] : 0
        const bl = palette ? palette[p + 2] : 0
        out[d] = r; out[d + 1] = g; out[d + 2] = bl; out[d + 3] = 255
      }
    }

    prev.set(line)
  }

  return { width, height, data: out }
}

function percentile(sorted, ratio) {
  if (sorted.length === 0) return 0
  const index = Math.min(sorted.length - 1, Math.max(0, Math.round((sorted.length - 1) * ratio)))
  return sorted[index]
}

/**
 * Rec.709 亮度 + 曝光/细节统计。
 *
 * @param {string} file PNG 路径
 * @param {object} [options]
 * @param {number} [options.border] 统计 detailEnergy 时忽略的边缘宽度（像素），
 *        避免把画面外框的一圈硬边算成"细节"。
 * @param {Array<{name:string,x:number,y:number,w:number,h:number}>} [options.regions]
 *        区域采样，坐标是**归一化** 0..1。
 */
export function analyzePng(file, options = {}) {
  const { width, height, data } = decodePng(file)
  const border = options.border ?? 2
  const total = width * height
  const luma = new Float32Array(total)

  let sum = 0
  let sumSq = 0
  let over = 0
  let under = 0
  for (let i = 0, p = 0; i < total; i++, p += 4) {
    // alpha 混合到白底：截图带 alpha 时不能把透明像素当成黑
    const a = data[p + 3] / 255
    const r = data[p] * a + 255 * (1 - a)
    const g = data[p + 1] * a + 255 * (1 - a)
    const b = data[p + 2] * a + 255 * (1 - a)
    const y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    luma[i] = y
    sum += y
    sumSq += y * y
    if (y >= 240) over++
    if (y <= 8) under++
  }

  const mean = sum / total
  const std = Math.sqrt(Math.max(0, sumSq / total - mean * mean))
  const sorted = Float32Array.from(luma).sort()

  // 可见细节能量：内部像素的四邻域亮度梯度均值。
  // 过曝会把梯度压向 0（大片同白），材质族加特征会把它抬起来。
  let grad = 0
  let gradCount = 0
  for (let y = border; y < height - border; y++) {
    const row = y * width
    for (let x = border; x < width - border; x++) {
      const c = row + x
      grad += Math.abs(luma[c + 1] - luma[c])
        + Math.abs(luma[c + width] - luma[c])
      gradCount += 2
    }
  }

  const result = {
    file,
    width,
    height,
    meanLuma: round(mean, 2),
    stdLuma: round(std, 2),
    p01: round(percentile(sorted, 0.01), 1),
    p50: round(percentile(sorted, 0.5), 1),
    p99: round(percentile(sorted, 0.99), 1),
    overexposureRatio: round(over / total, 4),
    underexposureRatio: round(under / total, 4),
    detailEnergy: round(gradCount > 0 ? grad / gradCount : 0, 3),
  }

  if (options.regions && options.regions.length > 0) {
    result.regions = {}
    for (const region of options.regions) {
      const x0 = Math.max(0, Math.floor(region.x * width))
      const y0 = Math.max(0, Math.floor(region.y * height))
      const x1 = Math.min(width, Math.ceil((region.x + region.w) * width))
      const y1 = Math.min(height, Math.ceil((region.y + region.h) * height))
      let rs = 0
      let gs = 0
      let bs = 0
      let rn = 0
      let rOver = 0
      let rSum = 0
      let rSumSq = 0
      // 区域内的"可见细节"：只在区域内部算四邻域梯度，避免把区域边框自身算成一条边。
      let rGrad = 0
      let rGradCount = 0
      for (let y = y0; y < y1; y++) {
        const row = y * width
        for (let x = x0; x < x1; x++) {
          const p = (row + x) * 4
          rs += data[p]
          gs += data[p + 1]
          bs += data[p + 2]
          const y2 = luma[row + x]
          rn++
          rSum += y2
          rSumSq += y2 * y2
          if (y2 >= 240) rOver++
          if (x > x0 && x < x1 - 1 && y > y0 && y < y1 - 1) {
            rGrad += Math.abs(luma[row + x + 1] - y2) + Math.abs(luma[row + width + x] - y2)
            rGradCount += 2
          }
        }
      }
      const meanR = rn > 0 ? rs / rn : 0
      const meanG = rn > 0 ? gs / rn : 0
      const meanB = rn > 0 ? bs / rn : 0
      const rMean = rn > 0 ? rSum / rn : 0
      result.regions[region.name] = {
        meanLuma: rn > 0 ? round((rs * 0.2126 + gs * 0.7152 + bs * 0.0722) / rn, 2) : 0,
        // 区域内的亮度标准差 / 梯度均值：判断"这块表面有没有可见纹理"的唯一依据。
        // 同一块墙、同一曝光下，stdLuma 变大就是表面真的多了起伏，而不是整体变亮。
        stdLuma: rn > 0 ? round(Math.sqrt(Math.max(0, rSumSq / rn - rMean * rMean)), 2) : 0,
        detailEnergy: rGradCount > 0 ? round(rGrad / rGradCount, 3) : 0,
        overexposureRatio: rn > 0 ? round(rOver / rn, 4) : 0,
        rgb: [Math.round(meanR), Math.round(meanG), Math.round(meanB)],
        // 天空"被打白"的客观判据：白/灰的天空 B−R 趋近 0，蓝天应有明显正值。
        blueBias: Math.round(meanB - meanR),
      }
    }
  }

  return result
}

function round(value, digits) {
  const f = 10 ** digits
  return Math.round(value * f) / f
}

/** CRC32（PNG chunk 校验）。 */
const CRC_TABLE = (() => {
  const table = new Uint32Array(256)
  for (let n = 0; n < 256; n++) {
    let c = n
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1
    table[n] = c >>> 0
  }
  return table
})()

function crc32(buf) {
  let c = 0xffffffff
  for (let i = 0; i < buf.length; i++) c = CRC_TABLE[(c ^ buf[i]) & 0xff] ^ (c >>> 8)
  return (c ^ 0xffffffff) >>> 0
}

/** 把 RGBA 写成一个 colorType=6 / 8bit / 非交错 PNG（filter 全 0，兼容性最好）。 */
export function encodePng(width, height, rgba) {
  const stride = width * 4
  const raw = Buffer.alloc((stride + 1) * height)
  for (let y = 0; y < height; y++) {
    raw[y * (stride + 1)] = 0
    Buffer.from(rgba.buffer, rgba.byteOffset + y * stride, stride)
      .copy(raw, y * (stride + 1) + 1)
  }
  const deflated = deflateSync(raw, { level: 6 })

  const chunk = (type, data) => {
    const out = Buffer.alloc(12 + data.length)
    out.writeUInt32BE(data.length, 0)
    out.write(type, 4, 'ascii')
    data.copy(out, 8)
    const crcBuf = Buffer.alloc(4 + data.length)
    crcBuf.write(type, 0, 'ascii')
    data.copy(crcBuf, 4)
    out.writeUInt32BE(crc32(crcBuf), 8 + data.length)
    return out
  }

  const ihdr = Buffer.alloc(13)
  ihdr.writeUInt32BE(width, 0)
  ihdr.writeUInt32BE(height, 4)
  ihdr[8] = 8    // bit depth
  ihdr[9] = 6    // RGBA
  ihdr[10] = 0   // compression
  ihdr[11] = 0   // filter
  ihdr[12] = 0   // interlace

  return Buffer.concat([
    PNG_SIGNATURE,
    chunk('IHDR', ihdr),
    chunk('IDAT', deflated),
    chunk('IEND', Buffer.alloc(0)),
  ])
}

/**
 * 区域裁剪 + 整数倍降采样，落盘成小图。
 *
 * 用途只有一个：**让人真的能看图**。2400x1500 的原图既塞不进上下文，
 * 也没法并排对比；裁成两三百像素宽的小条才能一眼看出"墙面有没有抹灰痕"。
 *
 * @param {object} options
 * @param {[number,number,number,number]} options.rect 归一化裁剪框 [x,y,w,h]，0..1
 * @param {number} [options.step] 降采样步长（2 = 边长各减半）
 */
export function cropScaleToFile(src, dst, options = {}) {
  const { width, height, data } = decodePng(src)
  const [rx, ry, rw, rh] = options.rect ?? [0, 0, 1, 1]
  const step = Math.max(1, Math.round(options.step ?? 1))

  const x0 = Math.max(0, Math.floor(rx * width))
  const y0 = Math.max(0, Math.floor(ry * height))
  const x1 = Math.min(width, Math.ceil((rx + rw) * width))
  const y1 = Math.min(height, Math.ceil((ry + rh) * height))
  const cw = Math.max(1, x1 - x0)
  const ch = Math.max(1, y1 - y0)
  const ow = Math.max(1, Math.floor(cw / step))
  const oh = Math.max(1, Math.floor(ch / step))

  const out = new Uint8Array(ow * oh * 4)
  for (let y = 0; y < oh; y++) {
    for (let x = 0; x < ow; x++) {
      const sx = x0 + x * step
      const sy = y0 + y * step
      const s = (sy * width + sx) * 4
      const d = (y * ow + x) * 4
      out[d] = data[s]; out[d + 1] = data[s + 1]; out[d + 2] = data[s + 2]; out[d + 3] = 255
    }
  }

  const png = encodePng(ow, oh, out)
  writeFileSync(dst, png)
  return { width: ow, height: oh, bytes: png.length }
}

/** 把若干张图**横向并排**成一张对比图（高度必须一致，会按第一张的高度裁齐）。 */
export function sideBySideToFile(sources, dst, options = {}) {
  const step = Math.max(1, Math.round(options.step ?? 1))
  const decoded = sources.map((item) => (typeof item === 'string' ? { file: item } : item))
    .map((item) => {
      const img = decodePng(item.file)
      const [rx, ry, rw, rh] = item.rect ?? [0, 0, 1, 1]
      return {
        img,
        x0: Math.max(0, Math.floor(rx * img.width)),
        y0: Math.max(0, Math.floor(ry * img.height)),
        x1: Math.min(img.width, Math.ceil((rx + rw) * img.width)),
        y1: Math.min(img.height, Math.ceil((ry + rh) * img.height)),
      }
    })

  const cellW = Math.min(...decoded.map((c) => Math.floor((c.x1 - c.x0) / step)))
  const cellH = Math.min(...decoded.map((c) => Math.floor((c.y1 - c.y0) / step)))
  const gap = options.gap ?? 4
  const ow = cellW * decoded.length + gap * (decoded.length - 1)
  const oh = cellH

  const out = new Uint8Array(ow * oh * 4).fill(24)
  decoded.forEach((cell, index) => {
    const baseX = index * (cellW + gap)
    for (let y = 0; y < cellH; y++) {
      for (let x = 0; x < cellW; x++) {
        const s = ((cell.y0 + y * step) * cell.img.width + (cell.x0 + x * step)) * 4
        const d = (y * ow + baseX + x) * 4
        out[d] = cell.img.data[s]
        out[d + 1] = cell.img.data[s + 1]
        out[d + 2] = cell.img.data[s + 2]
        out[d + 3] = 255
      }
    }
  })

  const png = encodePng(ow, oh, out)
  writeFileSync(dst, png)
  return { width: ow, height: oh, bytes: png.length }
}

/** 命令行入口：`node pngStats.mjs a.png [b.png ...]` */
if (process.argv[1] && process.argv[1].endsWith('pngStats.mjs')) {
  for (const file of process.argv.slice(2)) {
    // eslint-disable-next-line no-console
    console.log(JSON.stringify(analyzePng(file)))
  }
}
