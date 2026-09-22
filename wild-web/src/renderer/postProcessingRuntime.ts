/**
 * 后期合成运行时（引擎侧）：EffectComposer 链路 + SSAO（接触阴影）+ Bloom + FXAA。
 *
 * 为什么放到引擎里：AO 是"建筑与地面、柱脚、楼板下缘是否贴在一起"的唯一来源。
 * 它原先只活在 `CanvasViewport.vue`，于是别的渲染方（`lantu/viewer`、离线出图）
 * 要么完全没有接触阴影，要么自己写一套 —— 两条链路的观感差异就不再代表引擎能力。
 *
 * 链路顺序与每帧 RT 交换次数的关系见 `setMsaaSamples` 的注释：
 * RenderPass(不交换) → SSAO(交换) → Bloom(不交换) → Output(交换) → FXAA(交换)。
 */

import * as THREE from 'three'
import { EffectComposer } from 'three/examples/jsm/postprocessing/EffectComposer.js'
import { RenderPass } from 'three/examples/jsm/postprocessing/RenderPass.js'
import { SSAOPass } from 'three/examples/jsm/postprocessing/SSAOPass.js'
import { UnrealBloomPass } from 'three/examples/jsm/postprocessing/UnrealBloomPass.js'
import { OutputPass } from 'three/examples/jsm/postprocessing/OutputPass.js'
import { ShaderPass } from 'three/examples/jsm/postprocessing/ShaderPass.js'
import { FXAAShader } from 'three/examples/jsm/shaders/FXAAShader.js'

/** SSAO 内部 RT 的分辨率比例。0.5 ⇒ normal/ssao/blur 三个 RT 的面积降到 1/4。 */
const SSAO_RESOLUTION_SCALE = 0.5

export interface SsaoKernelOptions {
  kernelRadius?: number
  minDistance?: number
  maxDistance?: number
}

export interface WorldPostProcessingOptions extends SsaoKernelOptions {
  /** 合成 RT 的 MSAA 采样数。WebGL1 会自动回落到 0，只剩 FXAA。 */
  msaaSamples?: number
}

/**
 * 后期合成骨架。
 *
 * 刻意把 SSAO 与 Bloom 做成"默认关、由调用方按画质档开"——引擎不猜画质。
 */
export class WorldPostProcessingRuntime {
  readonly composer: EffectComposer
  readonly ssao: SSAOPass
  readonly bloom: UnrealBloomPass
  readonly fxaa: ShaderPass
  private readonly renderer: THREE.WebGLRenderer
  private appliedMsaaSamples = -1

  constructor(
    renderer: THREE.WebGLRenderer,
    scene: THREE.Scene,
    camera: THREE.Camera,
    options: WorldPostProcessingOptions = {},
  ) {
    this.renderer = renderer
    this.composer = new EffectComposer(renderer)
    this.composer.addPass(new RenderPass(scene, camera))

    // SSAO：核半径从 4 提到 6，补偿内部 RT 减半后的采样密度（否则接触阴影会变得又紧又闪）。
    //
    // `minDistance` / `maxDistance` 的单位是**视空间米**（three r160 `SSAOShader.js`
    // 里直接和 viewZ 的差比），不是"强度系数"。
    // ⚠️ 不要指望靠调大 maxDistance 出效果：实测把它从 0.3 提到 1.0，整图细节能量
    // 只从 1.200 动到 1.211、各区域标准差一位不动 —— 因为**屏幕空间遮蔽只在凹处生效**，
    // 而 `modern_pool_villa` 是个凸体（外墙外凸、无可视的檐下与内转角），本来就没多少
    // 可遮蔽的地方。"建筑像白盒子"的成因不是 AO 半径，是曝光与没有几何细部（S3）。
    this.ssao = new SSAOPass(scene, camera)
    this.ssao.kernelRadius = options.kernelRadius ?? 6
    this.ssao.minDistance = options.minDistance ?? 0.002
    this.ssao.maxDistance = options.maxDistance ?? 0.3
    this.scaleSsao(this.ssao)
    this.composer.addPass(this.ssao)

    this.bloom = new UnrealBloomPass(new THREE.Vector2(1, 1), 0.2, 0.35, 1.05)
    this.composer.addPass(this.bloom)
    this.composer.addPass(new OutputPass())

    this.fxaa = new ShaderPass(FXAAShader)
    this.composer.addPass(this.fxaa)

    this.setMsaaSamples(options.msaaSamples ?? 4)
  }

