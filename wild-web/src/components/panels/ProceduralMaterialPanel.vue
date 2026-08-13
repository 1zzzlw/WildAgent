<template>
  <details class="procedural-panel">
    <summary>
      <span>
        <strong>无图片程序化材质</strong>
        <small>砖缝、凹凸、风化与盐碱由 Shader 实时生成</small>
      </span>
      <span class="summary-arrow">⌄</span>
    </summary>

    <div class="panel-body">
      <section>
        <div class="section-title">内置预设</div>
        <div class="preset-grid">
          <button
            v-for="preset in PROCEDURAL_BRICK_PRESETS"
            :key="preset.id"
            class="preset-card"
            type="button"
            @click="loadMaterial(preset.material, preset.id)"
          >
            <span class="preset-swatch" :style="swatchStyle(preset.material)" />
            <span><b>{{ preset.name }}</b><small>{{ preset.description }}</small></span>
          </button>
        </div>
      </section>

      <section v-if="savedMaterials.length">
        <div class="section-title">我的程序化材质</div>
        <div class="saved-list">
          <div v-for="saved in savedMaterials" :key="saved.materialName" class="saved-item">
            <button type="button" class="saved-load" @click="loadMaterial(saved.material, saved.materialName)">
              <span class="preset-swatch" :style="swatchStyle(saved.material)" />
              <span>{{ saved.materialName }}</span>
            </button>
            <button type="button" class="saved-remove" title="从本机材质库移除" @click="removeSaved(saved.materialName)">×</button>
          </div>
        </div>
      </section>

      <section class="form-section">
        <div class="section-title">材质参数</div>
        <label class="wide-field">
          <span>材质 ID</span>
          <input v-model.trim="form.materialName" type="text" maxlength="64" placeholder="brick_red_custom" />
        </label>

        <div class="form-grid">
          <label><span>砖面颜色</span><input v-model="form.baseColor" type="color" /></label>
          <label><span>砖色变化</span><input v-model="form.secondaryColor" type="color" /></label>
          <label><span>砖宽 (m)</span><input v-model.number="form.brickWidth" type="number" min="0.04" max="2" step="0.01" /></label>
          <label><span>砖高 (m)</span><input v-model.number="form.brickHeight" type="number" min="0.02" max="1" step="0.005" /></label>
          <label><span>砖缝宽 (m)</span><input v-model.number="form.mortarWidth" type="number" min="0.002" max="0.03" step="0.001" /></label>
          <label><span>砖缝凹陷 (m)</span><input v-model.number="form.mortarDepth" type="number" min="0" max="0.02" step="0.001" /></label>
          <label>
            <span>砌筑方式</span>
            <select v-model="form.bond"><option value="running">错缝</option><option value="stack">齐缝</option></select>
          </label>
          <label><span>随机种子</span><input v-model.number="form.seed" type="number" min="0" max="2147483647" step="1" /></label>
        </div>

        <div class="slider-list">
          <label><span>砖色离散 <b>{{ percent(form.colorVariation) }}</b></span><input v-model.number="form.colorVariation" type="range" min="0" max="1" step="0.01" /></label>
          <label><span>粗糙度离散 <b>{{ percent(form.roughnessVariation) }}</b></span><input v-model.number="form.roughnessVariation" type="range" min="0" max="1" step="0.01" /></label>
          <label><span>边缘磨损 <b>{{ percent(form.edgeWear) }}</b></span><input v-model.number="form.edgeWear" type="range" min="0" max="1" step="0.01" /></label>
          <label><span>整体风化 <b>{{ percent(form.weatherAmount) }}</b></span><input v-model.number="form.weatherAmount" type="range" min="0" max="1" step="0.01" /></label>
          <label><span>盐碱泛白 <b>{{ percent(form.efflorescence) }}</b></span><input v-model.number="form.efflorescence" type="range" min="0" max="1" step="0.01" /></label>
          <label><span>雨痕 <b>{{ percent(form.streaks) }}</b></span><input v-model.number="form.streaks" type="range" min="0" max="1" step="0.01" /></label>
          <label><span>墙根受潮 <b>{{ percent(form.baseDampness) }}</b></span><input v-model.number="form.baseDampness" type="range" min="0" max="1" step="0.01" /></label>
        </div>

        <label class="wide-field">
          <span>风化尺度</span>
          <input v-model.number="form.weatherScale" type="number" min="0.1" max="100" step="0.1" />
        </label>
      </section>

      <p v-if="feedback" :class="['feedback', feedbackKind]">{{ feedback }}</p>
      <button class="apply-button" type="button" :disabled="saving" @click="saveAndApply">
        {{ saving ? '正在保存…' : selectionStore.selectedIds.length ? '保存并应用到已选对象' : '保存到场景与我的材质库' }}
      </button>
      <p class="footnote">参数保存在蓝图中；“我的材质”同时保存在当前浏览器，后续项目可直接复用。</p>
    </div>
  </details>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useSceneStore } from '../../stores/sceneStore'
