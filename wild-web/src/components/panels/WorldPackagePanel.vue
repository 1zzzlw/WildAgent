<template>
  <section class="world-package-panel">
    <div class="section-heading">
      <div>
        <strong>{{ mode === 'material' ? '世界材质包' : '世界光影与天气' }}</strong>
        <p v-if="mode === 'material'">导入 .wildmat 后，可将 PBR 材质应用到当前选中的构件。</p>
        <p v-else>导入 .wildlook 后需手动启用；天气参数作用于整个世界。</p>
      </div>
      <el-button size="small" :loading="worldStore.loading" @click="openPackageFile">
        导入 {{ packageExtension }}
      </el-button>
      <input
        ref="packageInput"
        class="hidden-input"
        type="file"
        :accept="packageExtension"
        @change="handlePackageFile"
      />
    </div>

    <div class="runtime-grid single">
      <label v-if="mode === 'material'">
        <span>默认表面 Shader</span>
        <el-switch
          :model-value="worldStore.rendering.surfaceEnabled"
          @change="toggleSurface"
        />
      </label>
      <label v-else>
        <span>全局天气效果</span>
        <el-switch
          :model-value="worldStore.rendering.weatherEnabled"
          @change="toggleWeather"
        />
      </label>
    </div>

    <section v-if="mode === 'look'" class="weather-panel">
      <div class="weather-heading">
        <div>
          <strong>全局环境天气</strong>
          <p>作用于整个世界，不写入单栋建筑 Blueprint。</p>
        </div>
        <span>{{ activeWeatherPreset ? WORLD_WEATHER_PRESETS[activeWeatherPreset].label : '自定义' }}</span>
      </div>
      <div class="weather-presets">
        <button
          v-for="presetId in WORLD_WEATHER_PRESET_ORDER"
          :key="presetId"
          type="button"
          :class="{ active: activeWeatherPreset === presetId }"
          :title="WORLD_WEATHER_PRESETS[presetId].description"
          :aria-pressed="activeWeatherPreset === presetId"
          @click="applyWeatherPreset(presetId)"
        >
          <span aria-hidden="true">{{ WORLD_WEATHER_PRESETS[presetId].icon }}</span>
          {{ WORLD_WEATHER_PRESETS[presetId].label }}
        </button>
      </div>
      <details class="weather-settings">
        <summary>高级参数微调</summary>
        <label v-for="control in weatherControls" :key="control.key">
          <span>{{ control.label }} · {{ worldStore.environment[control.key].toFixed(2) }}</span>
          <el-slider
            :model-value="worldStore.environment[control.key]"
            :min="0"
            :max="1"
            :step="0.05"
            @input="setWeather(control.key, $event)"
          />
        </label>
      </details>
      <div class="effect-heading">
        <strong>环境渲染效果</strong>
        <p>云层、积水、波纹、沙尘、体积雾与反射，默认关闭；开启时会自动提升对应天气参数，积水需展示模式或草地等环境。</p>
      </div>
      <div class="effect-grid">
        <label v-for="effectId in effectOrder" :key="effectId">
          <span class="effect-name">{{ effectLabels[effectId].icon }} {{ effectLabels[effectId].label }}</span>
          <el-switch
            size="small"
            :model-value="effectState[effectId]"
            @change="toggleEffect(effectId, $event)"
          />
        </label>
      </div>
    </section>

    <div v-if="message" :class="['package-message', messageType]">{{ message }}</div>
    <div v-if="worldStore.error" class="package-message error">{{ worldStore.error }}</div>

    <div v-if="mode === 'material'" class="package-group">
      <div class="group-title">材质包 · {{ worldStore.materialPackages.length }}</div>
      <div v-if="!worldStore.materialPackages.length" class="empty">尚未导入 .wildmat</div>
      <article v-for="item in worldStore.materialPackages" :key="item.manifest.packageId" class="package-card">
        <div class="card-title">
          <span>{{ item.manifest.name }}</span>
          <em :class="item.unsupportedFeatures.length ? 'unsupported' : 'supported'">
            {{ item.unsupportedFeatures.length ? '缺少能力' : '支持' }}
          </em>
        </div>
        <code>{{ item.manifest.materialId }} · v{{ item.manifest.version }}</code>
        <p>{{ item.manifest.family || 'neutral' }} · {{ item.manifest.license }} · {{ trustLabel(item.trust) }}</p>
        <div v-if="item.unsupportedFeatures.length" class="unsupported-list">
          {{ item.unsupportedFeatures.join('、') }}
        </div>
        <div class="card-actions">
          <el-button
            type="primary"
            plain
            size="small"
            :disabled="!selectionStore.hasSelection || item.unsupportedFeatures.length > 0"
            @click="applyMaterialPackage(item.manifest)"
          >
            应用到已选 {{ selectionStore.selectedIds.length || '' }}
          </el-button>
          <el-button type="danger" text size="small" @click="removeMaterial(item.manifest.packageId)">移除</el-button>
        </div>
      </article>
    </div>

    <div v-else class="package-group">
      <div class="group-title">光影包 · {{ worldStore.lookProfiles.length }}</div>
      <article v-for="profile in worldStore.lookProfiles" :key="profile.profileId" class="package-card">
        <div class="card-title">
          <span>{{ profile.name }}</span>
          <em :class="worldStore.activeProfileId === profile.profileId ? 'active' : 'supported'">
            {{ worldStore.activeProfileId === profile.profileId ? '使用中' : '已安装' }}
          </em>
        </div>
        <code>{{ profile.profileId }} · v{{ profile.version }}</code>
        <p>{{ profile.license || '内置/未声明许可证' }}</p>
        <div class="card-actions">
          <el-button
            type="primary"
            plain
            size="small"
            :disabled="worldStore.activeProfileId === profile.profileId"
            @click="activateLook(profile.profileId)"
          >启用</el-button>
          <el-button
            v-if="profile.profileId !== 'builtin:default'"
            type="danger"
            text
            size="small"
            @click="removeLook(profile.profileId)"
          >移除</el-button>
        </div>
      </article>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, toRef } from 'vue'
