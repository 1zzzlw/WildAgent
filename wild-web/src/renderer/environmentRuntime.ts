/**
 * 环境运行时（引擎侧）：环境贴图（IBL）+ 天空 uniform + 日月精灵。
 *
 * ── 为什么必须放在 `src/renderer/` 里 ──────────────────────────────
 * `materialAdapter` 是按"场景里存在 `scene.environment`"来设计材质的：
 * 玻璃走 `transmission` + `ior`、金属走 `envMapIntensity`，两者都靠 IBL 出反射。
 * 但历史上这段生产环境贴图的代码被写死在 `CanvasViewport.vue` 里，
 * 于是**任何不经过编辑器视口的渲染方**（`lantu/viewer`、离线出图脚本）都拿不到
 * `scene.environment` —— 表现就是"玻璃死蓝、金属发暗、没有反射"，
 * 而渲染方为了自救只能在本地再搭一套光照，等于把引擎行为抄了一遍。
 *
 * 所以这里把**机制**（PMREM 生产、重建调度、释放）收进引擎，
 * 把**策略**（用哪个时段/环境预设）留给调用方。
 *
 * 职责边界：
 *   - 本文件只管"环境贴图怎么产生、什么时候重建、怎么释放"；
 *   - 不管"当前应该是白天还是黄昏"（策略在 `defaultWorldLook` + 调用方）；
 *   - 不管主场景的天空实体/日月/天气层（那是编辑器视口自己的观察道具）。
 */

import * as THREE from 'three'
import { Sky } from 'three/examples/jsm/objects/Sky.js'
import type { TimePreset } from './defaultWorldLook'
import type { WorldAtmosphereAppearance } from './worldWeatherRuntime'

/** 夜晚沿用更模糊的环境贴图（月光散射），白天用更锐的（太阳镜面高光要清晰）。 */
const ENVIRONMENT_SIGMA_DAY = 0.045
const ENVIRONMENT_SIGMA_NIGHT = 0.16
const ENVIRONMENT_NEAR = 0.1
const ENVIRONMENT_FAR = 1000
/** 环境贴图内太阳亮点的放置半径，必须远大于 PMREM 采样半径。 */
const ENVIRONMENT_SUN_DISTANCE = 380
/** 天空穹顶与太阳亮点的世界尺度。 */
const SKY_SCALE = 450
const ENVIRONMENT_SUN_SCALE = 60

/**
 * 日月精灵：程序化画布贴图，供主场景（观察者看到的太阳/月亮）与环境贴图共用。
 * 刻意共用一份实现 —— 环境贴图里的太阳亮点必须与画面上看到的太阳同向同形，
 * 否则金属/玻璃上的高光会从"太阳在另一侧"的方向冒出来。
 */
export function createCelestialBody(kind: 'sun' | 'moon'): THREE.Sprite {
  const canvas = document.createElement('canvas')
  canvas.width = 128
  canvas.height = 128
  const context = canvas.getContext('2d')
  if (context) {
    if (kind === 'sun') {
      const glow = context.createRadialGradient(64, 64, 4, 64, 64, 62)
      glow.addColorStop(0, 'rgba(255,255,250,1)')
      glow.addColorStop(0.3, 'rgba(255,240,200,0.92)')
      glow.addColorStop(0.55, 'rgba(255,214,130,0.55)')
      glow.addColorStop(1, 'rgba(255,180,80,0)')
      context.fillStyle = glow
      context.fillRect(0, 0, 128, 128)
      // 明亮日轮，边缘清晰可见
      context.fillStyle = 'rgba(255,252,242,1)'
      context.beginPath()
      context.arc(64, 64, 24, 0, Math.PI * 2)
      context.fill()
    } else {
      context.fillStyle = 'rgba(224,232,244,0.96)'
      context.beginPath()
      context.arc(64, 64, 47, 0, Math.PI * 2)
      context.fill()
      context.fillStyle = 'rgba(155,169,188,0.28)'
      for (const [x, y, radius] of [[45, 47, 9], [78, 38, 6], [82, 73, 11], [49, 82, 5]]) {
        context.beginPath()
        context.arc(x, y, radius, 0, Math.PI * 2)
        context.fill()
      }
    }
  }
  const texture = new THREE.CanvasTexture(canvas)
  texture.colorSpace = THREE.SRGBColorSpace
  const material = new THREE.SpriteMaterial({
    map: texture,
    color: 0xffffff,
    transparent: true,
    opacity: 1,
    depthWrite: false,
    depthTest: true,
    fog: false,
    toneMapped: false,
  })
  const body = new THREE.Sprite(material)
  body.name = kind === 'sun' ? 'WorldSun' : 'WorldMoon'
  body.renderOrder = 3
  return body
}

