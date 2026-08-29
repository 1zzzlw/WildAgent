<template>
  <Teleport to="body">
    <Transition name="wild-config-modal">
      <div
        v-if="visible"
        ref="configOverlay"
        class="wild-config-modal__overlay"
        tabindex="-1"
        @click.self="handleClose"
        @keydown.esc="handleClose"
      >
        <section
          class="wild-config-modal__panel"
          role="dialog"
          aria-modal="true"
          aria-labelledby="wild-config-modal-title"
        >
          <header class="wild-config-modal__header">
            <div>
              <p class="wild-config-modal__eyebrow">系统设置</p>
              <h2 id="wild-config-modal-title">LLM 配置</h2>
            </div>
            <button class="wild-config-modal__close" type="button" aria-label="关闭" @click="handleClose">×</button>
          </header>

          <div class="config-content">
            <div class="config-scope-warning">
              这是当前服务器的全站 Chat 模型配置，会影响所有会话；它不是按用户隔离的个人密钥。
            </div>
            <div class="config-section">
              <label class="config-label">模型名称</label>
              <input
                v-model="form.name"
                type="text"
                class="config-input"
                placeholder="例如: qwen-plus, gpt-4, deepseek-chat"
              />
              <div class="config-hint">OpenAI-compatible 服务的模型名称</div>
            </div>

            <div class="config-section">
              <label class="config-label">API Key</label>
              <input
                v-model="form.api_key"
                type="password"
                class="config-input"
                placeholder="留空表示不修改"
              />
              <div class="config-hint">访问 LLM 服务的密钥</div>
            </div>

            <div class="config-section">
              <label class="config-label">Base URL</label>
              <input
                v-model="form.base_url"
                type="text"
                class="config-input"
                placeholder="留空使用默认地址"
              />
              <div class="config-hint">自建或第三方服务地址，例如: https://api.openai.com/v1</div>
            </div>

            <div class="config-divider"></div>

            <div class="config-section">
              <label class="config-label">当前配置</label>
              <div class="current-config">
                <div class="config-item">
                  <span class="config-key">模型:</span>
                  <span class="config-value">{{ currentConfig.name || '未配置' }}</span>
                </div>
                <div class="config-item">
                  <span class="config-key">API Key:</span>
                  <span class="config-value">{{ currentConfig.api_key_set ? '已设置' : '未设置' }}</span>
                </div>
                <div class="config-item">
                  <span class="config-key">Base URL:</span>
                  <span class="config-value">{{ currentConfig.base_url || '默认' }}</span>
                </div>
                <div class="config-item">
                  <span class="config-key">保存位置:</span>
                  <span class="config-value config-path">
                    {{ currentConfig.host_storage_path || currentConfig.storage_path || '未声明' }}
                  </span>
                </div>
                <div class="config-item">
                  <span class="config-key">持久化:</span>
                  <span :class="['config-value', currentConfig.persistent ? 'config-persistent' : 'config-volatile']">
                    {{ currentConfig.persistent ? '已映射，重启后保留' : '未确认，容器重建后可能丢失' }}
                  </span>
                </div>
              </div>
            </div>
          </div>

          <footer class="wild-config-modal__footer">
            <button type="button" class="btn-secondary" @click="handleTest" :disabled="testing">
              {{ testing ? '测试中...' : '测试连接' }}
            </button>
            <div v-if="testResult" class="test-result">
              <span v-if="testResult.success" class="test-success">
                ✓ 延迟: {{ testResult.latency }}ms
              </span>
              <span v-else class="test-error">
                ✗ {{ testResult.message }}
              </span>
            </div>
            <div style="flex: 1"></div>
            <button type="button" class="btn-secondary" @click="handleClose">取消</button>
            <button type="button" class="btn-primary" @click="handleSave" :disabled="saving">
              {{ saving ? '保存中...' : '保存' }}
            </button>
          </footer>
        </section>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'

interface Props {
  visible: boolean
}

interface Emits {
  (e: 'update:visible', value: boolean): void
}

const props = defineProps<Props>()
const emit = defineEmits<Emits>()

