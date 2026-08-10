<template>
  <details class="execution-panel" :open="turn.status === 'running'">
    <summary class="execution-summary">
      <span :class="['status-mark', `status-${turn.status}`]">
        <span v-if="turn.status === 'running'" class="spinner"></span>
        <span v-else-if="turn.status === 'completed'">✓</span>
        <span v-else>!</span>
      </span>
      <span class="summary-title">{{ summaryTitle }}</span>
      <span class="summary-meta">{{ summaryMeta }}</span>
      <span class="summary-chevron">›</span>
    </summary>

    <div class="execution-body">
      <div v-if="turn.interruption_reason" class="interruption-notice">
        {{ turn.interruption_reason }}
      </div>
      <details
        v-for="step in turn.steps"
        :key="step.node"
        class="execution-step"
        :open="step.status === 'running'"
      >
        <summary class="step-summary">
          <span :class="['step-dot', `status-${step.status}`]"></span>
          <span class="step-label">{{ step.label }}</span>
          <span class="step-detail">{{ step.detail }}</span>
          <span class="step-state">{{ statusLabel(step.status) }}</span>
        </summary>
        <div v-if="step.thinking" class="step-thinking">
          <div class="thinking-label">
            {{ step.thinking_channel === 'progress' ? '执行说明' : '模型过程' }}
          </div>
          <div class="thinking-content" v-html="renderMarkdown(step.thinking)"></div>
        </div>
        <div v-if="step.diagnostic" class="step-diagnostics">
          <span v-if="step.diagnostic.rag_chars">RAG {{ step.diagnostic.rag_chars }} 字</span>
          <span v-if="step.diagnostic.llm_ms">LLM {{ formatDuration(step.diagnostic.llm_ms) }}</span>
          <span v-if="step.diagnostic.fragment_count !== undefined">
            {{ step.diagnostic.fragment_count }} 个结果
          </span>
          <span v-if="step.diagnostic.token_usage">
            {{ step.diagnostic.token_usage.total }} tokens
          </span>
          <details v-if="step.diagnostic.rag_hits?.length" class="rag-trace">
            <summary>命中 {{ step.diagnostic.rag_hits.length }} 条知识</summary>
            <div
              v-for="(hit, index) in step.diagnostic.rag_hits"
              :key="`${hit.source}:${hit.heading}:${index}`"
              class="rag-hit"
            >
              <span>{{ hit.heading || '未命名片段' }}</span>
              <span>{{ hit.source }}</span>
            </div>
          </details>
        </div>
      </details>

      <div v-if="turn.steps.length === 0" class="execution-empty">正在准备执行计划…</div>

      <details v-if="turn.validation_steps.length" class="validation-details">
        <summary>
          校验 {{ turn.validation_steps.length }} 步
          <span v-if="validationErrorCount" class="validation-error">
            · {{ validationErrorCount }} 个错误
          </span>
        </summary>
        <div
          v-for="(step, index) in turn.validation_steps"
          :key="`${index}-${step.label}`"
          :class="['validation-line', `status-${step.status}`]"
        >
          {{ step.label }}
        </div>
      </details>

      <details v-if="turn.metrics" class="developer-details">
        <summary>运行诊断</summary>
        <div class="metrics-grid">
          <span>节点 {{ turn.metrics.active_nodes }}/{{ turn.metrics.node_count }}</span>
          <span>RAG {{ formatDuration(turn.metrics.total_rag_ms) }}</span>
          <span>LLM {{ formatDuration(turn.metrics.total_llm_ms) }}</span>
          <span>Token {{ turn.metrics.total_tokens?.total || 0 }}</span>
          <span>校验错误 {{ turn.metrics.validation_errors }}</span>
          <span v-if="turn.metrics.retry_count !== undefined">
            重试 {{ turn.metrics.retry_count }}/{{ turn.metrics.max_retries || 3 }}
          </span>
        </div>
      </details>
    </div>
  </details>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import MarkdownIt from 'markdown-it'
import type { AgentTurn } from '../../types/agent'

const props = defineProps<{ turn: AgentTurn }>()
const clock = ref(Date.now())
let timer: number | undefined

const md = new MarkdownIt({ html: false, breaks: true, linkify: false })

const durationMs = computed(() => {
  const end = props.turn.completed_at || clock.value
  return Math.max(0, end - props.turn.started_at)
})

const summaryTitle = computed(() => {
  if (props.turn.status === 'running') return '正在处理'
  if (props.turn.status === 'error') return '处理未完成'
  return '处理完成'
})

const summaryMeta = computed(() => {
  const completed = props.turn.steps.filter(step => step.status === 'done').length
  const total = props.turn.steps.length
  const count = total ? `${completed}/${total} 步` : '准备中'
  return `${count} · ${formatDuration(durationMs.value)}`
})

const validationErrorCount = computed(() =>
  props.turn.validation_steps.filter(step => step.status === 'error').length,
)

function renderMarkdown(content: string): string {
  return md.render(content)
}