import { useSelectionStore } from '../../stores/selectionStore'
import type { MaterialDef } from '../../types/blueprint'
import { createPatch } from '../../wild/scenePatch'
import { createSelectedMaterialBindings } from '../../wild/materialBindings'
import {
  PROCEDURAL_BRICK_PRESETS,
  cloneMaterial,
} from '../../wild/proceduralMaterialPresets'

const STORAGE_KEY = 'wild.procedural-material-library.v1'

interface SavedMaterial {
  materialName: string
  material: MaterialDef
}

const sceneStore = useSceneStore()
const selectionStore = useSelectionStore()
const saving = ref(false)
const feedback = ref('')
const feedbackKind = ref<'success' | 'error'>('success')
const savedMaterials = ref<SavedMaterial[]>([])

const form = reactive({
  materialName: 'brick_red',
  baseColor: '#9c4a32',
  secondaryColor: '#713222',
  brickWidth: 0.24,
  brickHeight: 0.065,
  mortarWidth: 0.01,
  mortarDepth: 0.006,
  bond: 'running' as 'running' | 'stack',
  seed: 1,
  colorVariation: 0.12,
  roughnessVariation: 0.12,
  edgeWear: 0.05,
  weatherAmount: 0,
  weatherScale: 1.8,
  efflorescence: 0,
  streaks: 0,
  baseDampness: 0,
})

onMounted(() => {
  restoreSavedMaterials()
  const preset = PROCEDURAL_BRICK_PRESETS[0]
  if (preset) loadMaterial(preset.material, preset.id)
})

function percent(value: number): string {
  return `${Math.round(value * 100)}%`
}

function colorToHex(color: [number, number, number] | undefined, fallback: string): string {
  if (!color) return fallback
  return `#${color.map((channel) => Math.round(Math.min(1, Math.max(0, channel)) * 255).toString(16).padStart(2, '0')).join('')}`
}

function hexToColor(hex: string): [number, number, number] {
  const value = hex.replace('#', '')
  return [0, 2, 4].map((offset) => Number.parseInt(value.slice(offset, offset + 2), 16) / 255) as [number, number, number]
}

function loadMaterial(material: MaterialDef, materialName: string): void {
  const procedural = material.procedural
  if (!procedural || procedural.type !== 'brick') return
  form.materialName = materialName
  form.baseColor = colorToHex(material.baseColor, '#9c4a32')
  form.secondaryColor = colorToHex(procedural.secondaryColor, '#713222')
  form.brickWidth = procedural.brickSize?.[0] ?? 0.24
  form.brickHeight = procedural.brickSize?.[1] ?? 0.065
  form.mortarWidth = procedural.mortarWidth ?? 0.01
  form.mortarDepth = procedural.mortarDepth ?? 0.006
  form.bond = procedural.bond ?? 'running'
  form.seed = procedural.seed ?? 1
  form.colorVariation = procedural.colorVariation ?? 0.12
  form.roughnessVariation = procedural.roughnessVariation ?? 0.12
  form.edgeWear = procedural.edgeWear ?? 0.05
  form.weatherAmount = procedural.weathering?.amount ?? 0
  form.weatherScale = procedural.weathering?.scale ?? 1.8
  form.efflorescence = procedural.weathering?.efflorescence ?? 0
  form.streaks = procedural.weathering?.verticalStreaks ?? 0
  form.baseDampness = procedural.weathering?.baseDampness ?? 0
  feedback.value = ''
}

function buildMaterial(): MaterialDef {
  return {
    materialClass: 'standard',
    baseColor: hexToColor(form.baseColor),
    roughness: 0.82,
    metallic: 0,
    albedo: 1,
    lightingCondition: 'D65_noon',
    procedural: {
      type: 'brick',
      seed: Math.round(form.seed),
      brickSize: [form.brickWidth, form.brickHeight],
      mortarWidth: form.mortarWidth,
      mortarDepth: form.mortarDepth,
      bond: form.bond,
      secondaryColor: hexToColor(form.secondaryColor),
      colorVariation: form.colorVariation,
      roughnessVariation: form.roughnessVariation,
      edgeWear: form.edgeWear,
      weathering: {
        amount: form.weatherAmount,
        scale: form.weatherScale,
        efflorescence: form.efflorescence,
        verticalStreaks: form.streaks,
        baseDampness: form.baseDampness,
      },
    },
  }
}

