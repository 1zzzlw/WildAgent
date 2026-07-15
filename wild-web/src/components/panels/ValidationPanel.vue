<template>
  <div class="validation-panel">
    <div class="panel-header">
      <span>校验结果</span>
    </div>
    <div class="panel-body">
      <div v-if="issues.length === 0" class="success-state">
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
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useSceneStore } from '../../stores/sceneStore'

const sceneStore = useSceneStore()

const issues = computed(() => sceneStore.validationIssues)
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