import { ElMessageBox } from 'element-plus'
import type { MaterialDef, PBRTextureSetAsset, ReferencedImageData } from '../../types/blueprint'
import type { WorldEnvironmentState, WildMaterialPackageManifest } from '../../wild-core/src/materials'
import { useSceneStore } from '../../stores/sceneStore'
import { useSelectionStore } from '../../stores/selectionStore'
import { useWorldPackageStore } from '../../stores/worldPackageStore'
import { createPatch } from '../../wild/scenePatch'
import { createSelectedMaterialBindings } from '../../wild/materialBindings'
import { createWorldPackageChannelUri } from '../../renderer/worldMaterialRuntime'
import {
  matchWorldWeatherPreset,
  WORLD_WEATHER_PRESET_ORDER,
  WORLD_WEATHER_PRESETS,
  type WorldWeatherPresetId,
} from '../../renderer/worldWeatherRuntime'
import {
  getWorldEffectState,
  updateWorldEffectState,
  WORLD_EFFECT_LABELS,
  WORLD_EFFECT_ORDER,
  type WorldEffectId,
  type WorldEffectState,
} from '../../renderer/worldEffectRuntime'

type WeatherKey = 'rain' | 'wetness' | 'snow' | 'dust' | 'cloudCoverage' | 'fog' | 'wind'

const props = withDefaults(defineProps<{ mode?: 'material' | 'look' }>(), {
  mode: 'material',
})
const mode = toRef(props, 'mode')

const worldStore = useWorldPackageStore()
const sceneStore = useSceneStore()
const selectionStore = useSelectionStore()
const packageInput = ref<HTMLInputElement>()
const message = ref('')
const messageType = ref<'success' | 'error'>('success')
const packageExtension = computed(() => mode.value === 'material' ? '.wildmat' : '.wildlook')
const weatherControls: Array<{ key: WeatherKey; label: string }> = [
  { key: 'rain', label: '降雨' },
  { key: 'wetness', label: '表面湿润' },
  { key: 'snow', label: '积雪' },
  { key: 'dust', label: '积尘' },
  { key: 'cloudCoverage', label: '云量' },
  { key: 'fog', label: '雾强度' },
  { key: 'wind', label: '风力' },
]
const activeWeatherPreset = computed(() => matchWorldWeatherPreset(worldStore.environment))
const effectState = reactive<WorldEffectState>({ ...getWorldEffectState() })
const effectOrder = WORLD_EFFECT_ORDER
const effectLabels = WORLD_EFFECT_LABELS

onMounted(() => void worldStore.initialize())