/**
 * 把时段预设 + 天气大气写进一个 Sky 实例的 uniform。
 *
 * 天气对天空的影响不是"另加一层雾"，而是**改写大气散射参数**：
 * 云抬高浑浊度、尘埃偏暖、雾压低米氏系数 —— 这样天空的色相与亮度才会
 * 与环境贴图（同一套 uniform 烘出来的）保持一致。
 */
export function syncSkyPreset(
  target: Sky,
  preset: TimePreset,
  atmosphere: WorldAtmosphereAppearance,
  sunDirection: THREE.Vector3,
): void {
  const uniforms = target.material.uniforms
  uniforms.turbidity.value = preset.turbidity
    + atmosphere.cloud * 7
    + atmosphere.rain * 3
    + atmosphere.dust * 9
    + atmosphere.fog * 4
  uniforms.rayleigh.value = Math.max(0.08, preset.rayleigh * (1 - atmosphere.cloud * 0.38))
  uniforms.mieCoefficient.value = Math.min(
    0.08,
    preset.mieCoefficient + atmosphere.cloud * 0.012 + atmosphere.fog * 0.018 + atmosphere.dust * 0.026,
  )
  uniforms.mieDirectionalG.value = Math.min(0.96, preset.mieDirectionalG + atmosphere.fog * 0.04)
  uniforms.sunPosition.value.copy(sunDirection)
}

/**
 * 影响环境贴图的输入签名。所有会改变天空观感的量都必须在里面，
 * 否则会出现"改了天气但环境贴图没跟上"。
 *
 * 量化到 1/32：肉眼不可辨，但能把连续拖动滑杆产生的大量中间态折叠掉。
 */
export function buildEnvironmentSignature(
  preset: TimePreset,
  atmosphere: WorldAtmosphereAppearance,
  isNight: boolean,
): string {
  const q = (value: number) => Math.round(value * 32) / 32
  return [
    preset.label,
    q(atmosphere.cloud),
    q(atmosphere.rain),
    q(atmosphere.snow),
    q(atmosphere.dust),
    q(atmosphere.fog),
    q(atmosphere.tintStrength),
    atmosphere.backgroundTint,
    isNight ? 'night' : 'day',
  ].join('|')
}

export interface WorldEnvironmentMapOptions {
  /** 节流窗口（毫秒）。窗口内最多重建一次，窗口末尾一定落地最终状态。 */
  throttleMs?: number
  /** 每次真正重建完成后回调（调用方用来请求重绘）。 */
  onRebuilt?: () => void
}

/**
 * 环境贴图运行时：持有 PMREM generator 与一个离屏环境场景，
 * 负责把它烘成 `scene.environment`，并按签名去重 + 前后沿节流。
 *
 * 为什么需要节流：`pmremGenerator.fromScene()` 是**一遍立方图 6 面渲染 + 卷积 +
 * 纹理创建 + 旧纹理销毁**。而天气面板的滑杆走的是连续 `@input`，
 * 一次拖动能打出上百个事件。实测 60 个事件会触发 59 次 `fromScene()`。
 * 策略因此是：签名去重（量化 1/32）+ 前 120ms 内首次变化立即重建（离散操作无延迟感）
 * + 其后合并到窗口末尾（拖动期间最多约 8 次/秒，且松开一定落地最终态）。
 */
export class WorldEnvironmentMapRuntime {
  private readonly scene: THREE.Scene
  private readonly throttleMs: number
  private readonly onRebuilt: (() => void) | undefined
  private pmrem: THREE.PMREMGenerator | null = null
  private environmentScene: THREE.Scene | null = null
  private environmentSky: Sky | null = null
  private environmentSunSprite: THREE.Sprite | null = null
  private target: THREE.WebGLRenderTarget | null = null
  private lastRebuildTime = 0
  private lastSignature = ''
  private timer: ReturnType<typeof setTimeout> | null = null
  private pending: {
    preset: TimePreset
    atmosphere: WorldAtmosphereAppearance
    sunDirection: THREE.Vector3
    isNight: boolean
  } | null = null

  constructor(
    renderer: THREE.WebGLRenderer,
    scene: THREE.Scene,
    options: WorldEnvironmentMapOptions = {},
  ) {
    this.scene = scene
    this.throttleMs = options.throttleMs ?? 120
    this.onRebuilt = options.onRebuilt

    this.pmrem = new THREE.PMREMGenerator(renderer)
    this.pmrem.compileCubemapShader()
    this.environmentScene = new THREE.Scene()
    this.environmentSky = new Sky()
    this.environmentSky.scale.setScalar(SKY_SCALE)
    this.environmentScene.add(this.environmentSky)
    // 环境贴图内的太阳亮点：让 IBL 反射出现真实太阳镜面高光（材质更立体）。
    this.environmentSunSprite = createCelestialBody('sun')
    this.environmentSunSprite.scale.setScalar(ENVIRONMENT_SUN_SCALE)
    this.environmentSunSprite.name = 'EnvironmentSun'
    this.environmentScene.add(this.environmentSunSprite)
  }

