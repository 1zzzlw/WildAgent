/**
 * 光照运行时（引擎侧）：半球光 + 关键光（含阴影）的**机制**。
 *
 * 为什么放到引擎里：阴影正交框、bias、normalBias 这三个量是互相耦合的，
 * 而且都随【太阳高度角】与【建筑尺寸】变化。以前这套推导只写在
 * `CanvasViewport.vue` 的 `updateLightingToBounds()` 里，于是任何别的渲染方
 * （`lantu/viewer`、离线出图）只能自己拍一组固定参数 —— 结果是"同一个蓝图、
 * 两套光影"，而查看器为了补光又不得不自己造光，引擎行为就被本地代码掩盖了。
 *
 * 职责边界：本文件只管**怎么把光放到正确的位置、阴影框怎么算**；
 * "现在是白天还是黄昏、太阳在哪个方位、光强多少"属于策略，仍在调用方。
 */

import * as THREE from 'three'

/**
 * 关键光高度角下限（度）—— 仅作【数值护栏】，防止太阳贴地平线时 far 爆炸（1/tan → ∞）。
 * 预设中最低是黄昏 6°，正常情况下不会触发；刻意不改动光方向本身，
 * 这样"可见的太阳位置"与"主光方向"始终一致（否则落影会与天空里的太阳对不上）。
 */
const SHADOW_MIN_ELEVATION_DEG = 5
/** normalBias 折算成【纹素数】表达，这样它与 mapSize / extent 自动保持自洽。 */
const SHADOW_NORMAL_BIAS_TEXELS = 1.5
/** 阴影深度 bias 的目标世界空间偏移量；实际写入前会按 far − near 换算。 */
const SHADOW_BIAS_WORLD = 0.01

export interface WorldLightingAppearance {
  hemisphereSkyColor: number
  hemisphereGroundColor: number
  hemisphereIntensity: number
  keyColor: number
  keyIntensity: number
}

export interface ShadowFitOptions {
  /** 阴影贴图被改动后回调（调用方据此置 `renderer.shadowMap.needsUpdate`）。 */
  onShadowsDirty?: () => void
}

export interface ShadowFitResult {
  /** 正交阴影框半宽。 */
  extent: number
  /** 关键光到场景中心的世界距离。 */
  lightDistance: number
}

export interface WorldLightingRigOptions {
  /** 阴影贴图边长。默认 2048（与编辑器"均衡"档一致）。 */
  shadowMapSize?: number
}

/**
 * 引擎光照骨架：半球光（环境补光）+ 关键光（平行光，带阴影）。
 *
 * 刻意**不**提供 AmbientLight —— `scene.environment`（IBL）已经承担了漫反射环境光，
 * 再叠一层均匀环境光只会把接触阴影洗掉、让白色墙面失去朝向感。
 */
export class WorldLightingRig {
  readonly hemisphere: THREE.HemisphereLight
  readonly key: THREE.DirectionalLight
  private shadowExtent = 8

  constructor(scene: THREE.Scene, options: WorldLightingRigOptions = {}) {
    const shadowMapSize = options.shadowMapSize ?? 2048

    this.hemisphere = new THREE.HemisphereLight(0xddeeff, 0x665544, 0.75)
    this.hemisphere.name = 'WorldHemisphereLight'
    scene.add(this.hemisphere)

    this.key = new THREE.DirectionalLight(0xfff4df, 2.4)
    this.key.name = 'WorldKeyLight'
    this.key.position.set(10, 20, 10)
    this.key.castShadow = true
    this.key.shadow.mapSize.width = shadowMapSize
    this.key.shadow.mapSize.height = shadowMapSize
    this.key.shadow.bias = -0.0002
    this.key.shadow.normalBias = 0.025
    // 这里【不要】设 shadow.radius：three r160 的 shadowRadius 只在 SHADOWMAP_TYPE_PCF 分支
    // 被引用（shadowmap_pars_fragment.glsl.js:122-125），而 PCFSoftShadowMap 编译出的
    // PCF_SOFT 分支用固定 9 抽样 bilinear kernel、完全不读它 ⇒ radius 是个死配置。
    // 想要更柔的阴影只能降 mapSize，或换成 VSMShadowMap（需另行处理漏光与 bias）。
    // 阴影相关的 bias / normalBias / 相机范围统一由 fitToBounds() 按实时参数推导。
    this.key.shadow.autoUpdate = false
    this.key.shadow.camera.left = -20
    this.key.shadow.camera.right = 20
    this.key.shadow.camera.top = 20
    this.key.shadow.camera.bottom = -20
    scene.add(this.key)
    scene.add(this.key.target)
  }

  /** 当前正交阴影框半宽（由最近一次 fitToBounds 推导）。 */
  get extent(): number {
    return this.shadowExtent
  }

  /** 应用时段/环境/天气合成后的外观参数。颜色与强度都由调用方算好。 */
  applyAppearance(appearance: WorldLightingAppearance): void {
    this.hemisphere.color.setHex(appearance.hemisphereSkyColor)
    this.hemisphere.groundColor.setHex(appearance.hemisphereGroundColor)
    this.hemisphere.intensity = appearance.hemisphereIntensity
    this.key.color.setHex(appearance.keyColor)
    this.key.intensity = appearance.keyIntensity
  }

