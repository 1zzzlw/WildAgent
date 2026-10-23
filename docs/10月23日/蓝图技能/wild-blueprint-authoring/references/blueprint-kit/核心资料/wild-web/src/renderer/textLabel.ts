import * as THREE from 'three'
import type { TextLabel } from 'wild-core/types'
import type { MaterialCache } from './materialAdapter'

/** 文字保留为 WILD 数据；渲染时生成透明印字纹理，复用现有材质/纹理生命周期。 */
export function createTextLabel(label: TextLabel, bounds: THREE.Box3, cache: MaterialCache): THREE.Mesh {
  const size = bounds.getSize(new THREE.Vector3())
  const canvas = document.createElement('canvas')
  const scale = 1024 / Math.max(size.x, size.y)
  canvas.width = Math.max(16, Math.round(size.x * scale))
  canvas.height = Math.max(16, Math.round(size.y * scale))
  const context = canvas.getContext('2d')!
  const lines = label.text.trim().split(/\r?\n/)
  const family = label.fontFamily === 'sans-serif'
    ? '"Microsoft YaHei", "Noto Sans CJK SC", sans-serif'
    : '"SimSun", "Noto Serif CJK SC", serif'
  let fontSize = canvas.height * 0.72 / lines.length
  context.font = `600 ${fontSize}px ${family}`
  const lineWidth = Math.max(...lines.map(line => context.measureText(line).width))
  if (lineWidth > canvas.width * 0.84) fontSize *= canvas.width * 0.84 / lineWidth
  context.font = `600 ${fontSize}px ${family}`
  context.textAlign = 'center'
  context.textBaseline = 'middle'
  const color = label.color ?? [0.9, 0.77, 0.47]
  context.fillStyle = `rgb(${color.map(value => Math.round(value * 255)).join(',')})`
  const lineHeight = fontSize * 1.2
  lines.forEach((line, index) => context.fillText(line, canvas.width / 2,
    canvas.height / 2 + (index - (lines.length - 1) / 2) * lineHeight))
  const material = cache.getOrCreate('__text_label', {
    baseColor: [1, 1, 1], roughness: 0.65, metallic: 0, albedo: 1, opacity: 0.98,
    embeddedImage: { encoding: 'base64', mimeType: 'image/png', data: canvas.toDataURL('image/png').split(',')[1]! },
  }, false)
  const mesh = new THREE.Mesh(new THREE.PlaneGeometry(size.x, size.y), material)
  const center = bounds.getCenter(new THREE.Vector3())
  mesh.position.set(center.x, center.y, bounds.max.z + 0.002)
  mesh.renderOrder = 2
  mesh.name = 'TextLabel'
  return mesh
}
