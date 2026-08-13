<template>
  <div class="asset-panel">
    <div class="panel-header">PBR 素材入库</div>
    <div class="panel-body">
      <div class="hint">
        只需一张颜色图片即可入库；法线、粗糙度等专业贴图均为可选增强。
        图片保存到资产目录，WILD 仅记录 URL、哈希和授权信息，不写入 Base64。
        Ctrl + 左键可多选；左键点击视口空白处可取消选择。
      </div>

      <label>素材名称</label>
      <el-input v-model="form.name" size="small" placeholder="例如：浅灰石材" />
      <label>材质 ID</label>
      <el-input v-model="form.materialName" size="small" placeholder="例如：stone_light_pbr" />
      <label>授权信息</label>
      <el-input v-model="form.license" size="small" placeholder="例如：CC0 / User supplied" />
      <label>材质类别</label>
      <el-select v-model="form.materialClass" size="small">
        <el-option v-for="option in materialClasses" :key="option.value" :label="option.label" :value="option.value" />
      </el-select>
      <label>检索标签</label>
      <el-input v-model="form.tags" size="small" placeholder="stone, warm_gray, seamless" />
      <label>推荐角色</label>
      <el-input v-model="form.recommendedRoles" size="small" placeholder="facade_primary, roof" />

      <div class="number-row">
        <div>
          <label>粗糙度</label>
          <el-input-number v-model="form.roughness" :min="0" :max="1" :step="0.05" size="small" />
        </div>
        <div>
          <label>金属度</label>
          <el-input-number v-model="form.metallic" :min="0" :max="1" :step="0.05" size="small" />
        </div>
      </div>

      <div class="color-row">
        <div>
          <label>颜色染色</label>
          <div class="color-control">
            <el-color-picker v-model="form.colorTint" size="small" />
            <code>{{ form.colorTint.toUpperCase() }}</code>
          </div>
        </div>
        <div class="parameter-help">与图片颜色相乘；白色保持原图，适合制作同纹理的不同色系。</div>
      </div>

      <div class="number-row">
        <div>
          <label>真实宽度（米）</label>
          <el-input-number v-model="form.realWidth" :min="0.01" :max="1000" :step="0.1" size="small" />
        </div>
        <div>
          <label>真实高度（米）</label>
          <el-input-number v-model="form.realHeight" :min="0.01" :max="1000" :step="0.1" size="small" />
        </div>
      </div>

      <div class="number-row">
        <div>
          <label>UV 横向重复</label>
          <el-input-number v-model="form.uvScaleX" :min="0.01" :max="64" :step="0.25" size="small" />
        </div>
        <div>
          <label>UV 纵向重复</label>
          <el-input-number v-model="form.uvScaleY" :min="0.01" :max="64" :step="0.25" size="small" />
        </div>
      </div>
      <label>法线强度 · {{ form.normalScale.toFixed(1) }}</label>
      <el-slider v-model="form.normalScale" :min="0" :max="4" :step="0.1" show-stops />
      <div class="parameter-help">需要法线贴图；0 为关闭，1 为物理原始强度，超过 1 会强化凹凸。</div>

      <div class="file-list">
        <label class="file-field">
          <span>颜色图片（Base Color）<b> *</b></span>
          <input type="file" accept="image/png,image/jpeg,image/webp" @change="setFile('baseColor', $event)" />
        </label>
        <details>
          <summary>可选专业贴图</summary>
          <label v-for="field in optionalFileFields" :key="field.key" class="file-field optional-file">
            <span>{{ field.label }}</span>
            <input type="file" accept="image/png,image/jpeg,image/webp" @change="setFile(field.key, $event)" />
          </label>
        </details>
      </div>

      <div class="selection-tip">入库后会自动应用到全部已选构件。</div>
      <div v-if="selectionStore.hasSelection" class="selection-tip">
        已选 {{ selectionStore.selectedIds.length }} 项：{{ selectionStore.selectedIds.join('、') }}
      </div>

      <el-button
        type="primary"
        size="small"
        :loading="assetStore.loading"
        :disabled="!canSubmit"
        @click="registerAndApply"
      >
        入库并写入场景
      </el-button>

      <div v-if="message" :class="['message', messageType]">{{ message }}</div>
      <div v-if="assetStore.error" class="message error">{{ assetStore.error }}</div>

      <div class="asset-list-header">
        <span>本地资产 · {{ assetStore.assets.length }}</span>
        <button @click="assetStore.refresh">刷新</button>
      </div>
      <el-input v-model="assetSearch" size="small" clearable placeholder="按名称、类别或标签搜索" />
      <div v-if="assetStore.assets.length === 0" class="empty">尚无 PBR 资产</div>
      <div v-else-if="filteredAssets.length === 0" class="empty">没有匹配的 PBR 资产</div>
      <div v-for="asset in filteredAssets" :key="asset.assetId" class="asset-item">
        <img :src="asset.maps.baseColor.uri" :alt="asset.name" loading="lazy" />
        <div class="asset-info">
          <div class="asset-title">{{ asset.name }}</div>
          <code>{{ asset.assetId }}</code>
          <div class="asset-meta">
            {{ asset.classification?.materialClass || 'other' }} ·
            {{ Object.keys(asset.maps).join(' / ') }} · {{ asset.license }}
          </div>
          <div class="asset-parameters">
            色彩 {{ tintToHex(asset.defaults?.baseColorTint) }} ·
            粗糙 {{ formatNumber(asset.defaults?.roughness, 0.8) }} ·
            金属 {{ formatNumber(asset.defaults?.metallic, 0) }} ·
            法线 {{ formatNumber(asset.defaults?.normalScale, 1) }}
          </div>
          <div v-if="asset.classification?.tags?.length" class="asset-tags">
            {{ asset.classification.tags.join(' · ') }}
          </div>
          <div class="asset-actions">
            <el-button
              type="primary"
              size="small"
              plain
              :disabled="!selectionStore.hasSelection || assetStore.loading"
              @click="applyExistingAsset(asset)"
            >
              应用到已选 {{ selectionStore.selectedIds.length || '' }}
            </el-button>
            <el-button
              type="danger"
              size="small"
              text
              :disabled="assetStore.loading"
              @click="removeAsset(asset)"
            >
              从素材库移除
            </el-button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import type { MaterialDef, PBRTextureSetAsset } from '../../types/blueprint'
