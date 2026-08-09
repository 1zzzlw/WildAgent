<template>
  <div class="session-list-panel" :class="{ 'is-expanded': expanded }">
    <!-- 紧凑标题栏（始终可见） -->
    <div class="session-header" @click="expanded = !expanded">
      <el-icon class="header-arrow">
        <component :is="expanded ? 'ArrowDown' : 'ArrowRight'" />
      </el-icon>
      <span :class="['header-dot', `dot-${currentStatus}`]"></span>
      <span class="header-name">{{ currentName }}</span>
      <span class="header-hint">{{ sessions.length }} 个会话</span>
      <el-button class="header-new-btn" size="small" @click.stop="$emit('new')" title="新建会话">
        +
      </el-button>
    </div>

    <!-- 展开：卡片列表 + 搜索 + 操作 -->
    <transition name="slide-down">
      <div v-if="expanded" class="session-body">
        <!-- 搜索 -->
        <div class="session-search" v-if="sessions.length > 3">
          <el-input v-model="searchQuery" size="small" placeholder="搜索会话..." clearable />
        </div>

        <!-- 卡片列表 -->
        <div class="session-cards">
          <div
            v-for="s in filteredSessions"
            :key="s.session_id"
            :class="['session-card', { 'session-active': s.session_id === agentStore.currentSessionId }]"
            @click="switchAndCollapse(s.session_id)"
            @dblclick="startRename(s)"
          >
            <div :class="['session-status-bar', `status-${s.status}`]"></div>
            <div class="session-card-body">
              <div class="session-name-row">
                <span v-if="!renamingId || renamingId !== s.session_id" class="session-name">
                  {{ s.name || '新建筑' }}
                </span>
                <el-input
                  v-else v-model="renameText" size="small" class="rename-input"
                  @blur="confirmRename(s)" @keydown.enter="confirmRename(s)" @keydown.escape="cancelRename"
                />
                <span :class="['session-status-tag', `tag-${s.status}`]">
                  {{ statusLabel(s.status) }}
                </span>
              </div>
              <div class="session-meta">
                <span v-if="s.elements_count || s.components_count">
                  {{ s.elements_count || 0 }}元素<span v-if="s.components_count">·{{ s.components_count }}组件</span>
                </span>
                <span class="meta-time">{{ formatRelativeTime(s.updated_at) }}</span>
              </div>
            </div>
            <div class="session-card-menu" @click.stop>
              <el-dropdown trigger="click" placement="bottom-end">
                <span class="menu-trigger">···</span>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item @click="startRename(s)">重命名</el-dropdown-item>
                    <el-dropdown-item v-if="s.status === 'saved'" @click="$emit('delete', s.session_id)" class="danger-item">
                      删除
                    </el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </div>
          </div>
          <div v-if="filteredSessions.length === 0" class="session-empty">
            {{ searchQuery ? '无匹配会话' : '暂无会话' }}
          </div>
        </div>

        <!-- 删除按钮 -->
        <div class="session-actions" v-if="canDeleteCurrent">
          <el-button class="action-del-btn" size="small" @click="$emit('delete', agentStore.currentSessionId)">
            删除当前会话
          </el-button>
        </div>
      </div>
    </transition>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, nextTick } from 'vue'
import { ArrowDown, ArrowRight } from '@element-plus/icons-vue'
import { useAgentStore, formatRelativeTime } from '../../stores/agentStore'
import type { SessionInfo } from '../../types/agent'

const agentStore = useAgentStore()

const emit = defineEmits<{
  switch: [sessionId: string]
  new: []
  delete: [sessionId: string]
}>()

// ── 展开/折叠 ──
const expanded = ref(false)

function switchAndCollapse(sessionId: string) {
  emit('switch', sessionId)
  expanded.value = false
}

// ── 当前会话信息（标题栏用）──
const currentInfo = computed(() =>
  agentStore.sessions.find(s => s.session_id === agentStore.currentSessionId)
)
const currentName = computed(() => currentInfo.value?.name || '新建筑')
const currentStatus = computed(() => currentInfo.value?.status || 'draft')
const sessions = computed(() => agentStore.sessions)

// ── 搜索 ──
const searchQuery = ref('')
const filteredSessions = computed(() => {
  const q = searchQuery.value.trim().toLowerCase()
  if (!q) return sessions.value
  return sessions.value.filter(s =>
    s.name.toLowerCase().includes(q) || s.session_id.includes(q)
  )
})

// ── 重命名 ──
const renamingId = ref<string | null>(null)
const renameText = ref('')

function startRename(s: SessionInfo) {
  renamingId.value = s.session_id
  renameText.value = s.name || '新建筑'
  nextTick(() => {
    const el = document.querySelector('.rename-input input') as HTMLInputElement | null
    el?.focus(); el?.select()
  })
}
function confirmRename(s: SessionInfo) {
  const n = renameText.value.trim()
  if (n && n !== s.name) agentStore.renameSession(s.session_id, n)
  renamingId.value = null
}
function cancelRename() { renamingId.value = null }

const canDeleteCurrent = computed(() => {
  const cur = sessions.value.find(s => s.session_id === agentStore.currentSessionId)
  return cur?.status === 'saved' && sessions.value.length > 1
})

