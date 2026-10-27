<template>
  <div class="material-workspace">
    <div class="material-tabs"><button type="button" :class="{ active: tab === 'scene' }" @click="tab = 'scene'">场景材质</button><button type="button" :class="{ active: tab === 'library' }" @click="tab = 'library'">材质与素材库</button></div>
    <section v-show="tab === 'scene'" class="scene-materials">
      <details class="builtin-materials" open>
        <summary>内置材质</summary>
        <div class="swatch-grid"><button v-for="preset in SURFACE_MATERIAL_PRESETS" :key="preset.id" type="button"
          class="swatch" :title="preset.description" :disabled="!scene.document || scene.isReconstructing" @click="addPreset(preset)">
          <i :style="{ backgroundColor: colorHex(preset.material.baseColor), backgroundImage: previews[preset.id] ? `url(${previews[preset.id]})` : undefined, backgroundSize: 'cover', backgroundPosition: 'center', height: '64px' }"></i><span>{{ preset.name }}</span>
        </button></div>
        <p class="material-hint">点击加入场景；有选中构件时同时应用到匹配的部位。</p>
      </details>
      <input v-model="query" type="search" placeholder="搜索场景材质" aria-label="搜索场景材质" />
      <div class="swatch-grid"><button v-for="[name,material] in materials" :key="name" type="button" :class="['swatch', { selected: active === name }]" :title="name" @click="active = name"><i :style="{ background: colorHex(material.baseColor) }"></i><span>{{ name }}</span></button></div>
      <p v-if="!materials.length" class="material-hint">当前没有匹配的场景材质，导入建筑或从素材库添加。</p>
      <div v-if="selected" class="material-editor">
        <h2>{{ active }}</h2>
        <label>基础颜色<input type="color" aria-label="材质基础颜色" :value="colorHex(selected.baseColor)" @change="changeColor" /></label>
        <label>粗糙度<input type="number" aria-label="材质粗糙度" min="0" max="1" step="0.05" :value="selected.roughness ?? .8" @change="changeNumber('roughness', $event)" /></label>
        <label>金属度<input type="number" aria-label="材质金属度" min="0" max="1" step="0.05" :value="selected.metallic ?? 0" @change="changeNumber('metallic', $event)" /></label>
        <button type="button" class="apply-material" :disabled="!selection.hasSelection || scene.isReconstructing" @click="applySelected">应用到选中构件（{{ selection.selectedIds.length }}）</button>
        <p class="material-hint">材质修改支持撤销；保存后与建筑一起存储。</p>
      </div>
    </section>
    <PBRAssetPanel v-show="tab === 'library'" />
  </div>