import type { SceneOperation } from '../../types/scenePatch'
import { useAssetStore } from '../../stores/assetStore'
import { useSceneStore } from '../../stores/sceneStore'
import { useSelectionStore } from '../../stores/selectionStore'
import { createPatch } from '../../wild/scenePatch'

type FileKey = 'baseColor' | 'normal' | 'roughness' | 'metalness' | 'ambientOcclusion'

const assetStore = useAssetStore()
const sceneStore = useSceneStore()
const selectionStore = useSelectionStore()
const baseColorFile = ref<File | null>(null)
const optionalFiles = reactive<Partial<Record<FileKey, File>>>({})
const message = ref('')
const messageType = ref<'success' | 'error'>('success')
const assetSearch = ref('')
const form = reactive({
  name: '',
  materialName: '',
  license: 'User supplied',
  roughness: 0.8,
  metallic: 0,
  colorTint: '#ffffff',
  normalScale: 1,
  uvScaleX: 1,
  uvScaleY: 1,
  realWidth: 1,
  realHeight: 1,
  materialClass: 'other',
  tags: '',
  recommendedRoles: '',
})

const materialClasses = [
  { value: 'stone', label: '石材' },
  { value: 'concrete', label: '混凝土' },
  { value: 'brick', label: '砖' },
  { value: 'wood', label: '木材' },
  { value: 'metal', label: '金属' },
  { value: 'plaster', label: '涂料 / 抹灰' },
  { value: 'tile', label: '瓷砖' },
  { value: 'fabric', label: '织物' },
  { value: 'other', label: '其他' },
]

const optionalFileFields: Array<{ key: Exclude<FileKey, 'baseColor'>; label: string }> = [
  { key: 'normal', label: 'Normal' },
  { key: 'roughness', label: 'Roughness' },
  { key: 'metalness', label: 'Metalness' },
  { key: 'ambientOcclusion', label: 'Ambient Occlusion' },
]

const canSubmit = computed(() => Boolean(
  sceneStore.document
  && form.name.trim()
  && form.materialName.trim()
  && form.license.trim()
  && baseColorFile.value
))

const filteredAssets = computed(() => {
  const query = assetSearch.value.trim().toLowerCase()
  if (!query) return assetStore.assets
  return assetStore.assets.filter(asset => [
    asset.name,
    asset.assetId,
    asset.classification?.materialClass,
    ...(asset.classification?.tags || []),
    ...(asset.classification?.recommendedRoles || []),
  ].some(value => String(value || '').toLowerCase().includes(query)))
})