function openPackageFile(): void {
  packageInput.value?.click()
}

async function handlePackageFile(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  message.value = ''
  try {
    if (!file.name.toLowerCase().endsWith(packageExtension.value)) {
      throw new Error(`请选择 ${packageExtension.value} 文件`)
    }
    const id = await worldStore.importFile(file, mode.value)
    messageType.value = 'success'
    message.value = mode.value === 'material'
      ? `已安全导入 ${id}；请选择构件后再应用材质。`
      : `已安全导入 ${id}；光影包不会自动启用。`
  } catch (cause) {
    messageType.value = 'error'
    message.value = cause instanceof Error
      ? cause.message
      : '导入失败，当前场景和光影保持不变。'
  }
}

function setWeather(key: WeatherKey, value: number | number[]): void {
  if (typeof value !== 'number') return
  worldStore.setEnvironment({ [key]: value } as Partial<WorldEnvironmentState>)
}

function applyWeatherPreset(presetId: WorldWeatherPresetId): void {
  worldStore.setEnvironment(WORLD_WEATHER_PRESETS[presetId].environment)
}

function toggleSurface(value: string | number | boolean): void {
  worldStore.setRendering({ surfaceEnabled: Boolean(value) })
}

function toggleWeather(value: string | number | boolean): void {
  worldStore.setRendering({ weatherEnabled: Boolean(value) })
}

function toggleEffect(id: WorldEffectId, value: string | number | boolean): void {
  const enabled = Boolean(value)
  effectState[id] = enabled
  updateWorldEffectState({ [id]: enabled })
  // 开启效果时若对应天气参数过低，自动提升到可见水平，避免"开了开关却看不到"。
  if (!enabled) return
  const boost: Partial<WorldEnvironmentState> = {}
  if (id === 'clouds' && worldStore.environment.cloudCoverage < 0.35) {
    boost.cloudCoverage = 0.55
  }
  if (id === 'dustParticles' && worldStore.environment.dust < 0.35) {
    boost.dust = 0.6
  }
  if (id === 'volumetricFog' && worldStore.environment.fog < 0.25) {
    boost.fog = 0.5
  }
  if ((id === 'puddles' || id === 'ripples' || id === 'reflections') && worldStore.environment.rain < 0.3) {
    boost.rain = 0.6
    if (worldStore.environment.wetness < 0.3) boost.wetness = 0.6
  }
  if (Object.keys(boost).length) worldStore.setEnvironment(boost)
}

async function applyMaterialPackage(manifest: WildMaterialPackageManifest): Promise<void> {
  if (!sceneStore.document) return
  const bindings = createSelectedMaterialBindings(
    sceneStore.document.blueprint,
    selectionStore.selectedIds,
    manifest.materialId,
  )
  if (!bindings.length) {
    messageType.value = 'error'
    message.value = '请先选择需要应用材质包的构件。'
    return
  }
  try {
    const asset = manifestToBlueprintAsset(manifest)
    const defaults = manifest.defaults || {}
    const material: MaterialDef = {
      baseColor: defaults.baseColorTint || [1, 1, 1],
      roughness: defaults.roughness ?? 0.72,
      metallic: defaults.metallic ?? 0,
      albedo: 1,
      lightingCondition: 'D65_noon',
      textureSet: asset.assetId,
      normalScale: defaults.normalScale ?? 1,
      uvScale: defaults.uvScale ?? [1, 1],
      surfaceFamily: manifest.family,
      environmentResponse: manifest.environmentResponse,
      requiredFeatures: manifest.requiredFeatures,
    }
    const patch = createPatch(sceneStore.document.revision, [
      { op: 'upsert_asset', asset_id: asset.assetId, asset },
      { op: 'upsert_material', name: manifest.materialId, material },
      ...bindings,
    ], 'user', false, `应用世界材质包 ${manifest.name}`)
    const applied = await sceneStore.applyPatch(patch)
    messageType.value = applied ? 'success' : 'error'
    message.value = applied
      ? `已将 ${manifest.name} 应用到 ${bindings.length} 个构件。`
      : '材质包未通过场景校验，场景未改变。'
  } catch (cause) {
    messageType.value = 'error'
    message.value = cause instanceof Error ? cause.message : '材质包应用失败。'
  }
}