function statusLabel(s: string) {
  return { saved: '已保存', draft: '草稿', generating: '生成中' }[s] || s
}
</script>

<style scoped>
.session-list-panel {
  flex-shrink: 0;
  border-bottom: 1px solid rgba(255,255,255,0.05);
  background: rgba(0,0,0,0.15);
}

/* ── 标题栏（始终可见，单行）── */
.session-header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  cursor: pointer;
  user-select: none;
  transition: background 0.12s;
}
.session-header:hover { background: rgba(255,255,255,0.03); }

.header-arrow {
  font-size: 12px;
  color: #6b6b75;
  flex-shrink: 0;
  transition: transform 0.15s;
}
.is-expanded .header-arrow { transform: rotate(0deg); }

.header-dot {
  width: 6px; height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
}
.dot-saved  { background: #6bbf9b; }
.dot-draft  { background: #d4b871; }
.dot-generating { background: #6899d4; animation: pulse-dot 1.2s ease-in-out infinite; }
@keyframes pulse-dot {
  0%,100%{ opacity:1; } 50%{ opacity:0.3; }
}

.header-name {
  font-size: 12px;
  font-weight: 500;
  color: #e4e4e7;
  flex: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.header-hint {
  font-size: 10px;
  color: #5a5a62;
  flex-shrink: 0;
}

.header-new-btn {
  width: 22px; height: 22px;
  padding: 0;
  font-size: 14px;
  font-weight: 600;
  line-height: 1;
  flex-shrink: 0;
  background: transparent;
  border: 1px solid rgba(255,255,255,0.08);
  color: #6b6b75;
  border-radius: 4px;
  cursor: pointer;
}
.header-new-btn:hover {
  color: #a0a0a8;
  border-color: rgba(255,255,255,0.15);
}

/* ── 展开区域（限制最大高度，不挤压消息区）── */
.session-body {
  max-height: 260px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.slide-down-enter-active, .slide-down-leave-active {
  transition: max-height 0.2s ease, opacity 0.15s ease;
}
.slide-down-enter-from, .slide-down-leave-to {
  max-height: 0;
  opacity: 0;
}

.session-search {
  padding: 4px 10px 6px;
  flex-shrink: 0;
}
.session-search :deep(.el-input__wrapper) {
  background: rgba(255,255,255,0.04);
  border: 1px solid rgba(255,255,255,0.06);
  border-radius: 5px;
}

.session-cards {
  flex: 1;
  overflow-y: auto;
  padding: 0 8px 4px;
}

.session-card {
  display: flex;
  margin-bottom: 2px;
  border-radius: 6px;
  background: rgba(255,255,255,0.03);
  border: 1px solid rgba(255,255,255,0.04);
  cursor: pointer;
  transition: background 0.12s;
  overflow: hidden;
}
.session-card:hover { background: rgba(255,255,255,0.06); }
.session-active { background: rgba(104,153,212,0.08); border-color: rgba(104,153,212,0.2); }

.session-status-bar {
  width: 2px; flex-shrink: 0;
}
.status-saved  { background: #6bbf9b; }
.status-draft  { background: #d4b871; }
.status-generating { background: #6899d4; }

.session-card-body { flex:1; padding: 6px 8px; min-width:0; }
.session-name-row { display:flex; align-items:center; gap:5px; margin-bottom:2px; }
.session-name {
  font-size:12px; font-weight:500; color:#e4e4e7;
  white-space:nowrap; overflow:hidden; text-overflow:ellipsis; flex:1;
}
.rename-input { flex:1; min-width:0; }

.session-status-tag {
  font-size:9px; padding:0 5px; border-radius:3px; flex-shrink:0; font-weight:500;
}
.tag-saved  { background:rgba(107,191,155,0.12); color:#6bbf9b; }
.tag-draft  { background:rgba(212,184,113,0.12); color:#d4b871; }
.tag-generating { background:rgba(104,153,212,0.12); color:#6899d4; }

.session-meta { font-size:10px; color:#5a5a62; }
.meta-time { color:#4a4a52; }

.session-card-menu { display:flex; align-items:flex-start; padding:4px 4px 0 0; flex-shrink:0; }
.menu-trigger {
  display:block; width:20px; height:20px; line-height:20px; text-align:center;
  font-size:12px; font-weight:700; color:#5a5a62; border-radius:4px; cursor:pointer; user-select:none;
}
.menu-trigger:hover { color:#a0a0a8; background:rgba(255,255,255,0.05); }
.danger-item { color:#e07060 !important; }

.session-empty { text-align:center; padding:16px; font-size:11px; color:#5a5a62; }

.session-actions {
  display:flex; padding:6px 8px;
  border-top:1px solid rgba(255,255,255,0.04); flex-shrink:0;
}
.action-del-btn {
  flex:1; height:28px; font-size:11px; color:#6b6b75;
  background:transparent; border:1px solid rgba(255,255,255,0.06);
  border-radius:5px; cursor:pointer;
}
.action-del-btn:hover { color:#e07060; border-color:rgba(224,112,96,0.3); }
</style>