onMounted(() => assetStore.refresh())

function setFile(key: FileKey, event: Event): void {
  const file = (event.target as HTMLInputElement).files?.[0]
  if (key === 'baseColor') baseColorFile.value = file || null
  else if (file) optionalFiles[key] = file
  else delete optionalFiles[key]
}

function selectedBindings(materialName: string): SceneOperation[] {
  if (!sceneStore.document) return []
  const selectedIds = new Set(selectionStore.selectedIds)
  const operations: SceneOperation[] = []
  for (const element of sceneStore.document.blueprint.geometry.elements) {
    if (selectedIds.has(element.id)) {
      operations.push({ op: 'update_element', id: element.id, changes: { material: materialName } })
    }
  }
  for (const component of sceneStore.document.blueprint.geometry.components || []) {
    if (!selectedIds.has(component.id)) continue
    const materialField = component.type === 'door'
      ? 'leafMaterial'
      : component.type === 'window' || component.type === 'bay_window'
        ? 'frameMaterial'
        : component.type === 'light'
          ? 'shadeMaterial'
          : 'material'
    operations.push({
      op: 'update_component',
      id: component.id,
      changes: { [materialField]: materialName },
    })
  }
  return operations
}

async function registerAndApply(): Promise<void> {
  if (!sceneStore.document || !baseColorFile.value) return
  message.value = ''
  const result = await assetStore.registerPbr({
    name: form.name.trim(),
    materialName: form.materialName.trim(),
    license: form.license.trim(),
    baseRevision: sceneStore.document.revision,
    roughness: form.roughness,
    metallic: form.metallic,
    baseColorTint: hexToTint(form.colorTint),
    normalScale: form.normalScale,
    uvScale: [form.uvScaleX, form.uvScaleY],
    materialClass: form.materialClass,
    tags: splitTerms(form.tags),
    recommendedRoles: splitTerms(form.recommendedRoles),
    realWorldSizeMeters: [form.realWidth, form.realHeight],
    files: {
      baseColor: baseColorFile.value,
      normal: optionalFiles.normal,
      roughness: optionalFiles.roughness,
      metalness: optionalFiles.metalness,
      ambientOcclusion: optionalFiles.ambientOcclusion,
    },
  })
  if (!result) return
  const bindings = selectedBindings(form.materialName.trim())
  result.patch.operations.push(...bindings)
  const applied = await sceneStore.applyPatch(result.patch)
  messageType.value = applied ? 'success' : 'error'
  message.value = applied
    ? bindings.length > 0
      ? `已入库 ${result.asset.assetId} 并应用到 ${bindings.length} 个已选构件`
      : `已入库 ${result.asset.assetId}，可随时从素材库复用`
    : `资产 ${result.asset.assetId} 已入库，但场景补丁未通过，请查看校验面板`
}

async function applyExistingAsset(asset: PBRTextureSetAsset): Promise<void> {
  if (!sceneStore.document) return
  const materialName = asset.assetId
  const bindings = selectedBindings(materialName)
  if (bindings.length === 0) {
    messageType.value = 'error'
    message.value = '请先在视口或场景树中选择要应用素材的构件'
    return
  }
  const defaults = asset.defaults || {}
  const material: MaterialDef = {
    baseColor: defaults.baseColorTint ?? [1, 1, 1],
    roughness: defaults.roughness ?? 0.8,
    metallic: defaults.metallic ?? 0,
    albedo: 1,
    lightingCondition: 'D65_noon',
    textureSet: asset.assetId,
    normalScale: defaults.normalScale ?? 1,
    uvScale: defaults.uvScale ?? [1, 1],
  }
  const patch = createPatch(sceneStore.document.revision, [
    { op: 'upsert_asset', asset_id: asset.assetId, asset },
    { op: 'upsert_material', name: materialName, material },
    ...bindings,
  ], 'user', false, `复用 PBR 素材 ${asset.name}`)
  const applied = await sceneStore.applyPatch(patch)
  messageType.value = applied ? 'success' : 'error'
  message.value = applied
    ? `已将 ${asset.name} 应用到 ${bindings.length} 个已选构件`
    : `素材 ${asset.name} 未能应用，请查看校验面板`
}