const form = ref({
  name: '',
  api_key: '',
  base_url: '',
})

const currentConfig = ref({
  name: '',
  api_key_set: false,
  base_url: '',
  storage_path: '',
  host_storage_path: null as string | null,
  persistent: false,
})

const saving = ref(false)
const testing = ref(false)
const configOverlay = ref<HTMLElement | null>(null)

const testResult = ref<{
  success: boolean
  latency?: number
  message?: string
} | null>(null)

watch(() => props.visible, async (visible) => {
  if (visible) {
    await loadCurrentConfig()
    testResult.value = null
    nextTick(() => configOverlay.value?.focus())
  }
})

async function loadCurrentConfig() {
  try {
    const response = await fetch('/api/config/llm', { cache: 'no-store' })
    if (!response.ok) throw new Error('加载失败')
    currentConfig.value = await response.json()
    
    form.value = {
      name: currentConfig.value.name,
      api_key: '',
      base_url: currentConfig.value.base_url,
    }
  } catch (error) {
    ElMessage.error('加载配置失败')
    console.error('Load config error:', error)
  }
}

async function handleSave() {
  saving.value = true
  try {
    const payload: Record<string, string> = {}
    
    if (form.value.name && form.value.name !== currentConfig.value.name) {
      payload.name = form.value.name
    }
    
    if (form.value.api_key) {
      payload.api_key = form.value.api_key
    }
    
    if (form.value.base_url !== currentConfig.value.base_url) {
      payload.base_url = form.value.base_url
    }
    
    if (Object.keys(payload).length === 0) {
      ElMessage.warning('没有修改任何配置')
      return
    }
    
    const response = await fetch('/api/config/llm', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    
    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: '保存失败' }))
      throw new Error(error.detail)
    }
    
    const data = await response.json()
    
    if (data.success) {
      ElMessage.success(data.config?.persistent
        ? '配置已保存到持久化文件，并已热重载'
        : '配置已热重载，但当前保存路径未声明为持久化')
      await loadCurrentConfig()
      handleClose()
    } else {
      ElMessage.error(data.message || '保存失败')
    }
  } catch (error: any) {
    ElMessage.error(error.message || '保存配置失败')
    console.error('Save config error:', error)
  } finally {
    saving.value = false
  }
}

async function handleTest() {
  testing.value = true
  testResult.value = null
  const startTime = Date.now()
  
  try {
    const response = await fetch('/api/config/llm/test', {
      method: 'POST',
    })
    
    const latency = Date.now() - startTime
    const data = await response.json()
    
    if (data.success) {
      testResult.value = {
        success: true,
        latency,
      }
    } else {
      testResult.value = {
        success: false,
        message: data.message || '连接失败',
      }
    }
  } catch (error: any) {
    testResult.value = {
      success: false,
      message: error.message || '网络错误',
    }
  } finally {
    testing.value = false
  }
}

function handleClose() {
  emit('update:visible', false)
}
</script>

<style scoped>
.wild-config-modal__overlay {
  position: fixed;
  z-index: 3000;
  inset: 0;
  display: grid;
  place-items: center;
  padding: 24px;
  background: rgba(8, 11, 16, 0.72);
  backdrop-filter: blur(4px);
  outline: none;
}

.wild-config-modal__panel {
  display: flex;
  width: min(600px, calc(100vw - 48px));
  max-height: min(86vh, 700px);
  overflow: hidden;
  flex-direction: column;
  border: 1px solid #42464f;
  border-radius: 12px;
  background: #25272c;
  box-shadow: 0 24px 72px rgba(0, 0, 0, 0.55);
  color: #d8dbe2;
}

.wild-config-modal__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 20px 22px 16px;
  border-bottom: 1px solid #393c43;
}

.wild-config-modal__eyebrow {
  margin: 0 0 3px;
  color: #55bfe6;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.16em;
}

.wild-config-modal__header h2 {
  margin: 0;
  color: #f5f6f8;
  font-size: 19px;
  font-weight: 600;
}

.wild-config-modal__close {
  width: 32px;
  height: 32px;
  padding: 0;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: #aeb3bd;
  cursor: pointer;
  font-size: 24px;
  line-height: 30px;
}

