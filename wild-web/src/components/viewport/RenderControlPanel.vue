<template>
  <div class="render-control-root">
    <!-- 收起态：一个小圆钮，悬浮在工具栏下方，几乎不占画布空间 -->
    <button v-if="store.collapsed" type="button" class="rc-fab" :class="fpsTier"
      :title="`展开渲染面板（FPS ${store.stats.fps}）`" aria-label="展开渲染面板" @click="store.collapsed = false">
      <span class="rc-fab-icon" aria-hidden="true">⚙</span>
      <span class="rc-fab-fps">{{ store.stats.fps }}</span>
    </button>

    <!-- 展开态：毛玻璃控制面板 -->
    <section v-else class="rc-panel" role="region" aria-label="渲染控制面板">
      <header class="rc-header">
        <span class="rc-title">渲染面板</span>
        <button type="button" class="rc-collapse" title="收起面板" aria-label="收起渲染面板" @click="store.collapsed = true">
          <span aria-hidden="true">−</span>
        </button>
      </header>

      <!-- 渲染信息 -->
      <div class="rc-section">
        <div class="rc-section-title">渲染信息</div>
        <div class="rc-stats">
          <div class="rc-stat">
            <span class="rc-stat-label">帧率</span>
            <span class="rc-stat-value" :class="fpsTier">{{ store.stats.fps }} FPS</span>
          </div>
          <div class="rc-stat">
            <span class="rc-stat-label">绘制调用</span>
            <span class="rc-stat-value">{{ store.stats.drawCalls }}</span>
          </div>
          <div class="rc-stat">
            <span class="rc-stat-label">三角面</span>
            <span class="rc-stat-value">{{ formatCount(store.stats.triangles) }}</span>
          </div>
          <div class="rc-stat">
            <span class="rc-stat-label">几何体</span>
            <span class="rc-stat-value">{{ store.stats.geometries }}</span>
          </div>
          <div class="rc-stat">
            <span class="rc-stat-label">纹理</span>
            <span class="rc-stat-value">{{ store.stats.textures }}</span>
          </div>
          <div class="rc-stat rc-stat-wide">
            <span class="rc-stat-label">分辨率</span>
            <span class="rc-stat-value">{{ resolutionLabel }}</span>
          </div>
        </div>
      </div>

      <!-- 显示开关 -->
      <div class="rc-section">
        <div class="rc-section-title">显示</div>
        <label class="rc-toggle">
          <span>建筑线条</span>
          <input v-model="store.showEdges" type="checkbox" />
          <span class="rc-switch" aria-hidden="true"></span>
        </label>
        <label class="rc-toggle">
          <span>网格地面</span>
          <input v-model="store.showGrid" type="checkbox" />
          <span class="rc-switch" aria-hidden="true"></span>
        </label>
        <label class="rc-toggle">
          <span>自动旋转</span>
          <input v-model="store.autoRotate" type="checkbox" />
          <span class="rc-switch" aria-hidden="true"></span>
        </label>
        <div v-if="store.autoRotate" class="rc-slider-row">
          <span class="rc-slider-label">速度</span>
          <input v-model.number="store.autoRotateSpeed" type="range" min="0.2" max="4" step="0.2" class="rc-slider" />
          <span class="rc-slider-value">{{ store.autoRotateSpeed.toFixed(1) }}</span>
        </div>
      </div>

      <!-- 操作 -->
      <div class="rc-section">
        <div class="rc-section-title">操作</div>
        <div class="rc-actions">
          <button type="button" class="rc-button" @click="store.requestResetView()">
            <span aria-hidden="true">⌖</span> 重置视角
          </button>
          <button type="button" class="rc-button" @click="store.requestScreenshot()">
            <span aria-hidden="true">⤓</span> 保存截图
          </button>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRenderPanelStore } from '../../stores/renderPanelStore'

/**
 * 渲染控制面板（毛玻璃、可收起）。
 *
 * 只读 store 里的渲染统计、只写开关；three.js 的执行全部在
 * CanvasViewport 里（保持"面板无 three 依赖"的边界）。
 */
const store = useRenderPanelStore()

const fpsTier = computed(() =>
  store.stats.fps >= 50 ? 'good' : store.stats.fps >= 30 ? 'ok' : 'bad',
)

const resolutionLabel = computed(() => {
  const { renderWidth, renderHeight, pixelRatio } = store.stats
  if (!renderWidth || !renderHeight) return '—'
  return `${renderWidth}×${renderHeight} @${pixelRatio.toFixed(2)}x`
})