</template>
<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { useSceneStore } from '../../stores/sceneStore'
import { useSelectionStore } from '../../stores/selectionStore'
import { createPatch } from '../../wild/scenePatch'
import { createSelectedMaterialBindings } from '../../wild/materialBindings'
import { SURFACE_MATERIAL_PRESETS } from '../../wild/surfaceMaterialPresets'
import type { MaterialDef } from '../../types/blueprint'
import PBRAssetPanel from './PBRAssetPanel.vue'
import { getMaterialThumbnails } from '../../renderer/materialThumbnails'
const previews = ref<Record<string, string>>({})
onMounted(() => { void getMaterialThumbnails().then(value => { previews.value = value }).catch(error => console.warn('材质预览生成失败', error)) })
const scene = useSceneStore()
const selection = useSelectionStore()
const tab = ref('scene')
const query = ref('')
const active = ref('')
const materials = computed(() => Object.entries(scene.document?.blueprint.materials || {}).filter(([name]) => name.toLowerCase().includes(query.value.toLowerCase())))
const selected = computed(() => scene.document?.blueprint.materials?.[active.value])
async function addPreset(preset: typeof SURFACE_MATERIAL_PRESETS[number]) {
  if (!scene.document || scene.isReconstructing) return
  let name = preset.id
  let suffix = 2
  while (scene.document.blueprint.materials?.[name]
    && JSON.stringify(scene.document.blueprint.materials[name]) !== JSON.stringify(preset.material)) name = `${preset.id}_${suffix++}`
  const material = JSON.parse(JSON.stringify(preset.material)) as MaterialDef
  const blueprint = scene.document.blueprint
  const bindings = createSelectedMaterialBindings(blueprint, selection.selectedIds, name, material)
  if (await scene.applyPatch(createPatch(scene.document.revision,
    [{ op: 'upsert_material', name, material }, ...bindings], 'user', false, '添加' + preset.name))) active.value = name
}
watch(() => scene.document?.id, () => { active.value = Object.keys(scene.document?.blueprint.materials || {})[0] || '' }, { immediate: true })
function colorHex(value: unknown) {
  const rgb = Array.isArray(value) ? value : [.5, .5, .5]
  return '#' + rgb.slice(0,3).map(v => Math.round(Math.max(0,Math.min(1,Number(v)))*255).toString(16).padStart(2,'0')).join('')
}
async function update(changes: Partial<MaterialDef>) {
  if (!scene.document || !selected.value) return
  await scene.applyPatch(createPatch(scene.document.revision, [{ op: 'upsert_material', name: active.value, material: { ...selected.value, ...changes } }], 'user', false, '修改材质 ' + active.value))
}
function changeColor(event: Event) {
  const hex = (event.target as HTMLInputElement).value
  void update({ baseColor: [1,3,5].map(i => parseInt(hex.slice(i,i+2),16)/255) as [number,number,number] })
}
function changeNumber(key: 'roughness' | 'metallic', event: Event) {
  const value = Number((event.target as HTMLInputElement).value)
  if (Number.isFinite(value)) void update({ [key]: Math.min(1,Math.max(0,value)) })
}
async function applySelected() {
  if (!scene.document) return
  const operations = createSelectedMaterialBindings(scene.document.blueprint, selection.selectedIds, active.value)
  if (operations.length && await scene.applyPatch(createPatch(scene.document.revision, operations, 'user', false, '应用材质 ' + active.value))) ElMessage.success('材质已应用到选中构件')
}
</script>
<style scoped>
.material-tabs{display:flex;padding:12px;gap:7px;border-bottom:1px solid var(--studio-border)}.material-tabs button{flex:1;padding:8px;border:1px solid var(--studio-border);border-radius:7px;background:transparent;color:var(--studio-muted);font-size:11px;cursor:pointer}.material-tabs button.active{color:var(--studio-text);background:var(--studio-hover);border-color:var(--studio-border)}.scene-materials{padding:16px}.scene-materials>input{width:100%;padding:9px 10px;background:var(--studio-input);color:var(--studio-text);border:1px solid var(--studio-border);border-radius:7px;font-size:11px}.swatch-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:9px;margin:16px 0}.swatch{min-width:0;padding:6px;border:1px solid var(--studio-border);border-radius:8px;background:var(--studio-hover);color:var(--studio-muted);text-align:left;cursor:pointer}.swatch.selected{border-color:var(--studio-border);color:var(--studio-text)}.swatch i{display:block;height:40px;border-radius:4px;box-shadow:inset 0 -14px 18px rgba(41, 76, 61, 0.12)}.swatch span{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:9px;padding:7px 1px 1px}.material-editor{border-top:1px solid var(--studio-border);padding-top:15px}.material-editor h2{font-size:12px;color:var(--studio-text);margin-bottom:12px;overflow-wrap:anywhere}.material-editor label{display:flex;justify-content:space-between;align-items:center;gap:10px;margin-bottom:12px;color:var(--studio-muted);font-size:11px}.material-editor input{width:110px;height:30px;color:var(--studio-text);background:var(--studio-input);border:1px solid var(--studio-border);border-radius:5px;padding:4px}.apply-material{width:100%;padding:10px;border-radius:7px;border:1px solid var(--studio-border);color:var(--studio-text);background:var(--studio-hover);cursor:pointer;font-size:11px}.apply-material:disabled{opacity:.4;cursor:not-allowed}.material-hint{font-size:10px;line-height:1.8;color:var(--studio-muted);margin-top:10px}
</style>