function validateForm(): string | null {
  if (!form.materialName || !/^[A-Za-z0-9_-]+$/.test(form.materialName)) {
    return '材质 ID 只能包含英文字母、数字、下划线和短横线。'
  }
  const finiteFields = [form.brickWidth, form.brickHeight, form.mortarWidth, form.mortarDepth, form.seed, form.weatherScale]
  if (finiteFields.some((value) => !Number.isFinite(value))) return '请填写有效的数值参数。'
  if (form.brickWidth < 0.04 || form.brickWidth > 2 || form.brickHeight < 0.02 || form.brickHeight > 1) {
    return '砖块尺寸超出支持范围。'
  }
  if (form.mortarWidth < 0.002 || form.mortarWidth > 0.03 || form.mortarWidth >= Math.min(form.brickWidth, form.brickHeight) / 2) {
    return '砖缝宽度必须小于砖块短边的一半，并处于 0.002–0.03m。'
  }
  if (form.mortarDepth < 0 || form.mortarDepth > 0.02) return '砖缝凹陷必须处于 0–0.02m。'
  if (form.weatherScale < 0.1 || form.weatherScale > 100) return '风化尺度必须处于 0.1–100。'
  return null
}

async function saveAndApply(): Promise<void> {
  const error = validateForm()
  if (error) {
    feedbackKind.value = 'error'
    feedback.value = error
    return
  }
  const document = sceneStore.document
  if (!document) {
    feedbackKind.value = 'error'
    feedback.value = '当前还没有可编辑的蓝图。'
    return
  }

  saving.value = true
  const material = buildMaterial()
  const operations = [
    { op: 'upsert_material' as const, name: form.materialName, material },
    ...createSelectedMaterialBindings(document.blueprint, selectionStore.selectedIds, form.materialName),
  ]
  try {
    const patch = createPatch(
      document.revision,
      operations,
      'user',
      false,
      `保存程序化材质 ${form.materialName}`,
    )
    const applied = await sceneStore.applyPatch(patch)
    if (!applied) throw new Error('材质补丁未应用，请查看校验面板')
    rememberMaterial(form.materialName, material)
    feedbackKind.value = 'success'
    feedback.value = selectionStore.selectedIds.length
      ? `已保存并应用到 ${selectionStore.selectedIds.length} 个已选对象。`
      : '已保存到当前场景与我的材质库。'
  } catch (cause) {
    feedbackKind.value = 'error'
    feedback.value = cause instanceof Error ? cause.message : '保存程序化材质失败。'
  } finally {
    saving.value = false
  }
}

function rememberMaterial(materialName: string, material: MaterialDef): void {
  const next = savedMaterials.value.filter((entry) => entry.materialName !== materialName)
  next.unshift({ materialName, material: cloneMaterial(material) })
  savedMaterials.value = next.slice(0, 24)
  persistSavedMaterials()
}

function removeSaved(materialName: string): void {
  savedMaterials.value = savedMaterials.value.filter((entry) => entry.materialName !== materialName)
  persistSavedMaterials()
}

function restoreSavedMaterials(): void {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    const parsed = raw ? JSON.parse(raw) : []
    if (!Array.isArray(parsed)) return
    savedMaterials.value = parsed.filter(
      (entry): entry is SavedMaterial => Boolean(entry && typeof entry.materialName === 'string' && entry.material?.procedural?.type === 'brick'),
    )
  } catch {
    savedMaterials.value = []
  }
}

function persistSavedMaterials(): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(savedMaterials.value))
  } catch {
    feedbackKind.value = 'error'
    feedback.value = '材质已写入场景，但浏览器未允许保存到本机材质库。'
  }
}

function swatchStyle(material: MaterialDef): Record<string, string> {
  const first = colorToHex(material.baseColor, '#9c4a32')
  const second = material.procedural?.type === 'brick'
    ? colorToHex(material.procedural.secondaryColor, '#713222')
    : '#713222'
  return { background: `linear-gradient(135deg, ${first} 0 48%, #c8bca9 49% 54%, ${second} 55% 100%)` }
}
</script>

