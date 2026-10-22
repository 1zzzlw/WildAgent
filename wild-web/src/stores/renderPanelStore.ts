/**
 * 渲染控制面板状态（毛玻璃面板的唯一事实源）。
 *
 * 面板组件（RenderControlPanel.vue）只负责展示与开关；
 * CanvasViewport 是这些开关的**唯一执行者**——它把状态落到
 * OrbitControls / 线条叠加层 / GridHelper 上。统计数字只由
 * 渲染循环回写（节流 ~2Hz），面板侧只读。
 */

import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { CameraPresetId, EnvironmentPresetId, QualityLevel, TimeOfDay, ViewMode } from '../renderer/defaultWorldLook'

export type RenderPresetRequest =
  | { type: 'camera'; value: CameraPresetId }
  | { type: 'environment'; value: EnvironmentPresetId }
  | { type: 'quality'; value: QualityLevel }
  | { type: 'time'; value: TimeOfDay }
  | { type: 'view'; value: ViewMode }

export interface RenderStats {
  /** 平滑后的实时帧率（由渲染循环写入）。 */
  fps: number
  /** 最近一次渲染的 draw call 数（renderer.info.render.calls）。 */
  drawCalls: number
  /** 最近一次渲染的三角面数（renderer.info.render.triangles）。 */
  triangles: number
  /** 显存中的几何体数量（renderer.info.memory.geometries）。 */
  geometries: number
  /** 显存中的纹理数量（renderer.info.memory.textures）。 */
  textures: number
  /** 当前渲染分辨率（CSS 像素 × pixelRatio）。 */
  renderWidth: number
  renderHeight: number
  pixelRatio: number
}

function emptyStats(): RenderStats {
  return {
    fps: 0,
    drawCalls: 0,
    triangles: 0,
    geometries: 0,
    textures: 0,
    renderWidth: 0,
    renderHeight: 0,
    pixelRatio: 1,
  }
}

export const useRenderPanelStore = defineStore('renderPanel', () => {
  /** 面板是否收起。收起后只剩一个小圆钮，不遮挡渲染画布。 */
  const collapsed = ref(false)

  // ── 显示开关 ──
  /** 建筑线条：按相邻面夹角 > 30° 提取 EdgesGeometry 叠加层。 */
  const showEdges = ref(false)
  /** 网格地面（编辑器模式下的 gridHelper；展示模式恒隐藏）。 */
  const showGrid = ref(true)
  const waterAnimated = ref(true)
  try { waterAnimated.value = localStorage.getItem('wild_water_animated') !== 'false' } catch { /* 默认动态水面。 */ }
  /** 相机自动旋转（OrbitControls.autoRotate）。 */
  const autoRotate = ref(false)
  /** 自动旋转速度（OrbitControls.autoRotateSpeed，2.0 = 30 秒一圈）。 */
  const autoRotateSpeed = ref(1.2)

  // ── 一次性动作（视口用 nonce 侦听，避免面板直接持有 three 对象）──
  /** 递增一次 = 请求重置视角（回到当前相机机位预设）。 */
  const resetViewNonce = ref(0)
  /** 递增一次 = 请求把当前画布保存为 PNG 截图。 */
  const screenshotNonce = ref(0)
  const frameSelectionNonce = ref(0)
  const presetRequest = ref<RenderPresetRequest | null>(null)
  const presets = ref({ camera: 'corner', environment: 'minimal', quality: 'medium', time: 'day', view: 'editor' })
  const sectionEnabled = ref(false)
  const sectionHeight = ref(3.5)

  function requestFrameSelection() { frameSelectionNonce.value += 1 }
  function requestPreset(request: RenderPresetRequest) { presetRequest.value = { ...request } }

  // ── 渲染统计（视口渲染循环写入，面板只读）──
  const stats = ref<RenderStats>(emptyStats())

  function requestResetView() {
    resetViewNonce.value += 1
  }

  function requestScreenshot() {
    screenshotNonce.value += 1
  }

  return {
    collapsed,
    showEdges,
    showGrid,
    waterAnimated,
    autoRotate,
    autoRotateSpeed,
    resetViewNonce,
    screenshotNonce,
    frameSelectionNonce,
    presetRequest,
    presets,
    sectionEnabled,
    sectionHeight,
    requestFrameSelection,
    requestPreset,
    stats,
    requestResetView,
    requestScreenshot,
  }
})
