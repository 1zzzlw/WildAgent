<template>
  <div class="asset-panel">
    <div class="panel-header">PBR 素材入库</div>
    <div class="panel-body">
      <div class="hint">
        图片保存到资产目录，WILD 仅记录 URL、哈希和授权信息，不写入 Base64。
      </div>

      <label>素材名称</label>
      <el-input v-model="form.name" size="small" placeholder="例如：浅灰石材" />
      <label>材质 ID</label>
      <el-input v-model="form.materialName" size="small" placeholder="例如：stone_light_pbr" />
      <label>授权信息</label>
      <el-input v-model="form.license" size="small" placeholder="例如：CC0 / User supplied" />

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

      <div class="file-list">
        <label v-for="field in fileFields" :key="field.key" class="file-field">
          <span>{{ field.label }}<b v-if="field.required"> *</b></span>
          <input type="file" accept="image/png,image/jpeg,image/webp" @change="setFile(field.key, $event)" />
        </label>
      </div>

      <label class="bind-option">
        <input v-model="bindSelection" type="checkbox" :disabled="!selectionStore.isSingleSelection" />
        入库后绑定到当前选中构件
      </label>
      <div v-if="selectionStore.isSingleSelection" class="selection-tip">
        当前选中：{{ selectionStore.selectedIds[0] }}
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
      <div v-if="assetStore.assets.length === 0" class="empty">尚无 PBR 资产</div>
      <div v-for="asset in assetStore.assets" :key="asset.assetId" class="asset-item">
        <div class="asset-title">{{ asset.name }}</div>
        <code>{{ asset.assetId }}</code>
        <div class="asset-meta">
          {{ Object.keys(asset.maps).join(' / ') }} · {{ asset.license }}
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import type { SceneOperation } from '../../types/scenePatch'
import { useAssetStore } from '../../stores/assetStore'
import { useSceneStore } from '../../stores/sceneStore'
import { useSelectionStore } from '../../stores/selectionStore'

type FileKey = 'baseColor' | 'normal' | 'roughness' | 'metalness' | 'ambientOcclusion'

const assetStore = useAssetStore()
const sceneStore = useSceneStore()
const selectionStore = useSelectionStore()
const bindSelection = ref(true)
const baseColorFile = ref<File | null>(null)
const optionalFiles = reactive<Partial<Record<FileKey, File>>>({})
const message = ref('')
const messageType = ref<'success' | 'error'>('success')
const form = reactive({
  name: '',
  materialName: '',
  license: 'User supplied',
  roughness: 0.8,
  metallic: 0,
})

const fileFields: Array<{ key: FileKey; label: string; required?: boolean }> = [
  { key: 'baseColor', label: 'Base Color', required: true },
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

onMounted(() => assetStore.refresh())

function setFile(key: FileKey, event: Event): void {
  const file = (event.target as HTMLInputElement).files?.[0]
  if (key === 'baseColor') baseColorFile.value = file || null
  else if (file) optionalFiles[key] = file
  else delete optionalFiles[key]
}

function selectedBinding(materialName: string): SceneOperation | null {
  if (!bindSelection.value || !selectionStore.isSingleSelection || !sceneStore.document) return null
  const id = selectionStore.selectedIds[0]
  const element = sceneStore.document.blueprint.geometry.elements.find(item => item.id === id)
  if (element) return { op: 'update_element', id, changes: { material: materialName } }
  const component = sceneStore.document.blueprint.geometry.components?.find(item => item.id === id)
  if (!component) return null
  const materialField = component.type === 'door'
    ? 'leafMaterial'
    : component.type === 'window'
      ? 'frameMaterial'
      : 'material'
  return { op: 'update_component', id, changes: { [materialField]: materialName } }
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
    uvScale: [1, 1],
    files: {
      baseColor: baseColorFile.value,
      normal: optionalFiles.normal,
      roughness: optionalFiles.roughness,
      metalness: optionalFiles.metalness,
      ambientOcclusion: optionalFiles.ambientOcclusion,
    },
  })
  if (!result) return
  const binding = selectedBinding(form.materialName.trim())
  if (binding) result.patch.operations.push(binding)
  const applied = await sceneStore.applyPatch(result.patch)
  messageType.value = applied ? 'success' : 'error'
  message.value = applied
    ? `已入库 ${result.asset.assetId} 并写入当前场景`
    : `资产 ${result.asset.assetId} 已入库，但场景补丁未通过，请查看校验面板`
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
.file-list { display: flex; flex-direction: column; gap: 6px; padding: 7px; background: #2d2d30; border-radius: 4px; }
.file-field { display: flex; flex-direction: column; gap: 3px; }
.file-field b { color: #f48771; }
.file-field input { width: 100%; color: #999; font-size: 10px; }
.bind-option { display: flex; align-items: center; gap: 6px; }
.message { padding: 7px; border-radius: 3px; font-size: 11px; line-height: 1.4; }
.message.success { color: #4ec9b0; background: #20332e; }
.message.error { color: #f48771; background: #3b2424; }
.asset-list-header { display: flex; justify-content: space-between; margin-top: 8px; padding-top: 10px; border-top: 1px solid #3e3e42; font-size: 11px; }
.asset-list-header button { border: 0; background: transparent; color: #75beff; cursor: pointer; font-size: 11px; }
.asset-item { padding: 7px; background: #2d2d30; border-left: 2px solid #4ec9b0; border-radius: 3px; }
.asset-title { margin-bottom: 3px; font-size: 12px; }
.asset-item code { color: #9cdcfe; font-size: 10px; }
.asset-meta { margin-top: 4px; color: #85858e; font-size: 10px; }
</style>
