<template>
  <div class="session-list-panel">
    <button type="button" class="session-picker" aria-haspopup="dialog"
      :aria-label="`切换会话，当前：${currentName}`" @click="openPicker">
      <span :class="['header-dot', `dot-${currentStatus}`]"></span>
      <span class="current-session-name" :title="currentName">{{ currentName }}</span>
      <span class="switch-label">切换会话</span>
      <el-icon><ArrowDown /></el-icon>
    </button>
    <el-button class="new-session-btn" size="small" @click="$emit('new')">
      <el-icon><Plus /></el-icon><span>新建</span>
    </el-button>

    <el-dialog
      v-model="pickerVisible"
      title="切换会话"
      class="session-dialog"
      width="min(680px, calc(100vw - 32px))"
      top="12vh"
      append-to-body
      @opened="searchInput?.focus()"
    >
      <div class="session-picker-tools">
        <el-input ref="searchInput" v-model="searchQuery" placeholder="搜索会话名称或 ID"
          :prefix-icon="Search" clearable aria-label="搜索会话" />
        <el-button type="primary" @click="createSession">
          <el-icon><Plus /></el-icon><span>新建会话</span>
        </el-button>
      </div>
      <div class="session-list-hint">
        <span>{{ filteredSessions.length }} 个会话</span>
        <span>按最近更新排序</span>
      </div>
      <div class="session-cards" aria-label="会话列表">
        <div v-for="session in filteredSessions" :key="session.session_id"
          :class="['session-card', { 'session-active': session.session_id === agentStore.currentSessionId }]">
          <button type="button" class="session-select"
            :aria-current="session.session_id === agentStore.currentSessionId ? 'true' : undefined"
            @click="selectSession(session.session_id)">
            <span :class="['header-dot', `dot-${session.status}`]"></span>
            <span class="session-card-body">
              <span class="session-name-row">
                <span class="session-name" :title="session.name">{{ session.name || '新建筑' }}</span>
                <span v-if="session.session_id === agentStore.currentSessionId" class="current-badge">当前</span>
              </span>
              <span class="session-meta">
                <span>{{ statusLabel(session.status) }}</span>
                <span v-if="session.elements_count || session.components_count">{{ session.elements_count || 0 }} 个元素</span>
                <span>{{ formatRelativeTime(session.updated_at) }}</span>
              </span>
              <span class="session-id">{{ session.session_id }}</span>
            </span>
          </button>
          <el-dropdown trigger="click" placement="bottom-end" popper-class="session-menu">
            <button type="button" class="menu-trigger" :aria-label="`管理会话：${session.name || '新建筑'}`">···</button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item @click="renameSession(session)">重命名</el-dropdown-item>
                <el-dropdown-item @click="$emit('delete', session.session_id)"
                  class="danger-item">删除</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
        <div v-if="filteredSessions.length === 0" class="session-empty">
          {{ searchQuery.trim() ? '没有找到匹配的会话，试试其他名称或 ID' : '暂无会话，可以新建一个会话' }}
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { ElDialog, ElMessageBox, type InputInstance } from 'element-plus'
import 'element-plus/es/components/dialog/style/css'
import { ArrowDown, Plus, Search } from '@element-plus/icons-vue'
import { useAgentStore, formatRelativeTime } from '../../stores/agentStore'
import type { SessionInfo } from '../../types/agent'

const agentStore = useAgentStore()
const emit = defineEmits<{
  switch: [sessionId: string]
  new: []
  delete: [sessionId: string]
}>()

const pickerVisible = ref(false)
const searchQuery = ref('')
const searchInput = ref<InputInstance>()
const currentInfo = computed(() =>
  agentStore.sessions.find(session => session.session_id === agentStore.currentSessionId)
)
const currentName = computed(() => currentInfo.value?.name || '新建筑')
const currentStatus = computed(() => currentInfo.value?.status || 'draft')
const filteredSessions = computed(() => {
  const query = searchQuery.value.trim().toLowerCase()
  return agentStore.sessions
    .filter(session => !query || session.name.toLowerCase().includes(query) || session.session_id.toLowerCase().includes(query))
    .slice()
    .sort((a, b) => b.updated_at - a.updated_at)
})

function openPicker() {
  searchQuery.value = ''
  pickerVisible.value = true
}

function selectSession(sessionId: string) {
  emit('switch', sessionId)
  pickerVisible.value = false
}

function createSession() {
  emit('new')
  pickerVisible.value = false
}

async function renameSession(session: SessionInfo) {
  try {
    const { value } = await ElMessageBox.prompt('请输入新的会话名称', '重命名会话', {
      inputValue: session.name,
      customClass: 'session-rename-dialog',
      inputValidator: value => Boolean(value?.trim()) || '会话名称不能为空',
      confirmButtonText: '保存',
      cancelButtonText: '取消',
    })
    const name = value.trim()
    if (name !== session.name) agentStore.renameSession(session.session_id, name)
  } catch {
    // 用户取消
  }
}

