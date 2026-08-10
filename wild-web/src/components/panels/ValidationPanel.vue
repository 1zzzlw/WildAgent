<template>
  <div class="validation-panel">
    <div class="panel-header">
      <span>校验结果</span>
    </div>
    <div class="panel-body">
      <div v-if="issues.length === 0 && reconstructionIssues.length === 0 && textureFailures.length === 0" class="success-state">
        ✓ 场景校验通过
      </div>
      <div v-else class="issues-list">
        <div v-for="(issue, index) in issues" :key="index" :class="['issue-item', issue.level]">
          <span class="issue-icon">{{ issue.level === 'error' ? '✕' : '⚠' }}</span>
          <div class="issue-content">
            <div class="issue-message">{{ issue.message }}</div>
            <div class="issue-meta" v-if="issue.elementId || issue.path">
              <span v-if="issue.elementId">元素: {{ issue.elementId }}</span>
              <span v-if="issue.path">路径: {{ issue.path }}</span>
            </div>
          </div>
        </div>
        <div class="diagnostic-section" v-if="reconstructionIssues.length > 0">
          <div class="diagnostic-title">
            wild-core 重建诊断 · {{ reconstructionIssues.length }} 项
          </div>
          <div
            v-for="issue in reconstructionIssues"
            :key="`${issue.code}:${issue.elementId}`"
            :class="['issue-item', issue.level]"
          >
            <span class="issue-icon">{{ issue.level === 'error' ? '✕' : '⚠' }}</span>
            <div class="issue-content">
              <div class="issue-message">{{ issue.message }}</div>
              <div class="issue-meta">
                <span v-if="issue.elementId">元素: {{ issue.elementId }}</span>
                <span>代码: {{ issue.code }}</span>
                <span v-if="issue.expectedBounds">预期: {{ formatBounds(issue.expectedBounds) }}</span>
                <span v-if="issue.actualBounds">实际: {{ formatBounds(issue.actualBounds) }}</span>
              </div>
            </div>
          </div>
        </div>
        <div class="diagnostic-section" v-if="textureFailures.length > 0">
          <div class="diagnostic-title">PBR 纹理加载失败 · {{ textureFailures.length }} 项</div>
          <div v-for="item in textureFailures" :key="`${item.channel}:${item.uri}`" class="issue-item error">
            <span class="issue-icon">✕</span>
            <div class="issue-content">
              <div class="issue-message">{{ item.channel }} 纹理未能加载</div>
              <div class="issue-meta">
                <span>地址: {{ item.uri }}</span>
                <span v-if="item.detail">原因: {{ item.detail }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
      <details v-if="reconstructionObservations.length > 0" class="reconstruction-report">
        <summary>
          重建映射 {{ reconstructionObservations.length }} 项
          · {{ sceneStore.reconstructed?.reconstructionReport.errorCount ?? 0 }} 错误
          · {{ sceneStore.reconstructed?.reconstructionReport.warningCount ?? 0 }} 警告
        </summary>
        <div
          v-for="observation in reconstructionObservations"
          :key="observation.sourceId"
          :class="['observation-item', observation.status]"
        >
          <div class="observation-title">
            <span>{{ observation.sourceId }}</span>
            <span>{{ observation.sourceType }}</span>
          </div>
          <div class="issue-meta">
            <span v-if="observation.targetId">宿主: {{ observation.targetId }}</span>
            <span>网格: {{ observation.meshCount }}</span>
            <span v-if="observation.actualBounds">实际: {{ formatBounds(observation.actualBounds) }}</span>
            <span v-if="observation.expectedBounds">参照: {{ formatBounds(observation.expectedBounds) }}</span>
          </div>
        </div>
      </details>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useSceneStore } from '../../stores/sceneStore'
import {
  getTextureLoadRecords,
  subscribeTextureLoads,
  type TextureLoadRecord,
} from '../../renderer/textureLoadMonitor'

const sceneStore = useSceneStore()
const textureLoads = ref<TextureLoadRecord[]>(getTextureLoadRecords())
let unsubscribeTextureLoads: (() => void) | undefined

onMounted(() => {
  unsubscribeTextureLoads = subscribeTextureLoads(records => { textureLoads.value = records })
})
onBeforeUnmount(() => unsubscribeTextureLoads?.())

const issues = computed(() => sceneStore.validationIssues)
const reconstructionIssues = computed(() => (
  sceneStore.reconstructed?.diagnostics.filter(issue => issue.level !== 'info') ?? []
))
const reconstructionObservations = computed(() => (
  sceneStore.reconstructed?.reconstructionReport.observations ?? []
))
const textureFailures = computed(() => textureLoads.value.filter(item => item.state === 'error'))

function formatBounds(bounds: { min: [number, number, number]; max: [number, number, number] }): string {
  const point = (value: [number, number, number]) => value.map(item => item.toFixed(2)).join(', ')
  return `[${point(bounds.min)}] → [${point(bounds.max)}]`
}
</script>

<style scoped>
.validation-panel {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.panel-header {
  padding: 8px 12px;
  font-size: 13px;
  font-weight: 500;
  border-bottom: 1px solid #3e3e42;
}

.panel-body {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}

.success-state {
  padding: 16px;
  text-align: center;
  color: #4ec9b0;
  font-size: 13px;
}

.issues-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.diagnostic-section {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid #3e3e42;
}

.diagnostic-title {
  padding: 2px 4px 6px;
  color: #c8c8c8;
  font-size: 11px;
  font-weight: 600;
}

.reconstruction-report {
  margin-top: 10px;
  padding-top: 8px;
  border-top: 1px solid #3e3e42;
  color: #85858e;
  font-size: 11px;
}

.reconstruction-report > summary {
  cursor: pointer;
}

.observation-item {
  margin-top: 6px;
  padding: 6px 8px;
  background: #252528;
  border-left: 2px solid #4ec9b0;
  border-radius: 3px;
}

.observation-item.warning { border-left-color: #dcdcaa; }
.observation-item.error { border-left-color: #f48771; }

.observation-title {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 4px;
  color: #c8c8c8;
}

.issue-item {
  display: flex;
  gap: 8px;
  padding: 8px;
  background: #2d2d30;
  border-left: 3px solid;
  border-radius: 3px;
  font-size: 12px;
}

.issue-item.error {
  border-color: #f48771;
}

.issue-item.warning {
  border-color: #dcdcaa;
}

.issue-icon {
  font-size: 14px;
}

.issue-item.error .issue-icon {
  color: #f48771;
}

.issue-item.warning .issue-icon {
  color: #dcdcaa;
}

.issue-content {
  flex: 1;
}

.issue-message {
  margin-bottom: 4px;
}

.issue-meta {
  display: flex;
  flex-direction: column;
  gap: 2px;
  color: #888888;
  font-size: 11px;
}
</style>
