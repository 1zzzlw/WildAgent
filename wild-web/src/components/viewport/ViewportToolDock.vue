<template>
  <div ref="dock" class="viewport-tool-dock" @keydown.esc.stop="close">
    <nav class="orbit-toolbar" aria-label="视口圆形工具选择器">
      <div class="tool-orbit">
        <button class="circle-tool root-tool" :class="{ selected: active === 'viewport' }" aria-label="视口" data-label="视口" :aria-expanded="active === 'viewport'" @click="toggle('viewport')"><el-icon><Camera /></el-icon></button>
        <Transition name="orbit">
          <div v-if="active === 'viewport'" class="orbit-menu" role="group" aria-label="视口工具">
            <button v-for="(category,index) in categories" :key="category.type" class="circle-tool satellite category-tool"
              :class="{ selected: branch === category.type }" :style="position(index,categories.length,90)"
              :aria-label="category.label" :data-label="category.label" :aria-expanded="branch === category.type"
              @click="branch = branch === category.type ? null : category.type"><el-icon><EnvironmentIcon v-if="category.type === 'environment'" :preset="render.presets.environment as EnvironmentPresetId" /><component v-else :is="category.icon" /></el-icon></button>
            <TransitionGroup name="orbit-choice">
              <button v-for="(option,index) in choices" :key="branch+'-'+option.value" class="circle-tool satellite choice-tool"
                :class="{ chosen: branch && render.presets[branch] === option.value }" :style="position(index,choices.length,158)"
                :aria-label="branchLabel+'：'+option.label" :data-label="option.label" :aria-pressed="!!branch && render.presets[branch] === option.value"
                @click="choose(option.value)"><el-icon><EnvironmentIcon v-if="branch === 'environment'" :preset="option.value as EnvironmentPresetId" /><component v-else :is="option.icon" /></el-icon></button>
            </TransitionGroup>
          </div>
        </Transition>
      </div>
      <div class="tool-orbit">
        <button class="circle-tool root-tool render-tool" :class="{ selected: active === 'render' }" aria-label="渲染面板"
          :data-label="'渲染面板 · '+render.stats.fps+' FPS'" :aria-expanded="active === 'render'" @click="toggle('render')">
          <el-icon><Setting /></el-icon><span :class="['fps-number', fpsTier]">{{ render.stats.fps }}</span>
        </button>
        <Transition name="orbit">
          <div v-if="active === 'render'" class="orbit-menu" role="group" aria-label="渲染快捷工具">
            <button v-for="(action,index) in renderActions" :key="action.id" class="circle-tool satellite" :class="{ chosen: action.selected }"
              :style="position(index,renderActions.length,104)" :aria-label="action.label" :data-label="action.label" :aria-pressed="action.selected"
              @click="action.run()"><el-icon><component :is="action.icon" /></el-icon></button>
          </div>
        </Transition>
      </div>
      <div class="tool-orbit">
        <button class="circle-tool root-tool" :class="{ selected: active === 'section', chosen: render.sectionEnabled }" aria-label="剖切预览" data-label="剖切预览" :aria-expanded="active === 'section'" @click="toggle('section')"><el-icon><Crop /></el-icon></button>
        <Transition name="orbit">
          <div v-if="active === 'section'" class="orbit-menu" role="group" aria-label="剖切工具">
            <button class="circle-tool satellite" :class="{ chosen: render.sectionEnabled }" :style="position(0,3,90)" aria-label="切换水平剖切" data-label="水平剖切" :aria-pressed="render.sectionEnabled" @click="render.sectionEnabled = !render.sectionEnabled"><el-icon><Crop /></el-icon></button>
            <button class="circle-tool satellite" :style="position(1,3,90)" aria-label="升高剖切面" data-label="剖切面 +0.5m" @click="render.sectionHeight += .5"><el-icon><Top /></el-icon></button>
            <button class="circle-tool satellite" :style="position(2,3,90)" aria-label="降低剖切面" data-label="剖切面 −0.5m" @click="render.sectionHeight -= .5"><el-icon><Bottom /></el-icon></button>
            <output class="section-height" aria-live="polite">{{ render.sectionHeight.toFixed(1) }} m</output>
          </div>
        </Transition>
      </div>
      <div class="tool-orbit"><button class="circle-tool root-tool" :aria-label="'切换视角：'+cameraLabel" :data-label="'切换视角 · 当前'+cameraLabel" @click="render.requestNextCamera()"><el-icon><Aim /></el-icon></button></div>
    </nav>
    <Transition name="stats-panel">
      <section v-if="showStats && active === 'render'" class="render-details" aria-label="渲染信息与设置">
        <button class="close-details" aria-label="关闭渲染信息" @click="showStats = false"><el-icon><Close /></el-icon></button>
        <RenderControlPanel embedded />
      </section>
    </Transition>
  </div>