async function activateLook(profileId: string): Promise<void> {
  try {
    await worldStore.activateLook(profileId)
    messageType.value = 'success'
    message.value = `已启用光影包 ${profileId}，旧光影运行时资源已释放。`
  } catch {
    messageType.value = 'error'
    message.value = '光影包启用失败，继续使用原光影。'
  }
}

async function removeMaterial(packageId: string): Promise<void> {
  if (!await confirmRemove('材质包')) return
  if (sceneStore.document) {
    const blueprint = sceneStore.document.blueprint
    const assetIds = new Set(Object.values(blueprint.assets || {})
      .filter(asset => asset.source.type === 'wildmat' && asset.source.uri === packageId)
      .map(asset => asset.assetId))
    const fallbackOperations = Object.entries(blueprint.materials || {})
      .filter(([, material]) => Boolean(material.textureSet && assetIds.has(material.textureSet)))
      .map(([name, material]) => ({
        op: 'upsert_material' as const,
        name,
        material: {
          ...material,
          textureSet: undefined,
          textures: undefined,
          baseColor: material.baseColor || [0.5, 0.5, 0.5],
        } as MaterialDef,
      }))
    if (fallbackOperations.length) {
      const fallbackPatch = createPatch(
        sceneStore.document.revision,
        fallbackOperations,
        'system',
        false,
        `移除材质包 ${packageId} 前回退基础材质`,
      )
      if (!await sceneStore.applyPatch(fallbackPatch)) {
        messageType.value = 'error'
        message.value = '材质回退未通过校验，包没有被移除。'
        return
      }
    }
  }
  await worldStore.removeMaterial(packageId)
  messageType.value = 'success'
  message.value = '材质包已移除；正在使用的表面已回退基础颜色。'
}

async function removeLook(profileId: string): Promise<void> {
  if (!await confirmRemove('光影包')) return
  await worldStore.removeLook(profileId)
}

async function confirmRemove(kind: string): Promise<boolean> {
  try {
    await ElMessageBox.confirm(
      `确定移除这个${kind}？正在使用的光影会先回退默认；已写入 Blueprint 的材质仍保留声明。`,
      `移除${kind}`,
      { type: 'warning', confirmButtonText: '移除', cancelButtonText: '取消' },
    )
    return true
  } catch {
    return false
  }
}

function manifestToBlueprintAsset(manifest: WildMaterialPackageManifest): PBRTextureSetAsset {
  const hash = manifest.contentHash.toLowerCase().replace(/^sha256:/, '')
  if (!/^[0-9a-f]{64}$/.test(hash)) throw new Error('材质包 contentHash 必须是完整 SHA-256')
  const mapChannel = (
    name: keyof WildMaterialPackageManifest['channels'],
  ): ReferencedImageData | undefined => {
    const channel = manifest.channels[name]
    if (!channel) return undefined
    return {
      encoding: 'url',
      uri: createWorldPackageChannelUri(manifest.packageId, name),
      mimeType: channel.mimeType,
      sha256: channel.sha256.toLowerCase().replace(/^sha256:/, ''),
      byteSize: channel.byteSize,
      colorSpace: channel.colorSpace,
    }
  }
  return {
    schemaVersion: '1.0',
    assetId: `pbr_${hash.slice(0, 24)}`,
    kind: 'pbr_texture_set',
    name: manifest.name,
    contentHash: `sha256:${hash}`,
    source: { type: 'wildmat', uri: manifest.packageId },
    license: manifest.license,
    maps: {
      baseColor: mapChannel('baseColor')!,
      normal: mapChannel('normal'),
      roughness: mapChannel('roughness'),
      metalness: mapChannel('metalness'),
      ambientOcclusion: mapChannel('ambientOcclusion'),
    },
    classification: { materialClass: manifest.family },
    defaults: manifest.defaults,
    createdAt: new Date().toISOString(),
  }
}

function trustLabel(trust: 'builtin' | 'verified' | 'unverified'): string {
  return trust === 'verified' ? '签名已验证' : trust === 'builtin' ? '内置可信' : '本地未签名'
}
</script>