.wild-config-modal__close:hover {
  background: #373a41;
  color: #ffffff;
}

.config-content {
  min-height: 0;
  overflow-y: auto;
  padding: 20px 22px;
  scrollbar-color: #555b66 transparent;
  scrollbar-width: thin;
}

.config-section {
  margin-bottom: 20px;
  position: relative;
}

.config-label {
  display: block;
  margin-bottom: 8px;
  color: #f0f2f5;
  font-size: 14px;
  font-weight: 500;
}

.config-input {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid #3e4249;
  border-radius: 6px;
  background: #1e2024;
  color: #e8ebef;
  font-size: 14px;
  outline: none;
  transition: border-color 0.15s;
}

.config-input:focus {
  border-color: #3aaed8;
}

.config-input::placeholder {
  color: #7a7e87;
}

.config-hint {
  margin-top: 6px;
  color: #8a8f99;
  font-size: 12px;
  line-height: 1.5;
}

.config-divider {
  height: 1px;
  margin: 24px 0;
  background: #393c43;
}

.current-config {
  padding: 14px 16px;
  border: 1px solid #393d45;
  border-radius: 8px;
  background: #2b2e34;
}

.config-item {
  display: flex;
  margin-bottom: 8px;
}

.config-item:last-child {
  margin-bottom: 0;
}

.config-key {
  min-width: 80px;
  color: #aeb3bd;
  font-size: 13px;
}

.config-value {
  color: #e8ebef;
  font-size: 13px;
}

.config-scope-warning {
  margin-bottom: 18px;
  padding: 9px 11px;
  border: 1px solid rgba(240, 179, 90, 0.28);
  border-radius: 6px;
  background: rgba(240, 179, 90, 0.08);
  color: #d9b77d;
  font-size: 12px;
  line-height: 1.5;
}

.config-path {
  overflow-wrap: anywhere;
}

.config-persistent {
  color: #6fcf97;
}

.config-volatile {
  color: #f0b35a;
}

.wild-config-modal__footer {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 22px 18px;
  border-top: 1px solid #393c43;
}

.test-result {
  margin-left: 12px;
  font-size: 13px;
  font-weight: 500;
}

.test-success {
  color: #52c41a;
}

.test-error {
  color: #ff4d4f;
  max-width: 300px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.btn-primary,
.btn-secondary {
  min-width: 80px;
  padding: 8px 16px;
  border: 1px solid;
  border-radius: 5px;
  cursor: pointer;
  font-size: 13px;
  transition: all 0.15s;
}

.btn-primary {
  border-color: #168bc2;
  background: #137fac;
  color: #ffffff;
}

.btn-primary:hover:not(:disabled) {
  border-color: #35bfe8;
  background: #1593c7;
}

.btn-secondary {
  border-color: #3e4249;
  background: #2b2e34;
  color: #cdd1d8;
}

.btn-secondary:hover:not(:disabled) {
  background: #373a41;
  color: #ffffff;
}

.btn-primary:disabled,
.btn-secondary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.wild-config-modal-enter-active,
.wild-config-modal-leave-active {
  transition: opacity 0.16s ease;
}

.wild-config-modal-enter-active .wild-config-modal__panel,
.wild-config-modal-leave-active .wild-config-modal__panel {
  transition: transform 0.16s ease, opacity 0.16s ease;
}

.wild-config-modal-enter-from,
.wild-config-modal-leave-to {
  opacity: 0;
}

.wild-config-modal-enter-from .wild-config-modal__panel,
.wild-config-modal-leave-to .wild-config-modal__panel {
  opacity: 0;
  transform: translateY(8px) scale(0.985);
}

@media (max-width: 680px) {
  .wild-config-modal__overlay {
    padding: 12px;
  }

  .wild-config-modal__panel {
    width: calc(100vw - 24px);
    max-height: 92vh;
  }

  .wild-config-modal__header,
  .config-content,
  .wild-config-modal__footer {
    padding-right: 16px;
    padding-left: 16px;
  }
}
</style>
