import * as THREE from 'three'
import type { TimeOfDay } from './defaultWorldLook'

// 只缓存八个内置资源的压缩字节，不常驻多张 8K 解码图或 GPU 纹理。
const sources = new Map<string, Promise<Blob>>()

export type SkyTextureQuality = 'preview' | 'full'

export async function loadSkyTexture(time: TimeOfDay, quality: SkyTextureQuality,
  isCurrent: () => boolean): Promise<THREE.Texture | null> {
  const url = `${import.meta.env.BASE_URL}skies/${time}${quality === 'preview' ? '.preview' : ''}.webp`
  let source = sources.get(url)
  if (!source) {
    source = fetch(url).then(response => {
      if (!response.ok) throw new Error(`天空资源加载失败：${response.status}`)
      return response.blob()
    }).catch(error => { sources.delete(url); throw error })
    sources.set(url, source)
  }
  const blob = await source
  if (!isCurrent()) return null
  let texture: THREE.Texture
  if (typeof createImageBitmap === 'function') {
    const bitmap = await createImageBitmap(blob, {
      imageOrientation: 'flipY', premultiplyAlpha: 'none', colorSpaceConversion: 'none',
    })
    texture = new THREE.Texture(bitmap)
    texture.flipY = false
    texture.addEventListener('dispose', () => bitmap.close())
  } else {
    const objectUrl = URL.createObjectURL(blob)
    try { texture = await new THREE.TextureLoader().loadAsync(objectUrl) }
    finally { URL.revokeObjectURL(objectUrl) }
  }
  texture.colorSpace = THREE.SRGBColorSpace
  texture.name = `Sky:${time}:${quality}`
  texture.wrapS = THREE.RepeatWrapping
  texture.needsUpdate = true
  if (!isCurrent()) { texture.dispose(); return null }
  return texture
}