<style scoped>
.world-package-panel { display: flex; flex-direction: column; gap: 9px; padding: 9px; border: 1px solid #3e4653; border-radius: 6px; background: #25282e; }
.section-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 8px; }
.section-heading strong { color: #f0f3f7; font-size: 12px; }
.section-heading p { margin: 4px 0 0; color: #9299a5; font-size: 10px; line-height: 1.45; }
.hidden-input { display: none; }
.runtime-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; }
.runtime-grid.single { grid-template-columns: 1fr; }
.runtime-grid label { display: flex; align-items: center; justify-content: space-between; padding: 6px 7px; border-radius: 4px; background: #30343b; color: #cbd0d8; font-size: 10px; }
.weather-panel { padding: 8px; border: 1px solid #3a4655; border-radius: 6px; background: linear-gradient(145deg, #29313b, #272b31); }
.weather-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 8px; }
.weather-heading strong { color: #e8edf4; font-size: 11px; }
.weather-heading p { margin: 3px 0 0; color: #8f9aa7; font-size: 9px; line-height: 1.4; }
.weather-heading > span { flex: none; padding: 2px 6px; border-radius: 8px; color: #9dccff; background: #203c5c; font-size: 9px; }
.weather-presets { display: grid; grid-template-columns: repeat(3, 1fr); gap: 5px; margin-top: 8px; }
.weather-presets button { display: flex; align-items: center; justify-content: center; gap: 3px; min-height: 30px; border: 1px solid #414b58; border-radius: 5px; color: #b9c1cb; background: #30363e; font: inherit; font-size: 10px; cursor: pointer; transition: border-color 120ms ease, background 120ms ease, color 120ms ease; }
.weather-presets button:hover { border-color: #6398cf; color: #eef5fc; background: #344353; }
.weather-presets button.active { border-color: #66a9e8; color: #eaf5ff; background: #285079; box-shadow: inset 0 0 0 1px rgba(131, 193, 247, 0.16); }
.weather-settings { margin-top: 7px; padding: 6px 7px; border-radius: 4px; background: #252a30; }
.weather-settings summary { color: #9cdcfe; cursor: pointer; font-size: 10px; }
.weather-settings label { display: block; margin-top: 7px; color: #b9bec7; font-size: 10px; }
.effect-heading { margin-top: 10px; padding-top: 9px; border-top: 1px solid #3a4655; }
.effect-heading strong { color: #e8edf4; font-size: 11px; }
.effect-heading p { margin: 4px 0 0; color: #8f9aa7; font-size: 9px; line-height: 1.5; }
.effect-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; margin-top: 8px; }
.effect-grid label { display: flex; align-items: center; justify-content: space-between; gap: 8px; padding: 7px 9px; border: 1px solid #414b58; border-radius: 6px; background: #30363e; color: #cbd0d8; font-size: 10px; cursor: pointer; transition: border-color 120ms ease, background 120ms ease; }
.effect-grid label:hover { border-color: #6398cf; background: #344353; }
.effect-grid .effect-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.effect-grid label :deep(.el-switch) { --el-switch-on-color: #3aaed8; --el-switch-off-color: #5b626d; }
.package-message { padding: 6px 7px; border-radius: 4px; font-size: 10px; line-height: 1.45; }
.package-message.success { color: #63d6b5; background: #20352f; }
.package-message.error { color: #f29a8b; background: #3b2828; }
.package-group { display: flex; flex-direction: column; gap: 6px; }
.group-title { padding-top: 7px; border-top: 1px solid #3b414a; color: #c8ccd3; font-size: 10px; font-weight: 600; }
.empty { color: #858c97; font-size: 10px; }
.package-card { padding: 7px; border-left: 2px solid #689bd6; border-radius: 4px; background: #30343a; }
.card-title { display: flex; align-items: center; justify-content: space-between; gap: 6px; color: #eef2f7; font-size: 11px; }
.card-title em { padding: 2px 5px; border-radius: 8px; font-size: 9px; font-style: normal; }
.card-title .supported { color: #72d7b8; background: #214238; }
.card-title .active { color: #9dccff; background: #203c5c; }
.card-title .unsupported { color: #ffb19f; background: #4a2b28; }
.package-card code { display: block; margin-top: 4px; overflow: hidden; color: #9cdcfe; font-size: 9px; text-overflow: ellipsis; white-space: nowrap; }
.package-card p { margin: 4px 0 0; color: #9097a2; font-size: 9px; }
.unsupported-list { margin-top: 4px; color: #f29a8b; font-size: 9px; }
.card-actions { display: flex; gap: 4px; margin-top: 6px; }
.card-actions :deep(.el-button + .el-button) { margin-left: 0; }
</style>