  /** 当前生效的环境贴图；没有则为 null（调用方可据此判断 IBL 是否可用）。 */
  get texture(): THREE.Texture | null {
    return this.target?.texture ?? null
  }

  /** 是否已经产出过环境贴图。 */
  get ready(): boolean {
    return this.target !== null
  }

  /**
   * 立即重建环境贴图。签名与节流都绕开，用于时段/环境档/profile 这类离散切换。
   * 返回是否真的重建（环境场景尚未就绪时返回 false）。
   */
  rebuild(
    preset: TimePreset,
    atmosphere: WorldAtmosphereAppearance,
    sunDirection: THREE.Vector3,
    isNight: boolean,
  ): boolean {
    if (!this.pmrem || !this.environmentScene || !this.environmentSky) return false

    syncSkyPreset(this.environmentSky, preset, atmosphere, sunDirection)
    this.environmentScene.background = new THREE.Color(preset.background)
      .lerp(new THREE.Color(atmosphere.backgroundTint), atmosphere.tintStrength)
    if (this.environmentSunSprite) {
      // 沿太阳方向放置亮点（距离远于 PMREM 半径），夜晚隐藏避免月光串色。
      this.environmentSunSprite.position.copy(sunDirection).multiplyScalar(ENVIRONMENT_SUN_DISTANCE)
      this.environmentSunSprite.visible = !isNight
    }

    const nextTarget = this.pmrem.fromScene(
      this.environmentScene,
      isNight ? ENVIRONMENT_SIGMA_NIGHT : ENVIRONMENT_SIGMA_DAY,
      ENVIRONMENT_NEAR,
      ENVIRONMENT_FAR,
    )
    const previousTarget = this.target
    this.target = nextTarget
    // IBL 强度由 materialAdapter 的 envMapIntensity（非金属 1.0 / 金属 1.0~1.8）承担，
    // 太阳亮点已通过 environmentSunSprite 注入环境贴图，材质反射/高光更立体。
    this.scene.environment = nextTarget.texture
    previousTarget?.dispose()
    return true
  }

  /**
   * 调度一次重建：签名相同的重复请求直接丢弃，连续请求按窗口合并。
   *
   * @param force 离散切换（时段/环境档/画质档/WILD profile）传 true，绕过去重与节流。
   */
  schedule(
    preset: TimePreset,
    atmosphere: WorldAtmosphereAppearance,
    sunDirection: THREE.Vector3,
    isNight: boolean,
    force = false,
  ): void {
    const signature = buildEnvironmentSignature(preset, atmosphere, isNight)
    if (!force && signature === this.lastSignature && this.pending === null) return
    this.pending = { preset, atmosphere, sunDirection: sunDirection.clone(), isNight }
    const elapsed = performance.now() - this.lastRebuildTime
    if (force || elapsed >= this.throttleMs) {
      this.flush()
      return
    }
    if (this.timer === null) {
      this.timer = setTimeout(() => this.flush(), this.throttleMs - elapsed)
    }
  }

  /** 把挂起的重建立刻落地。 */
  flush(): void {
    if (this.timer !== null) {
      clearTimeout(this.timer)
      this.timer = null
    }
    const pending = this.pending
    this.pending = null
    if (!pending) return
    // 签名与时间戳都按"落地时"的参数记，避免把被合并掉的中间态当成已应用状态。
    this.lastRebuildTime = performance.now()
    this.lastSignature = buildEnvironmentSignature(pending.preset, pending.atmosphere, pending.isNight)
    if (this.rebuild(pending.preset, pending.atmosphere, pending.sunDirection, pending.isNight)) {
      this.onRebuilt?.()
    }
  }

  dispose(): void {
    if (this.timer !== null) {
      clearTimeout(this.timer)
      this.timer = null
    }
    this.pending = null
    this.scene.environment = null
    this.target?.dispose()
    this.target = null
    this.pmrem?.dispose()
    this.pmrem = null
    this.environmentSky?.geometry.dispose()
    this.environmentSky?.material.dispose()
    this.environmentSky = null
    const sprite = this.environmentSunSprite
    if (sprite) {
      const material = sprite.material as THREE.SpriteMaterial
      material.map?.dispose()
      material.dispose()
      sprite.removeFromParent()
      this.environmentSunSprite = null
    }
    this.environmentScene?.clear()
    this.environmentScene = null
  }
}