function statusLabel(status: string): string {
  return ({ running: '进行中', done: '完成', skipped: '跳过', error: '失败' } as Record<string, string>)[status] || status
}

function formatDuration(ms: number): string {
  if (ms < 1000) return `${Math.max(0, Math.round(ms))}ms`
  return `${(ms / 1000).toFixed(ms < 10_000 ? 1 : 0)}s`
}

onMounted(() => {
  timer = window.setInterval(() => { clock.value = Date.now() }, 1000)
})

onUnmounted(() => {
  if (timer !== undefined) window.clearInterval(timer)
})
</script>

<style scoped>
.execution-panel {
  width: min(88%, 760px);
  margin: -8px 0 2px;
  color: #c7c7ce;
  border-left: 2px solid rgba(104, 153, 212, 0.35);
}

.execution-summary,
.step-summary {
  list-style: none;
  cursor: pointer;
  user-select: none;
}

.execution-summary::-webkit-details-marker,
.step-summary::-webkit-details-marker {
  display: none;
}

.execution-summary {
  min-height: 34px;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 5px 10px;
  font-size: 12px;
  border-radius: 0 8px 8px 0;
  background: rgba(255, 255, 255, 0.025);
}

.execution-summary:hover {
  background: rgba(255, 255, 255, 0.045);
}

.status-mark {
  width: 18px;
  height: 18px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: #6bbf9b;
  font-weight: 700;
}

.status-mark.status-error { color: #e07060; }
.summary-title { color: #dedee3; font-weight: 600; }
.summary-meta { color: #777781; }
.summary-chevron { margin-left: auto; color: #777781; transition: transform .18s; }
.execution-panel[open] > .execution-summary .summary-chevron { transform: rotate(90deg); }

.spinner {
  width: 12px;
  height: 12px;
  border: 2px solid rgba(104, 153, 212, 0.25);
  border-top-color: #6899d4;
  border-radius: 50%;
  animation: spin .8s linear infinite;
}

.execution-body {
  padding: 5px 8px 8px 16px;
}

.interruption-notice {
  margin: 4px 0 8px;
  padding: 7px 9px;
  color: #d59a91;
  background: rgba(224, 112, 96, .08);
  border-radius: 6px;
  font-size: 11px;
}

.execution-step {
  border-bottom: 1px solid rgba(255, 255, 255, 0.035);
}

.step-summary {
  min-height: 32px;
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
}

.step-dot {
  width: 6px;
  height: 6px;
  flex: 0 0 auto;
  border-radius: 50%;
  background: #777781;
}
.step-dot.status-running { background: #6899d4; box-shadow: 0 0 0 3px rgba(104, 153, 212, .12); }
.step-dot.status-done { background: #6bbf9b; }
.step-dot.status-error { background: #e07060; }
.step-dot.status-skipped { background: #55555e; }

.step-label { color: #d2d2d8; font-weight: 550; white-space: nowrap; }
.step-detail { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: #777781; }
.step-state { margin-left: auto; color: #777781; font-size: 10.5px; white-space: nowrap; }

.step-thinking {
  margin: 0 0 8px 14px;
  padding: 8px 10px;
  border-radius: 6px;
  background: rgba(0, 0, 0, .14);
  color: #a8a8b0;
}

.thinking-label {
  margin-bottom: 5px;
  color: #707079;
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: .06em;
}

.thinking-content {
  font-size: 11.5px;
  line-height: 1.65;
  overflow-wrap: anywhere;
}

.thinking-content :deep(p) { margin: 3px 0; }
.thinking-content :deep(ul), .thinking-content :deep(ol) { margin: 4px 0; padding-left: 18px; }
.thinking-content :deep(code) { color: #d7a98c; font-family: Consolas, monospace; }

.step-diagnostics,
.metrics-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 12px;
  margin: 0 0 8px 14px;
  color: #6f6f79;
  font-size: 10.5px;
}

.rag-trace {
  flex-basis: 100%;
}

.rag-trace > summary {
  cursor: pointer;
  color: #85858e;
}

.rag-hit {
  display: grid;
  grid-template-columns: minmax(100px, 1fr) minmax(120px, 1.4fr);
  gap: 8px;
  padding: 3px 0 0 10px;
}

.rag-hit span:last-child {
  overflow: hidden;
  color: #5f5f68;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.validation-details,
.developer-details {
  margin-top: 7px;
  padding-top: 7px;
  border-top: 1px solid rgba(255, 255, 255, .04);
  color: #85858e;
  font-size: 11px;
}

.validation-details > summary,
.developer-details > summary { cursor: pointer; }
.validation-error, .validation-line.status-error { color: #e07060; }
.validation-line { padding: 3px 0 0 12px; color: #777781; }
.validation-line.status-warn { color: #d4b871; }
.validation-line.status-ok { color: #6bbf9b; }
.execution-empty { padding: 8px 0; color: #777781; font-size: 11px; }
.metrics-grid { margin: 7px 0 0 12px; }

@keyframes spin { to { transform: rotate(360deg); } }
</style>