</template>
<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { Camera, Crop, Aim, Setting, Sunny, Sunset, Moon, User, Position, OfficeBuilding, Coordinate, Odometer, Cpu, MagicStick, View, Edit, Grid, Refresh, RefreshLeft, Download, InfoFilled, Top, Bottom, Close } from '@element-plus/icons-vue'
import { useRenderPanelStore, type RenderPresetRequest } from '../../stores/renderPanelStore'
import { CAMERA_PRESETS, ENVIRONMENT_PRESETS, TIME_PRESETS, QUALITY_PRESETS, type EnvironmentPresetId } from '../../renderer/defaultWorldLook'
import EnvironmentIcon from './EnvironmentIcon.vue'
import RenderControlPanel from './RenderControlPanel.vue'
const render = useRenderPanelStore()
const dock = ref<HTMLElement>()
const active = ref<'viewport' | 'render' | 'section' | null>(null)
const branch = ref<RenderPresetRequest['type'] | null>(null)
const showStats = ref(false)
const categories = [
  { type: 'camera' as const, label: '相机机位', icon: Camera },
  { type: 'environment' as const, label: '场景环境', icon: EnvironmentIcon },
  { type: 'time' as const, label: '光照时段', icon: Sunny },
  { type: 'quality' as const, label: '渲染质量', icon: MagicStick },
  { type: 'view' as const, label: '视图模式', icon: View },
]
const branchLabel = computed(() => categories.find(category => category.type === branch.value)?.label || '')
const choiceSets = {
  camera: Object.entries(CAMERA_PRESETS).map(([value,row]) => ({ value, label: row.label, icon: { corner: Coordinate, human: User, bird: Position, front: OfficeBuilding }[value] })),
  environment: Object.entries(ENVIRONMENT_PRESETS).map(([value,row]) => ({ value, label: row.label, icon: EnvironmentIcon })),
  time: Object.entries(TIME_PRESETS).map(([value,row]) => ({ value, label: row.label, icon: { day: Sunny, sunset: Sunset, night: Moon }[value] })),
  quality: Object.entries(QUALITY_PRESETS).map(([value,row]) => ({ value, label: row.label, icon: { low: Cpu, medium: Odometer, high: MagicStick }[value] })),
  view: [{ value: 'editor', label: '编辑', icon: Edit }, { value: 'presentation', label: '展示', icon: View }],
}
const choices = computed(() => branch.value ? choiceSets[branch.value] : [])
const cameraLabel = computed(() => CAMERA_PRESETS[render.presets.camera as keyof typeof CAMERA_PRESETS]?.label || '')
const fpsTier = computed(() => render.stats.fps >= 50 ? 'good' : render.stats.fps >= 30 ? 'ok' : 'bad')
const renderActions = computed(() => [
  { id: 'stats', label: '渲染信息', icon: InfoFilled, selected: showStats.value, run: () => { showStats.value = !showStats.value } },
  { id: 'edges', label: '建筑线条', icon: View, selected: render.showEdges, run: () => { render.showEdges = !render.showEdges } },
  { id: 'grid', label: '网格地面', icon: Grid, selected: render.showGrid, run: () => { render.showGrid = !render.showGrid } },
  { id: 'rotate', label: '自动旋转', icon: Refresh, selected: render.autoRotate, run: () => { render.autoRotate = !render.autoRotate } },
  { id: 'reset', label: '重置视角', icon: RefreshLeft, selected: false, run: () => render.requestResetView() },
  { id: 'screenshot', label: '保存截图', icon: Download, selected: false, run: () => render.requestScreenshot() },
])
function position(index: number, count: number, radius: number) {
  const angle = (count === 1 ? 0 : -70 + 140 * index / (count - 1)) * Math.PI / 180
  return { '--x': Math.cos(angle) * radius + 'px', '--y': Math.sin(angle) * radius + 'px', '--delay': index * 22 + 'ms' }
}
function choose(value: string) { if (branch.value) render.requestPreset({ type: branch.value, value } as RenderPresetRequest) }
function close() { active.value = null; branch.value = null; showStats.value = false }
function toggle(tool: NonNullable<typeof active.value>) { const next = active.value === tool ? null : tool; close(); active.value = next }
function closeOutside(event: PointerEvent) { if (!dock.value?.contains(event.target as Node)) close() }
onMounted(() => window.addEventListener('pointerdown', closeOutside))
onUnmounted(() => window.removeEventListener('pointerdown', closeOutside))
</script>
<style scoped>
.viewport-tool-dock{position:absolute;left:20px;top:clamp(150px,calc(50% - 105px),300px);z-index:45;pointer-events:none}.orbit-toolbar{display:flex;flex-direction:column;gap:12px}.tool-orbit{position:relative;width:46px;height:46px}.circle-tool{position:relative;display:grid;place-items:center;width:46px;height:46px;padding:0;flex-shrink:0;pointer-events:auto;border:1px solid #ffffff42;border-radius:50%;background:#182a2d30;backdrop-filter:blur(9px) saturate(120%);color:#e0eae7;box-shadow:0 3px 16px #0000001f,inset 0 1px #ffffff14;cursor:pointer;transition:background .18s,border-color .18s,box-shadow .18s}.circle-tool .el-icon,.circle-tool>svg{font-size:20px;width:20px;height:20px}.circle-tool:hover{background:#385a4e65;border-color:#e0fff3b0;box-shadow:0 0 18px #c2e8d526}.circle-tool.selected{background:#7caa9750;border-color:#c4e8d7bd;color:#edfff5}.circle-tool.chosen{background:#89c6a94a;border-color:#bcecd6bb;color:#d7ffe8}.circle-tool.chosen:before{content:'';position:absolute;right:3px;bottom:3px;width:5px;height:5px;border-radius:50%;background:#b6f1ce;box-shadow:0 0 7px #6fca95}.circle-tool:after{content:attr(data-label);position:absolute;left:calc(100% + 9px);top:50%;transform:translateY(-50%);padding:6px 9px;border:1px solid #ffffff20;border-radius:7px;background:#15262ce0;color:#dbe9e4;font-size:10px;white-space:nowrap;opacity:0;visibility:hidden;pointer-events:none;z-index:30;transition:opacity .12s}.circle-tool:hover:after,.circle-tool:focus-visible:after{opacity:1;visibility:visible}.root-tool{z-index:5}.root-tool:hover:after{display:none}.render-tool{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:2px}.render-tool .el-icon{flex:none;font-size:17px;width:17px;height:17px}.fps-number{display:block;min-width:3ch;height:11px;text-align:center;font:10px/11px ui-monospace,monospace;font-variant-numeric:tabular-nums;letter-spacing:.2px}.good{color:#a5edc3}.ok{color:#f0d38a}.bad{color:#efaaa0}.orbit-menu{position:absolute;top:23px;left:23px;width:0;height:0;pointer-events:none;z-index:8}.satellite{position:absolute;top:0;left:0;transform:translate(calc(var(--x) - 50%),calc(var(--y) - 50%));width:40px;height:40px;background:#203b3d35;animation:orbit-out .22s cubic-bezier(.18,.78,.24,1) both;animation-delay:var(--delay)}.choice-tool{width:38px;height:38px;background:#45685b38;border-color:#c4d9ce65}.choice-tool .el-icon{font-size:18px}.category-tool.selected{box-shadow:0 0 0 4px #b9e7cf13,0 0 20px #95c9ac24}.section-height{position:absolute;left:48px;top:-9px;color:#d5e8dd;font:11px monospace;white-space:nowrap;text-shadow:0 1px 5px #000;pointer-events:none}.render-details{position:absolute;left:174px;top:50%;transform:translateY(-50%);width:280px;max-height:min(570px,calc(100dvh - 90px));overflow:auto;pointer-events:auto;border:1px solid #ffffff33;border-radius:16px;background:#172a30bb;backdrop-filter:blur(18px);box-shadow:0 12px 40px #0004}.render-details :deep(.render-control-root.embedded){margin-top:0}.render-details :deep(.rc-panel){background:transparent;border:0}.close-details{position:absolute;right:10px;top:9px;z-index:2;display:grid;place-items:center;width:25px;height:25px;background:transparent;color:#afc8c9;border:0;cursor:pointer}.close-details~:deep(.render-control-root .rc-header){padding-right:24px}.orbit-enter-active,.orbit-leave-active{transition:opacity .15s}.orbit-enter-from,.orbit-leave-to{opacity:0}.orbit-choice-leave-active{transition:opacity .1s}.orbit-choice-leave-to{opacity:0}.stats-panel-enter-active,.stats-panel-leave-active{transition:opacity .18s}.stats-panel-enter-from,.stats-panel-leave-to{opacity:0}@keyframes orbit-out{from{opacity:0;transform:translate(-50%,-50%) scale(.4)}to{opacity:1;transform:translate(calc(var(--x) - 50%),calc(var(--y) - 50%)) scale(1)}}
@media(max-width:760px){.viewport-tool-dock{left:12px}.render-details{position:absolute;left:0;top:175px;transform:none;width:min(280px,calc(100vw - 95px));max-height:calc(100dvh - 290px);z-index:15}}
@media(max-height:500px){.viewport-tool-dock{top:105px;left:10px}.orbit-toolbar{gap:7px}.tool-orbit,.root-tool{width:40px;height:40px}.orbit-menu{top:20px;left:20px;transform:scale(.8);transform-origin:0 0}.render-details{top:-70px;transform:none;max-height:calc(100dvh - 100px)}}
</style>