function statusLabel(status: SessionInfo['status']) {
  return { saved: '已保存', draft: '草稿', generating: '生成中' }[status]
}
</script>

<style scoped>
.session-list-panel,
:global(.session-dialog),
:global(.session-menu),
:global(.session-rename-dialog) {
  --el-color-primary: #6899d4;
  --el-color-primary-light-9: #2b3646;
  --el-bg-color: #252528;
  --el-bg-color-overlay: #252528;
  --el-fill-color-blank: #202023;
  --el-fill-color-light: #303039;
  --el-text-color-primary: #e4e4e7;
  --el-text-color-regular: #c5c5cd;
  --el-text-color-secondary: #94949e;
  --el-text-color-placeholder: #767681;
  --el-border-color: #42424c;
  --el-border-color-light: #393941;
  --el-border-color-lighter: #32323a;
  color-scheme: dark;
}

.session-list-panel {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  flex-shrink: 0;
  border-bottom: 1px solid rgba(255, 255, 255, 0.07);
  background: rgba(0, 0, 0, 0.15);
}

.session-picker {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
  min-width: 0;
  height: 32px;
  padding: 0 10px;
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.03);
  color: var(--el-text-color-secondary);
  cursor: pointer;
  transition: background-color 0.15s, border-color 0.15s;
}

.session-picker:hover,
.session-card:hover {
  border-color: rgba(104, 153, 212, 0.45);
  background-color: rgba(104, 153, 212, 0.08);
}

.current-session-name,
.session-name {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
  text-align: left;
  font-size: 13px;
  line-height: 1.5;
  color: var(--el-text-color-primary);
}

.switch-label {
  flex-shrink: 0;
  font-size: 12px;
  color: #9dbce1;
}

.new-session-btn {
  height: 32px;
  margin: 0;
  border-color: var(--el-border-color);
  background: transparent;
  color: var(--el-text-color-regular);
}

.header-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  flex-shrink: 0;
}

.dot-saved { background: #6bbf9b; }
.dot-draft { background: #d4b871; }
.dot-generating { background: #6899d4; }

.session-picker-tools {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 10px;
}

.session-picker-tools .el-button {
  margin: 0;
}

.session-list-hint,
.session-name-row,
.session-meta {
  display: flex;
  align-items: center;
  gap: 10px;
}

.session-list-hint {
  justify-content: space-between;
  margin: 16px 0 10px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.session-cards {
  max-height: min(460px, calc(76dvh - 170px));
  padding: 2px 4px 2px 2px;
  overflow-y: auto;
  overscroll-behavior: contain;
  scrollbar-gutter: stable;
}

.session-card {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  padding-right: 10px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  transition: background-color 0.15s, border-color 0.15s;
}

.session-active {
  border-color: var(--el-color-primary);
  background: rgba(104, 153, 212, 0.1);
}

.session-select {
  display: flex;
  align-items: center;
  gap: 12px;
  flex: 1;
  min-width: 0;
  padding: 12px;
  border: 0;
  border-radius: 7px;
  background: transparent;
  text-align: left;
  cursor: pointer;
  font: inherit;
  color: var(--el-text-color-primary);
}

.session-card-body {
  flex: 1;
  min-width: 0;
}

.session-name {
  font-weight: 500;
}

.current-badge {
  flex-shrink: 0;
  font-size: 11px;
  color: var(--el-color-primary);
}

.session-meta {
  flex-wrap: wrap;
  gap: 4px 12px;
  margin-top: 5px;
  font-size: 12px;
  line-height: 1.5;
  color: var(--el-text-color-secondary);
}

.session-id {
  display: block;
  margin-top: 4px;
  overflow-wrap: anywhere;
  font-size: 11px;
  line-height: 1.5;
  color: var(--el-text-color-placeholder);
}

.menu-trigger {
  width: 32px;
  height: 32px;
  padding: 0;
  border: 0;
  border-radius: 5px;
  background: transparent;
  color: var(--el-text-color-secondary);
  font-size: 18px;
  cursor: pointer;
}

.menu-trigger:hover {
  background: rgba(104, 153, 212, 0.15);
}

.danger-item {
  color: var(--el-color-danger);
}

.session-empty {
  padding: 40px 12px;
  text-align: center;
  color: var(--el-text-color-secondary);
}

.session-picker:focus-visible,
.session-select:focus-visible,
.menu-trigger:focus-visible {
  outline: 2px solid var(--el-color-primary);
  outline-offset: -2px;
}

@media (max-width: 420px) {
  .switch-label {
    display: none;
  }

  .session-picker-tools {
    grid-template-columns: minmax(0, 1fr);
  }

  .session-picker-tools .el-button {
    justify-self: end;
  }
}

@media (prefers-reduced-motion: reduce) {
  .session-picker,
  .session-card {
    transition: none;
  }
}
</style>
