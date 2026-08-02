<template>
  <el-popover
    v-if="presenceStore.supported"
    placement="bottom-end"
    :width="320"
    trigger="click"
    :disabled="!presenceStore.isConnected"
  >
    <template #reference>
      <el-tag
        class="presence-tag"
        :class="{ clickable: presenceStore.isConnected }"
        :type="presenceStore.isConnected ? 'success' : 'info'"
        effect="plain"
        size="small"
        round
        title="查看当前在线连接"
      >
        <span class="presence-dot" :class="{ online: presenceStore.isConnected }"></span>
        {{ presenceText }}
      </el-tag>
    </template>

    <div class="presence-panel">
      <div class="presence-panel-title">
        <span>当前在线访客</span>
        <span>{{ presenceStore.onlineCount }} 个</span>
      </div>
      <div class="presence-self">
        <span>我的名称：{{ presenceStore.visitorName }}</span>
        <el-button link type="primary" size="small" @click="changeVisitorName">修改</el-button>
      </div>
      <div v-if="presenceStore.onlineClients.length === 0" class="presence-empty">
        暂无在线连接信息
      </div>
      <div v-else class="presence-list">
        <div v-for="client in presenceStore.onlineClients" :key="client.id" class="presence-client">
          <span class="presence-client-dot"></span>
          <div class="presence-client-main">
            <span class="presence-client-name">{{ client.display_name || '访客' }}</span>
            <span class="presence-client-detail">{{ client.region }} · {{ client.masked_ip }}</span>
          </div>
          <span class="presence-client-time">{{ formatConnectionTime(client.connected_at) }}</span>
        </div>
      </div>
      <div class="presence-privacy">IP 已脱敏；地区信息仅供参考</div>
    </div>
  </el-popover>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { ElMessageBox } from 'element-plus'
import { MAX_VISITOR_NAME_LENGTH } from './types'
import { normalizeVisitorName, usePresenceStore } from './store'

const presenceStore = usePresenceStore()
const presenceText = computed(() => {
  if (presenceStore.connectionStatus === 'connecting') return '连接中'
  if (presenceStore.connectionStatus === 'reconnecting') return '重连中'
  if (!presenceStore.isConnected) return '离线'
  return `${presenceStore.onlineCount} 人在线`
})

function formatConnectionTime(timestamp: number) {
  return new Date(timestamp).toLocaleTimeString('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
  })
}

async function changeVisitorName() {
  try {
    const result = await ElMessageBox.prompt(
      '名称只用于在线列表展示。',
      '修改访客名称',
      {
        inputValue: presenceStore.visitorName,
        confirmButtonText: '保存',
        cancelButtonText: '取消',
        inputValidator: value => {
          if (!normalizeVisitorName(value)) return '请输入访客名称'
          if ([...value].length > MAX_VISITOR_NAME_LENGTH) {
            return `名称不能超过 ${MAX_VISITOR_NAME_LENGTH} 个字符`
          }
          return true
        },
      },
    )
    presenceStore.setVisitorName(result.value)
  } catch {
    // 用户取消修改时不处理。
  }
}
</script>

<style scoped>
.presence-tag {
  flex: none;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-variant-numeric: tabular-nums;
}

.presence-tag.clickable {
  cursor: pointer;
}

.presence-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #7f848e;
}

.presence-dot.online {
  background: #67c23a;
  box-shadow: 0 0 6px rgba(103, 194, 58, 0.65);
}

.presence-panel-title,
.presence-client {
  display: flex;
  align-items: center;
}

.presence-panel-title {
  justify-content: space-between;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--el-border-color-lighter);
  font-weight: 600;
}

.presence-self {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 2px;
  color: var(--el-text-color-regular);
  font-size: 12px;
  border-bottom: 1px solid var(--el-border-color-extra-light);
}

.presence-list {
  max-height: 280px;
  overflow-y: auto;
}

.presence-client {
  gap: 10px;
  padding: 10px 2px;
  border-bottom: 1px solid var(--el-border-color-extra-light);
}

.presence-client-dot {
  width: 8px;
  height: 8px;
  flex: none;
  border-radius: 50%;
  background: #67c23a;
}

.presence-client-main {
  min-width: 0;
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.presence-client-name {
  color: var(--el-text-color-primary);
  font-size: 13px;
  font-weight: 600;
}

.presence-client-detail,
.presence-client-time,
.presence-privacy,
.presence-empty {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.presence-client-time {
  flex: none;
  font-variant-numeric: tabular-nums;
}

.presence-empty {
  padding: 18px 0;
  text-align: center;
}

.presence-privacy {
  padding-top: 10px;
  line-height: 1.5;
}
</style>