function formatCount(value: number): string {
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(2)}M`
  if (value >= 1_000) return `${(value / 1_000).toFixed(1)}k`
  return String(value)
}
</script>

<style scoped>
.render-control-root {
  position: absolute;
  top: 56px;
  right: 12px;
  z-index: 30;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  pointer-events: none;
  /* 根节点不拦截画布事件；只有面板/按钮自身接管 */
}

/* ── 收起态小圆钮 ── */
.rc-fab {
  pointer-events: auto;
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 6px 10px;
  border: 1px solid rgba(255, 255, 255, 0.22);
  border-radius: 999px;
  background: rgba(18, 24, 32, 0.42);
  backdrop-filter: blur(12px) saturate(1.4);
  -webkit-backdrop-filter: blur(12px) saturate(1.4);
  color: #e8eef4;
  font-size: 12px;
  font-family: monospace;
  cursor: pointer;
  transition: background 0.2s ease, transform 0.15s ease;
}

.rc-fab:hover {
  background: rgba(30, 40, 52, 0.6);
  transform: translateY(-1px);
}

.rc-fab-icon {
  font-size: 13px;
  line-height: 1;
}

.rc-fab-fps.good {
  color: #7ee2a0;
}

.rc-fab-fps.ok {
  color: #f2d377;
}

.rc-fab-fps.bad {
  color: #f28b82;
}

/* ── 毛玻璃面板 ── */
.rc-panel {
  pointer-events: auto;
  width: 232px;
  padding: 12px 14px 14px;
  border: 1px solid rgba(255, 255, 255, 0.16);
  border-radius: 14px;
  background: rgba(18, 24, 32, 0.45);
  backdrop-filter: blur(16px) saturate(1.5);
  -webkit-backdrop-filter: blur(16px) saturate(1.5);
  box-shadow: 0 8px 28px rgba(0, 0, 0, 0.28);
  color: #e8eef4;
  font-size: 12px;
  user-select: none;
}

.rc-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.rc-title {
  font-size: 13px;
  font-weight: 600;
  letter-spacing: 0.04em;
}

.rc-collapse {
  width: 22px;
  height: 22px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid rgba(255, 255, 255, 0.18);
  border-radius: 7px;
  background: rgba(255, 255, 255, 0.08);
  color: #e8eef4;
  font-size: 14px;
  line-height: 1;
  cursor: pointer;
  transition: background 0.15s ease;
}

.rc-collapse:hover {
  background: rgba(255, 255, 255, 0.16);
}

.rc-section {
  padding: 8px 0;
  border-top: 1px solid rgba(255, 255, 255, 0.1);
}

.rc-section:first-of-type {
  border-top: none;
}

.rc-section-title {
  margin-bottom: 6px;
  font-size: 11px;
  font-weight: 600;
  color: rgba(232, 238, 244, 0.6);
  letter-spacing: 0.08em;
}

/* ── 渲染信息 ── */
.rc-stats {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 4px 12px;
}

.rc-stat {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
}

/* 分辨率一行太长（如 812×713 @1.50x），独占整行避免挤压换行 */
.rc-stat-wide {
  grid-column: 1 / -1;
}

.rc-stat-label {
  color: rgba(232, 238, 244, 0.62);
  flex-shrink: 0;
}

.rc-stat-value {
  font-family: monospace;
  font-size: 12px;
  white-space: nowrap;
}

.rc-stat-value.good {
  color: #7ee2a0;
}

.rc-stat-value.ok {
  color: #f2d377;
}

.rc-stat-value.bad {
  color: #f28b82;
}

/* ── 开关 ── */
.rc-toggle {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 3px 0;
  cursor: pointer;
}

.rc-toggle input {
  position: absolute;
  opacity: 0;
  width: 0;
  height: 0;
}

.rc-switch {
  position: relative;
  width: 30px;
  height: 16px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.18);
  transition: background 0.18s ease;
  flex-shrink: 0;
}

.rc-switch::after {
  content: '';
  position: absolute;
  top: 2px;
  left: 2px;
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: #e8eef4;
  transition: transform 0.18s ease;
}

.rc-toggle input:checked+.rc-switch {
  background: rgba(96, 205, 155, 0.75);
}

.rc-toggle input:checked+.rc-switch::after {
  transform: translateX(14px);
}

.rc-toggle input:focus-visible+.rc-switch {
  outline: 1px solid rgba(125, 211, 252, 0.8);
  outline-offset: 1px;
}

/* ── 速度滑杆 ── */
.rc-slider-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 4px;
}

.rc-slider-label {
  color: rgba(232, 238, 244, 0.62);
}

.rc-slider {
  flex: 1;
  accent-color: #60cd9b;
}

.rc-slider-value {
  font-family: monospace;
  min-width: 26px;
  text-align: right;
}

/* ── 操作按钮 ── */
.rc-actions {
  display: flex;
  gap: 8px;
}

.rc-button {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  padding: 6px 8px;
  border: 1px solid rgba(255, 255, 255, 0.18);
  border-radius: 9px;
  background: rgba(255, 255, 255, 0.08);
  color: #e8eef4;
  font-size: 12px;
  cursor: pointer;
  transition: background 0.15s ease;
}

.rc-button:hover {
  background: rgba(255, 255, 255, 0.16);
}

.rc-button:active {
  background: rgba(255, 255, 255, 0.22);
}
</style>