<style scoped>
.procedural-panel {
  margin: 0 0 12px;
  border: 1px solid rgba(239, 176, 95, 0.22);
  border-radius: 10px;
  background: linear-gradient(145deg, rgba(66, 42, 29, 0.34), rgba(24, 27, 32, 0.9));
  color: #e8eaed;
}

summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 14px;
  cursor: pointer;
  list-style: none;
  user-select: none;
}

summary::-webkit-details-marker { display: none; }
summary > span:first-child { display: grid; gap: 3px; }
summary strong { font-size: 13px; font-weight: 650; color: #f4d5b2; }
summary small, .preset-card small { color: #989da6; font-size: 11px; line-height: 1.35; }
.summary-arrow { color: #d79a5b; transition: transform 160ms ease; }
.procedural-panel[open] .summary-arrow { transform: rotate(180deg); }

.panel-body { padding: 0 12px 12px; border-top: 1px solid rgba(255, 255, 255, 0.06); }
section { padding-top: 12px; }
.section-title { margin-bottom: 8px; color: #c3c7cf; font-size: 11px; font-weight: 650; letter-spacing: .04em; }
.preset-grid { display: grid; gap: 7px; }
.preset-card, .saved-load {
  display: flex;
  align-items: center;
  gap: 9px;
  width: 100%;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 7px;
  background: rgba(255, 255, 255, 0.035);
  color: #e7e8eb;
  text-align: left;
  cursor: pointer;
}
.preset-card { padding: 8px; }
.preset-card > span:last-child { display: grid; gap: 2px; }
.preset-card:hover, .saved-load:hover { border-color: rgba(222, 155, 85, 0.55); background: rgba(222, 155, 85, 0.08); }
.preset-swatch { flex: 0 0 30px; width: 30px; height: 30px; border-radius: 5px; box-shadow: inset 0 0 0 1px rgba(255, 255, 255, .16); }

.saved-list { display: grid; gap: 5px; }
.saved-item { display: grid; grid-template-columns: 1fr 28px; gap: 5px; }
.saved-load { min-width: 0; padding: 5px 7px; }
.saved-load .preset-swatch { flex-basis: 22px; width: 22px; height: 22px; }
.saved-load span:last-child { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.saved-remove { border: 0; border-radius: 6px; background: rgba(255, 255, 255, .05); color: #8e949d; cursor: pointer; }
.saved-remove:hover { color: #ff9e9e; background: rgba(255, 90, 90, .1); }

.form-section { display: grid; gap: 9px; }
.form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 7px; }
label { display: grid; gap: 4px; min-width: 0; color: #9fa4ad; font-size: 11px; }
label > span { display: flex; justify-content: space-between; gap: 8px; }
label b { color: #d9b88f; font-weight: 500; }
input, select {
  min-width: 0;
  height: 28px;
  box-sizing: border-box;
  border: 1px solid rgba(255, 255, 255, .1);
  border-radius: 5px;
  outline: none;
  background: #1c2026;
  color: #e7e9ed;
  padding: 0 7px;
  font: inherit;
}
input:focus, select:focus { border-color: rgba(219, 152, 83, .72); }
input[type='color'] { width: 100%; padding: 2px 4px; cursor: pointer; }
input[type='range'] { width: 100%; height: 16px; padding: 0; accent-color: #c98245; }
.wide-field { grid-column: 1 / -1; }
.slider-list { display: grid; gap: 6px; margin-top: 2px; }
.feedback { margin: 10px 0 0; padding: 7px 9px; border-radius: 6px; font-size: 11px; line-height: 1.4; }
.feedback.success { color: #a9dfbd; background: rgba(52, 168, 91, .1); }
.feedback.error { color: #ffb4b4; background: rgba(225, 74, 74, .1); }
.apply-button {
  width: 100%;
  margin-top: 10px;
  padding: 8px 10px;
  border: 1px solid rgba(226, 160, 91, .48);
  border-radius: 7px;
  background: linear-gradient(180deg, #a85e2e, #82441f);
  color: #fff4e8;
  font-size: 12px;
  font-weight: 650;
  cursor: pointer;
}
.apply-button:hover:not(:disabled) { filter: brightness(1.1); }
.apply-button:disabled { opacity: .55; cursor: wait; }
.footnote { margin: 7px 2px 0; color: #777d86; font-size: 10px; line-height: 1.45; }
</style>