async function removeAsset(asset: PBRTextureSetAsset): Promise<void> {
  try {
    await ElMessageBox.confirm(
      `从素材库移除“${asset.name}”？已有场景仍可继续使用它。`,
      '移除素材',
      { confirmButtonText: '移除', cancelButtonText: '取消', type: 'warning' },
    )
  } catch {
    return
  }
  const removed = await assetStore.removeFromLibrary(asset.assetId)
  messageType.value = removed ? 'success' : 'error'
  message.value = removed ? `已从素材库移除 ${asset.name}` : '素材移除失败'
}

function splitTerms(value: string): string[] {
  return value.split(/[,，]/).map(item => item.trim()).filter(Boolean)
}

function hexToTint(value: string): [number, number, number] {
  const normalized = /^#[0-9a-f]{6}$/i.test(value) ? value.slice(1) : 'ffffff'
  return [0, 2, 4].map(index => Number.parseInt(normalized.slice(index, index + 2), 16) / 255) as [number, number, number]
}

function tintToHex(value?: [number, number, number]): string {
  const tint = value ?? [1, 1, 1]
  return `#${tint.map(channel => Math.round(Math.max(0, Math.min(1, channel)) * 255).toString(16).padStart(2, '0')).join('')}`.toUpperCase()
}

function formatNumber(value: number | undefined, fallback: number): string {
  return (value ?? fallback).toFixed(1)
}
</script>

<style scoped>
.asset-panel { height: 100%; display: flex; flex-direction: column; color: #cccccc; }
.panel-header { padding: 8px 12px; font-size: 13px; font-weight: 500; border-bottom: 1px solid #3e3e42; }
.panel-body { flex: 1; overflow-y: auto; padding: 10px; display: flex; flex-direction: column; gap: 7px; }
.hint, .selection-tip, .empty { color: #8f8f96; font-size: 11px; line-height: 1.5; }
label { color: #bdbdbd; font-size: 11px; }
.number-row { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.number-row > div { display: flex; flex-direction: column; gap: 5px; min-width: 0; }
.color-row { display: grid; grid-template-columns: 1fr 1.5fr; gap: 8px; align-items: end; }
.color-row > div:first-child { display: flex; flex-direction: column; gap: 5px; }
.color-control { display: flex; align-items: center; gap: 8px; }
.color-control code { color: #9cdcfe; font-size: 10px; }
.parameter-help { color: #85858e; font-size: 10px; line-height: 1.4; }
.file-list { display: flex; flex-direction: column; gap: 6px; padding: 7px; background: #2d2d30; border-radius: 4px; }
.file-field { display: flex; flex-direction: column; gap: 3px; }
.file-list details { color: #9cdcfe; font-size: 10px; }
.file-list summary { padding: 3px 0; cursor: pointer; }
.optional-file { margin-top: 7px; }
.file-field b { color: #f48771; }
.file-field input { width: 100%; color: #999; font-size: 10px; }
.message { padding: 7px; border-radius: 3px; font-size: 11px; line-height: 1.4; }
.message.success { color: #4ec9b0; background: #20332e; }
.message.error { color: #f48771; background: #3b2424; }
.asset-list-header { display: flex; justify-content: space-between; margin-top: 8px; padding-top: 10px; border-top: 1px solid #3e3e42; font-size: 11px; }
.asset-list-header button { border: 0; background: transparent; color: #75beff; cursor: pointer; font-size: 11px; }
.asset-item { display: flex; gap: 8px; padding: 7px; background: #2d2d30; border-left: 2px solid #4ec9b0; border-radius: 3px; }
.asset-item img { width: 52px; height: 52px; flex: 0 0 52px; border-radius: 4px; object-fit: cover; background: #1e1e1e; }
.asset-info { min-width: 0; }
.asset-title { margin-bottom: 3px; font-size: 12px; }
.asset-item code { color: #9cdcfe; font-size: 10px; }
.asset-meta { margin-top: 4px; color: #85858e; font-size: 10px; }
.asset-parameters { margin-top: 3px; color: #c8c8c8; font-size: 10px; }
.asset-tags { margin-top: 3px; overflow: hidden; color: #b6a0ff; font-size: 10px; text-overflow: ellipsis; white-space: nowrap; }
.asset-actions { display: flex; align-items: center; gap: 4px; margin-top: 7px; }
.asset-actions :deep(.el-button + .el-button) { margin-left: 0; }
</style>