  /** 尺寸变化：合成器 + FXAA resolution uniform（按设备像素比换算）。 */
  setSize(width: number, height: number): void {
    this.composer.setSize(width, height)
    const pixelRatio = this.renderer.getPixelRatio()
    this.fxaa.material.uniforms.resolution.value.set(
      1 / Math.max(width * pixelRatio, 1),
      1 / Math.max(height * pixelRatio, 1),
    )
  }

  setPixelRatio(pixelRatio: number): void {
    this.composer.setPixelRatio(pixelRatio)
  }

  /**
   * 合成链路 MSAA 采样数。
   *
   * ⚠️ 链路每帧净交换 3 次（奇数），所以 RenderPass 的落点会逐帧在 RT1/RT2 间交替
   * ⇒ **两个 RT 都要开**。改 samples 后必须 `dispose()`，否则已创建的帧缓冲不会按新采样数重建。
   * WebGL1 不支持 RT 多重采样，保持 0 并交由 FXAA 兜底。
   */
  setMsaaSamples(samples: number): void {
    const next = this.renderer.capabilities.isWebGL2 ? samples : 0
    if (next === this.appliedMsaaSamples) return
    for (const target of [this.composer.renderTarget1, this.composer.renderTarget2]) {
      target.samples = next
      target.dispose()
    }
    this.appliedMsaaSamples = next
  }

  setSsaoEnabled(enabled: boolean): void {
    this.ssao.enabled = enabled
  }

  setBloomEnabled(enabled: boolean): void {
    this.bloom.enabled = enabled
  }

  setFxaaEnabled(enabled: boolean): void {
    this.fxaa.enabled = enabled
  }

  render(): void {
    this.composer.render()
  }

  dispose(): void {
    this.ssao.dispose()
    this.bloom.dispose()
    this.fxaa.material.dispose()
    this.composer.dispose()
  }

  /**
   * 让 SSAO 真正跑在半分辨率上。
   *
   * 两个坑：
   *   1) `SSAOPass(scene, camera, width, height)` 的 width/height 是【目标像素尺寸】而非比例，
   *      默认 512；传 0.5 只会把初始 RT 建成 1×1，语义上并不是"半分辨率"。
   *   2) `SSAOPass.setSize()`（three r160 `examples/jsm/postprocessing/SSAOPass.js`）会把
   *      ssao/normal/blur 三个 RT 直接设为传入尺寸，内部【没有任何缩放系数】；
   *      而 `EffectComposer.setSize()` 会按 `width * pixelRatio` 逐个 pass 下发
   *      ⇒ 构造函数里的 0.5 会被全量覆盖，SSAO 实际一直跑全分辨率。
   * 所以只能在入口处包装 setSize —— 好在它内部会一并同步 resolution uniform 与投影矩阵 uniform，
   * 缩放入参即自洽。
   *
   * 为什么缩小是安全的：r160 的 `SSAOPass.OUTPUT.Default` 以合成器的 `readBuffer.texture`
   * （全分辨率）作为底图，只用 blurRenderTarget 走 CustomBlending 叠加 AO 项，
   * 因此缩小内部 RT 不会降低底图清晰度，只会让 AO 项被线性上采样 —— 这本就是 AO 的常规做法。
   */
  private scaleSsao(pass: SSAOPass): void {
    const baseSetSize = pass.setSize.bind(pass)
    pass.setSize = (width: number, height: number) =>
      baseSetSize(
        Math.max(1, Math.round(width * SSAO_RESOLUTION_SCALE)),
        Math.max(1, Math.round(height * SSAO_RESOLUTION_SCALE)),
      )
  }
}