  /**
   * 改阴影贴图尺寸。必须连同 `shadow.map` 一起重建，否则 three 会继续用旧尺寸的 RT。
   */
  setShadowMapSize(size: number, maxTextureSize = Number.POSITIVE_INFINITY): boolean {
    const next = Math.min(size, maxTextureSize)
    if (this.key.shadow.mapSize.width === next) return false
    this.key.shadow.map?.dispose()
    this.key.shadow.map = null
    this.key.shadow.mapSize.set(next, next)
    return true
  }

  /**
   * 按场景包围盒 + 关键光方向推导阴影正交框、光位与 bias。
   *
   * ── 阴影正交框必须同时罩住【投影体】与【落影区】 ──
   * 片元一旦落在框外，GLSL 的 inFrustum 为 false ⇒ 直接返回 shadow = 1（无阴影），
   * 表现为投影边缘一条笔直的裁切线。
   * 关键点：正交框与 far 都必须按【落影行程】放大 —— 黄昏 6° 时 10.95m 高的建筑投影要走
   * 104m，固定 far ≈ 55 会把长影在中途硬切。
   */
  fitToBounds(
    center: THREE.Vector3,
    size: THREE.Vector3,
    keyLightDirection: THREE.Vector3,
    options: ShadowFitOptions = {},
  ): ShadowFitResult {
    const elevation = Math.max(
      THREE.MathUtils.degToRad(SHADOW_MIN_ELEVATION_DEG),
      Math.asin(THREE.MathUtils.clamp(keyLightDirection.y, -1, 1)),
    )
    const sinElevation = Math.sin(elevation)
    const cosElevation = Math.cos(elevation)
    const horizontalRadius = 0.5 * Math.hypot(size.x, size.z)
    const halfHeight = Math.max(0, size.y) * 0.5
    // 正交框 U 轴水平、V 轴在太阳所在竖直面内，所以两个方向的上界分别是：
    //   U ≤ 足迹半对角线
    //   V ≤ 足迹半对角线 × sin(高度角) + 半高 × cos(高度角)
    // （与全量蓝图复算一致：tiantan 白天需 U 11.31 / V 13.44。）
    const extent = Math.max(horizontalRadius, horizontalRadius * sinElevation + halfHeight * cosElevation) + 1
    this.shadowExtent = extent
    // 落影行程 = 建筑高度 / tan(高度角)：6° 时约为高度的 9.5 倍。
    const shadowTravel = (halfHeight * 2) / Math.tan(elevation)
    const halfDiagonal = Math.hypot(horizontalRadius, halfHeight)
    const lightDistance = extent * 2.5

    this.key.position.copy(center).addScaledVector(keyLightDirection, lightDistance)
    this.key.target.position.copy(center)
    this.key.target.updateMatrixWorld()
    const shadowCamera = this.key.shadow.camera
    shadowCamera.left = -extent
    shadowCamera.right = extent
    shadowCamera.top = extent
    shadowCamera.bottom = -extent
    // near 按投影体的最近深度收紧（原来恒为 0.1，配 far≈130 时深度精度被白白浪费）。
    shadowCamera.near = Math.max(0.1, lightDistance - halfDiagonal * 2)
    // far 必须覆盖【落影行程】，否则低角度下长影会在中途被硬切。
    shadowCamera.far = lightDistance + shadowTravel + horizontalRadius + extent + 2
    shadowCamera.updateProjectionMatrix()

    // normalBias 按纹素表达。只写 `extent * 0.0015` 只在 mapSize = 2048 时恰好等于 1.5 纹素，
    // 换个档位就错位：1024 档只有 0.77 纹素（欠 bias → 自阴影痤疮），
    // 4096 档达 3.07 纹素（过 bias → 接触阴影变淡、薄构件漏影）。
    const shadowTexel = (2 * extent) / Math.max(1, this.key.shadow.mapSize.width)
    this.key.shadow.normalBias = Math.max(0.001, SHADOW_NORMAL_BIAS_TEXELS * shadowTexel)
    // bias 是【归一化深度】偏移，等效世界偏移 = |bias| × (far − near)，
    // 所以固定 -0.0002 在 far 从 55 涨到 200+ 之后等效偏移会翻好几倍（Peter-panning）。
    // 改为按世界空间目标偏移反推，并夹住上下限避免极端参数。
    const depthRange = Math.max(1e-3, shadowCamera.far - shadowCamera.near)
    this.key.shadow.bias = THREE.MathUtils.clamp(-SHADOW_BIAS_WORLD / depthRange, -5e-4, -2e-5)
    this.key.shadow.needsUpdate = true

    options.onShadowsDirty?.()
    return { extent, lightDistance }
  }

  dispose(): void {
    this.key.shadow.map?.dispose()
    this.key.shadow.map = null
    this.hemisphere.removeFromParent()
    this.key.target.removeFromParent()
    this.key.removeFromParent()
  }
}
