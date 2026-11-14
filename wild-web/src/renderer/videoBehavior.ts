import * as THREE from 'three'
import type { ExtensionElementBehavior } from 'wild-core/types'
import type { ElementBehaviorContext, ElementBehaviorInstance } from './elementBehaviorRuntime'

/** Three 0.160 的 VideoTexture 帧回调无法取消，改由行为实例持有并释放回调。 */
class ManagedVideoTexture extends THREE.Texture {
  readonly isVideoTexture = true

  constructor(video: HTMLVideoElement) {
    super(video)
    this.minFilter = this.magFilter = THREE.LinearFilter
    this.generateMipmaps = false
    this.colorSpace = THREE.SRGBColorSpace
  }

  update(): void {
    const video = this.image as HTMLVideoElement
    if (typeof video.requestVideoFrameCallback !== 'function' && video.readyState >= video.HAVE_CURRENT_DATA) {
      this.needsUpdate = true
    }
  }
}

/** 视频只拥有自己的播放器、纹理和屏幕材质，其他部件继续复用材质缓存。 */
export function createVideoBehavior(
  mesh: THREE.Mesh,
  behavior: ExtensionElementBehavior,
  context: ElementBehaviorContext,
): ElementBehaviorInstance {
  const src = String(behavior.config.src).trim()
  const screen = new THREE.MeshBasicMaterial({ color: 0x080808, toneMapped: false })
  if (mesh.userData.ownsMaterial) {
    const previous = Array.isArray(mesh.material) ? mesh.material : [mesh.material]
    previous.forEach(material => material.dispose())
  }
  mesh.material = screen
  mesh.userData.ownsMaterial = true
  const label = '右键 · 播放/暂停视频'
  if (!src) {
    return { label: '请先填写视频资源地址', interact: () => {}, dispose: () => {} }
  }

  // 建筑 UV 使用米制平铺；视频按表面两条主轴归一化，完整映射到屏幕。
  const geometry = mesh.geometry
  geometry.computeBoundingBox()
  const bounds = geometry.boundingBox!
  const size = bounds.getSize(new THREE.Vector3())
  const thinAxis = [size.x, size.y, size.z].indexOf(Math.min(size.x, size.y, size.z))
  const [uAxis, vAxis] = thinAxis === 0 ? [2, 1] : thinAxis === 1 ? [0, 2] : [0, 1]
  const position = geometry.getAttribute('position'), uv = new Float32Array(position.count*2)
  const point = new THREE.Vector3()
  for (let i = 0; i < position.count; i++) {
    point.fromBufferAttribute(position, i)
    uv[i*2] = (point.getComponent(uAxis) - bounds.min.getComponent(uAxis)) / Math.max(1e-8, size.getComponent(uAxis))
    uv[i*2+1] = (point.getComponent(vAxis) - bounds.min.getComponent(vAxis)) / Math.max(1e-8, size.getComponent(vAxis))
  }
  geometry.setAttribute('uv', new THREE.BufferAttribute(uv, 2))

  const video = document.createElement('video')
  video.crossOrigin = 'anonymous'
  video.playsInline = true
  video.preload = 'metadata'
  video.loop = behavior.config.loop !== false
  video.muted = behavior.config.muted !== false
  const texture = new ManagedVideoTexture(video)
  screen.map = texture
  screen.color.setHex(0xffffff)
  screen.needsUpdate = true
  let disposed = false
  let playRequested = false
  let playGeneration = 0
  let frameId: number | null = null
  const hasFrameCallback = typeof video.requestVideoFrameCallback === 'function'
  const requestFrame = () => {
    frameId = null
    if (disposed || video.paused || video.ended) return
    texture.needsUpdate = true
    context.requestRender()
    if (hasFrameCallback) frameId = video.requestVideoFrameCallback(requestFrame)
  }
  const status = (event?: Event) => {
    if (disposed) return
    if (event?.type === 'pause' || video.ended || video.error) playRequested = false
    if (video.error) mesh.userData.mediaError = video.error.message
    if (video.readyState >= video.HAVE_CURRENT_DATA) texture.needsUpdate = true
    mesh.userData.mediaState = video.error ? 'error' : video.ended ? 'ended' : video.paused ? 'paused' : 'playing'
    if (!video.paused && !video.ended && hasFrameCallback && frameId === null) {
      frameId = video.requestVideoFrameCallback(requestFrame)
    }
    context.requestRender()
  }
  const play = () => {
    const generation = ++playGeneration
    playRequested = true
    mesh.userData.mediaError = ''
    void video.play().then(() => {
      if (!disposed && generation === playGeneration) status()
    }).catch((error: unknown) => {
      if (disposed || !playRequested || generation !== playGeneration) return
      playRequested = false
      mesh.userData.mediaState = 'error'
      mesh.userData.mediaError = error instanceof Error ? error.message : String(error)
      context.requestRender()
    })
  }
  const events = ['loadeddata', 'play', 'pause', 'ended', 'error', 'seeked', 'timeupdate']
  events.forEach(event => video.addEventListener(event, status))
  video.src = src
  mesh.userData.mediaState = 'paused'
  if (behavior.config.autoplay === true) play()
  return {
    get label() { return mesh.userData.mediaError ? '视频不可播放，请检查资源地址与访问权限' : label },
    interact() {
      if (playRequested || !video.paused) {
        playRequested = false
        playGeneration++
        video.pause()
      } else play()
    },
    tick: () => !disposed && !hasFrameCallback && !video.paused && !video.ended,
    dispose() {
      disposed = true
      playRequested = false
      playGeneration++
      if (frameId !== null) video.cancelVideoFrameCallback(frameId)
      events.forEach(event => video.removeEventListener(event, status))
      video.pause()
      video.removeAttribute('src')
      video.load()
      texture.dispose()
    },
  }
}
