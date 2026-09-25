<template>
  <details class="execution-panel" :open="turn.status === 'running' || turn.status === 'waiting_review'">
    <summary class="execution-summary">
      <span :class="['status-mark', `status-${turn.status}`]">
        <span v-if="turn.status === 'running'" class="spinner"></span>
        <span v-else-if="turn.status === 'waiting_review'">?</span>
        <span v-else-if="turn.status === 'completed'">✓</span>
        <span v-else>!</span>
      </span>
      <span class="summary-title">{{ summaryTitle }}</span>
      <span class="summary-meta">{{ summaryMeta }}</span>
      <button
        v-if="turn.plan"
        type="button"
        class="plan-window-toggle"
        @click.prevent.stop="planWindowOpen = !planWindowOpen"
      >{{ planWindowOpen ? '收起计划' : '查看计划' }}</button>
      <span class="summary-chevron">›</span>
    </summary>

    <div class="execution-body">
      <div v-if="turn.interruption_reason" class="interruption-notice">
        {{ turn.interruption_reason }}
      </div>
      <section v-if="turn.design_document" class="design-review" :class="{ active: isDesignReview }">
        <div class="execution-plan-header">
          <strong>{{ architectureDecisions ? '建筑设计' : '物件方案' }} r{{ turn.design_document.revision }}</strong>
          <span>{{ designStatusLabel(turn.design_document.status) }}</span>
        </div>
        <div class="design-concept">{{ turn.design_document.decisions.concept }}</div>
        <!-- 建筑与物件是 decisions 带标签联合的两支，字段不重叠：
             模板必须按 kind 收窄后再读，否则读 massing 会直接抛异常。 -->
        <div v-if="architectureDecisions" class="design-facts">
          <span>{{ architectureDecisions.massing.width }} × {{ architectureDecisions.massing.depth }}m</span>
          <span>{{ architectureDecisions.massing.floors }} 层</span>
          <span>{{ architectureDecisions.volumes.length }} 个体量</span>
          <span>{{ architectureDecisions.envelope.system }}</span>
          <span>{{ architectureDecisions.roof.type }} 屋顶</span>
          <span v-if="designMaterialConcept">{{ designMaterialConcept }}</span>
        </div>
        <div v-else-if="objectDecisions" class="design-facts">
          <span>{{ objectDecisions.objects.length }} 类物件</span>
          <span>共 {{ objectCount }} 件</span>
          <span v-if="designMaterialConcept">{{ designMaterialConcept }}</span>
        </div>
        <div v-if="objectDecisions" class="design-objects">
          <div
            v-for="(item, index) in objectDecisions.objects"
            :key="`${item.kind}-${item.subtype}-${index}`"
            class="design-object"
          >
            <span class="object-name">{{ item.subtype || item.kind }} × {{ item.count }}</span>
            <span class="object-size">
              {{ item.width.toFixed(2) }} × {{ item.depth.toFixed(2) }} × {{ item.height.toFixed(2) }}m
            </span>
            <span v-if="item.placement" class="object-placement">{{ item.placement }}</span>
          </div>
        </div>
        <a
          v-if="turn.design_preview_url"
          class="design-preview-link"
          :href="turn.design_preview_url"
          target="_blank"
          rel="noopener noreferrer"
          title="在新窗口查看原始 SVG"
        >
          <img
            :src="turn.design_preview_url"
            :alt="architectureDecisions ? '建筑体量、主立面和侧立面设计预览' : '物件轮廓与尺寸预览'"
          />
        </a>
        <details class="design-details">
          <summary>设计约束与构件计划</summary>
          <div v-for="constraint in turn.design_document.constraints" :key="constraint.id">
            <strong>{{ constraint.kind }}</strong> · {{ constraint.expression }}
          </div>
          <div
            v-if="architectureDecisions"
            class="design-quota"
          >
            <span
              v-for="(quota, component) in architectureDecisions.component_quota"
              :key="component"
            >{{ component }} {{ quota.min }}–{{ quota.max }}</span>
          </div>
          <div v-else-if="objectDecisions" class="design-quota">
            <span
              v-for="(item, index) in objectDecisions.objects"
              :key="`quota-${item.kind}-${item.subtype}-${index}`"
            >{{ item.subtype || item.kind }} × {{ item.count }}</span>
          </div>
        </details>
        <div v-if="isDesignReview" class="review-actions">
          <button
            type="button"
            class="confirm-design-btn"
            @click="$emit('confirm-design', turn.request_id)"
          >批准此设计并生成 Blueprint</button>
          <span>Blueprint 将绑定设计 revision 和 hash</span>
        </div>
        <div v-if="isDesignReview" class="review-revision">
          <textarea
            v-model="designFeedback"
            rows="3"
            :placeholder="architectureDecisions
              ? '例如：塔楼向后退 2 米；主立面改为非对称；保留层数并减少窗格密度。'
              : '例如：桌子改宽到 1.8 米；四把椅子面向桌面；木色改深一点。'"
          ></textarea>
          <button
            type="button"
            class="revise-design-btn"
            :disabled="!designFeedback.trim()"
            @click="submitDesignRevision"
          >根据意见生成下一版设计</button>
        </div>
      </section>
      <details
        v-for="step in turn.steps"
        :key="step.node"
        :id="`agent-step-${turn.turn_id}-${step.node}`"
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
            修复轮次 {{ turn.metrics.retry_count }}（每目标最多 {{ turn.metrics.max_retries || 3 }} 次）
          </span>
        </div>
      </details>
    </div>
  </details>

  <Teleport to="body">
    <aside
      v-if="turn.plan && planWindowOpen"
      class="plan-floating-window"
      role="dialog"
      aria-label="执行计划"
    >
      <header class="plan-floating-header">
        <div>
          <strong>执行计划</strong>
          <span>{{ planCounts.done }}/{{ planCounts.total }} 完成</span>
        </div>
        <div class="plan-floating-actions">
          <button type="button" @click="planWindowMinimized = !planWindowMinimized">
            {{ planWindowMinimized ? '展开' : '最小化' }}
          </button>
          <button type="button" aria-label="关闭执行计划" @click="planWindowOpen = false">×</button>
        </div>
      </header>
      <template v-if="!planWindowMinimized">
        <div class="plan-floating-meta">
          <span>档位 {{ turn.plan.detail_level }}</span>
          <span>第 {{ turn.plan.iterations || 0 }} 轮</span>
          <span>{{ planBatchCount }} 个生成批次</span>
          <span v-if="planParallelGroups">{{ planParallelGroups }} 个并发组</span>
        </div>
        <div v-if="planShortfall.length" class="plan-change-summary">
          <strong>待处理 {{ planShortfall.length }} 条</strong>
        </div>
        <div class="dynamic-plan-tasks plan-floating-tasks">
          <div
            v-for="item in turn.plan.items"
            :key="item.id"
            :class="['dynamic-plan-task', `plan-${item.status}`]"
          >
            <span class="plan-step-mark">{{ planItemMark(item.status) }}</span>
            <span class="plan-step-main">
              <strong>{{ item.label || item.id }}</strong>
              <small>{{ planItemDetail(item) }}</small>
              <small v-if="planExecutionLabel(item)" class="plan-execution-mode">
                {{ planExecutionLabel(item) }}
              </small>
            </span>
            <span class="plan-phase">{{ item.op }}</span>
          </div>
        </div>
      </template>
    </aside>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import MarkdownIt from 'markdown-it'
import type { AgentTurn, PlanItem } from '../../types/agent'

const props = defineProps<{ turn: AgentTurn }>()
const emit = defineEmits<{
  (event: 'confirm-design', requestId: string): void
  (event: 'revise-design', requestId: string, feedback: string): void
}>()
const clock = ref(Date.now())
const designFeedback = ref('')
const planWindowOpen = ref(false)
const planWindowMinimized = ref(false)
const planAutoOpenedForRequest = ref('')
let timer: number | undefined

const md = new MarkdownIt({ html: false, breaks: true, linkify: false })

const durationMs = computed(() => {
  const end = props.turn.completed_at || clock.value
  return Math.max(0, end - props.turn.started_at)
})

const summaryTitle = computed(() => {
  if (props.turn.status === 'running') return '正在处理'
  if (isDesignReview.value) return '等待批准建筑设计'
  if (props.turn.status === 'waiting_review') return '等待用户确认'
  if (props.turn.status === 'error') return '处理未完成'
  return '处理完成'
})

const isDesignReview = computed(() =>
  props.turn.status === 'waiting_review'
  && props.turn.design_review_status === 'pending',
)

const summaryMeta = computed(() => {
  const completed = props.turn.steps.filter(step => step.status === 'done').length
  const total = props.turn.steps.length
  const count = total ? `${completed}/${total} 步` : '准备中'
  return `${count} · ${formatDuration(durationMs.value)}`
})

const validationErrorCount = computed(() =>
  props.turn.validation_steps.filter(step => step.status === 'error').length,
)

const designMaterialConcept = computed(() => {
  const plan = props.turn.design_document?.decisions.materials.resolved_plan
  return typeof plan?.concept === 'string' ? plan.concept : ''
})

// decisions 是带标签联合：模板必须先按 kind 收窄再读字段。
// 直接读 decisions.massing 在物件方案上会抛异常（那支根本没有 massing）。
const architectureDecisions = computed(() => {
  const decisions = props.turn.design_document?.decisions
  return decisions?.kind === 'architecture' ? decisions : null
})

const objectDecisions = computed(() => {
  const decisions = props.turn.design_document?.decisions
  return decisions?.kind === 'object' ? decisions : null
})

const objectCount = computed(() =>
  (objectDecisions.value?.objects ?? []).reduce((total, item) => total + (item.count ?? 0), 0),
)

watch(
  () => [props.turn.request_id, props.turn.design_document?.revision] as const,
  () => {
    designFeedback.value = ''
  },
)

watch(
  () => props.turn.plan,
  (plan) => {
    if (
      plan
      && props.turn.status === 'running'
      && planAutoOpenedForRequest.value !== props.turn.request_id
    ) {
      planWindowOpen.value = true
      planAutoOpenedForRequest.value = props.turn.request_id
    }
  },
  { immediate: true },
)

function submitDesignRevision() {
  const feedback = designFeedback.value.trim()
  if (!feedback) return
  emit('revise-design', props.turn.request_id, feedback)
  designFeedback.value = ''
}

function designStatusLabel(status: string): string {
  return ({ draft: '草案', approved: '已批准', compiled: '已编译' } as Record<string, string>)[status] || status
}

const planCounts = computed(() => {
  const items = props.turn.plan?.items || []
  return {
    total: items.length,
    done: items.filter(item => item.status === 'done').length,
  }
})

const planShortfall = computed(() =>
  (props.turn.plan?.items || []).filter(item => item.status !== 'done'),
)

const planBatchCount = computed(() =>
  (props.turn.plan?.items || []).filter(item => item.op === 'generate').length,
)

const planParallelGroups = computed(() => new Set(
  (props.turn.plan?.items || [])
    .map(item => item.params?.parallel_group)
    .filter((group): group is string => Boolean(group)),
).size)

function planItemMark(status: string): string {
  return ({
    pending: '·',
    ready: '·',
    blocked: '·',
    done: '✓',
    abandoned: '!',
    skipped: '–',
    unsupported: '?',
  } as Record<string, string>)[status] || '·'
}

function planItemDetail(item: PlanItem): string {
  const evidence = item.run?.evidence || ''
  const attempts = item.run?.attempts ? `（已尝试 ${item.run.attempts} 次）` : ''
  const strategy = String(item.params?.batch_reason || item.params?.reason || '')
  return evidence || `${strategy}${attempts}` || attempts || '等待执行'
}

function planExecutionLabel(item: PlanItem): string {
  if (item.op !== 'generate') return ''
  const batchSize = Number(item.target?.batch_size || 1)
  const batch = batchSize > 1 ? `一次批量 ${batchSize} 个` : '单批次生成'
  const group = item.params?.parallel_group
  return group ? `${batch} · 并发组 ${group}` : `${batch} · 串行`
}

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
.status-mark.status-waiting_review { color: #facc15; }
.summary-title { color: #dedee3; font-weight: 600; }
.summary-meta { color: #777781; }
.plan-window-toggle {
  margin-left: auto;
  padding: 2px 7px;
  color: #a9c8ee;
  border: 1px solid rgba(104, 153, 212, .35);
  border-radius: 5px;
  background: rgba(104, 153, 212, .08);
  font-size: 10px;
  cursor: pointer;
}
.plan-window-toggle:hover { background: rgba(104, 153, 212, .16); }
.summary-chevron { margin-left: auto; color: #777781; transition: transform .18s; }
.plan-window-toggle + .summary-chevron { margin-left: 0; }
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

.execution-plan-review {
  display: grid;
  gap: 8px;
  margin: 4px 0 10px;
  padding: 10px;
  border: 1px solid rgba(104, 153, 212, .2);
  border-radius: 7px;
  background: rgba(104, 153, 212, .035);
}

.plan-floating-window {
  position: fixed;
  z-index: 2400;
  right: 22px;
  bottom: 86px;
  width: min(420px, calc(100vw - 32px));
  max-height: min(68vh, 720px);
  overflow: hidden;
  color: #c7c7ce;
  border: 1px solid rgba(104, 153, 212, .42);
  border-radius: 12px;
  background: rgba(18, 21, 28, .96);
  box-shadow: 0 18px 48px rgba(0, 0, 0, .48), 0 0 0 1px rgba(255, 255, 255, .025) inset;
  backdrop-filter: blur(14px);
}

.plan-floating-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 11px 12px;
  border-bottom: 1px solid rgba(255, 255, 255, .07);
  background: linear-gradient(135deg, rgba(104, 153, 212, .16), rgba(104, 153, 212, .04));
}

.plan-floating-header > div:first-child { display: grid; gap: 2px; }
.plan-floating-header strong { color: #e5edf7; font-size: 13px; }
.plan-floating-header span { color: #8ea3bb; font-size: 10px; }
.plan-floating-actions { display: flex; gap: 5px; }
.plan-floating-actions button {
  min-height: 24px;
  padding: 2px 7px;
  color: #aebdd0;
  border: 1px solid rgba(255, 255, 255, .1);
  border-radius: 5px;
  background: rgba(255, 255, 255, .035);
  font-size: 10px;
  cursor: pointer;
}
.plan-floating-actions button:hover { background: rgba(255, 255, 255, .08); }

.plan-floating-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
  padding: 9px 11px 3px;
}
.plan-floating-meta span {
  padding: 2px 6px;
  color: #9eb7d3;
  border-radius: 4px;
  background: rgba(104, 153, 212, .09);
  font-size: 9.5px;
}
.plan-floating-window > .plan-change-summary { padding: 6px 11px 0; }
.plan-floating-tasks {
  max-height: calc(min(68vh, 720px) - 104px);
  overflow-y: auto;
  padding: 7px 10px 11px;
  scrollbar-width: thin;
}
.plan-execution-mode { color: #89a9ca !important; }

@media (max-width: 720px) {
  .plan-floating-window {
    right: 8px;
    bottom: 76px;
    width: calc(100vw - 16px);
    max-height: 62vh;
  }
}

.design-review {
  display: grid;
  gap: 8px;
  margin: 4px 0 10px;
  padding: 10px;
  border: 1px solid rgba(91, 178, 142, .24);
  border-radius: 7px;
  background: rgba(91, 178, 142, .04);
}

.design-review.active { border-color: rgba(250, 204, 21, .42); }
.design-concept { color: #c7d7cf; font-size: 11px; line-height: 1.5; }
.design-facts { display: flex; flex-wrap: wrap; gap: 5px; }
.design-facts span,
.design-quota span {
  padding: 2px 6px;
  color: #aec6b9;
  border-radius: 4px;
  background: rgba(91, 178, 142, .1);
  font-size: 10px;
}
.design-preview-link { display: block; overflow: hidden; border-radius: 6px; background: #171a20; }
.design-preview-link img { display: block; width: 100%; max-height: 360px; object-fit: contain; }
.design-details { color: #929da8; font-size: 10.5px; }
.design-details > summary { cursor: pointer; color: #bac4ce; }
.design-details > div { padding-top: 4px; }
.design-details strong { color: #8fbfa9; font-size: 9.5px; }
.design-quota { display: flex; flex-wrap: wrap; gap: 4px; }

/* 物件方案：逐件列出"做几个、多大、怎么摆"——审核要看的正是这三件事。 */
.design-objects { display: grid; gap: 3px; }
.design-object {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 6px;
  padding: 3px 6px;
  border-radius: 4px;
  background: rgba(91, 178, 142, .08);
}
.object-name { color: #cfe0d5; font-size: 10.5px; }
.object-size { color: #9fb6a9; font-size: 10px; }
.object-placement { color: #8d99a4; font-size: 10px; }

.execution-plan-header { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.execution-plan-header strong { color: #dedee3; font-size: 12px; }
.execution-plan-header span { color: #9ca3af; font-size: 10.5px; }
/* 条目状态配色与后端 PlanStatus 一一对应（§2.6 计划态） */
.plan-change-summary { display: grid; gap: 2px; color: #a8afba; font-size: 10px; }
.plan-change-summary strong { color: #d8d8dd; font-size: 10.5px; }
.dynamic-plan-tasks { display: grid; gap: 5px; }
.dynamic-plan-task {
  display: grid;
  grid-template-columns: 16px minmax(0, 1fr) auto;
  gap: 7px;
  align-items: start;
  padding: 8px;
  border: 1px solid rgba(104, 153, 212, .1);
  border-radius: 6px;
  background: rgba(255, 255, 255, .025);
}
.dynamic-plan-task.plan-ready { border-color: rgba(104, 153, 212, .38); background: rgba(104, 153, 212, .12); }
.dynamic-plan-task.plan-done .plan-step-mark { color: #6bbf9b; }
.dynamic-plan-task.plan-abandoned .plan-step-mark { color: #e07060; }
.dynamic-plan-task.plan-unsupported .plan-step-mark { color: #d8b26a; }
.dynamic-plan-task .plan-step-main small { white-space: normal; }
.plan-phase { color: #7f9dc0; font-size: 9.5px; white-space: nowrap; }
.plan-step-mark { color: #8aa8cf; font-weight: 700; }
.plan-step-main { display: grid; min-width: 0; gap: 2px; }
.plan-step-main strong { color: #d8d8dd; font-size: 11px; }
.plan-step-main small { overflow: hidden; color: #777781; font-size: 10px; text-overflow: ellipsis; white-space: nowrap; }

.interruption-notice {
  margin: 4px 0 8px;
  padding: 7px 9px;
  color: #d59a91;
  background: rgba(224, 112, 96, .08);
  border-radius: 6px;
  font-size: 11px;
}

.review-actions {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 7px 0;
}

.confirm-design-btn,
.revise-design-btn {
  border: 1px solid rgba(104, 153, 212, .35);
  border-radius: 5px;
  padding: 4px 9px;
  color: #aeb7c7;
  background: rgba(104, 153, 212, .08);
  cursor: pointer;
}

.review-actions {
  justify-content: space-between;
  color: #777781;
  font-size: 10.5px;
}

.confirm-design-btn {
  color: #dff6e9;
  border-color: rgba(107, 191, 155, .5);
  background: rgba(107, 191, 155, .13);
}

.review-revision {
  display: grid;
  gap: 6px;
  margin-top: 9px;
  padding-top: 9px;
  border-top: 1px solid rgba(255, 255, 255, .06);
}

.review-revision textarea {
  width: 100%;
  box-sizing: border-box;
  resize: vertical;
  min-height: 58px;
  padding: 7px 9px;
  color: #dedee3;
  border: 1px solid rgba(104, 153, 212, .3);
  border-radius: 5px;
  outline: none;
  background: rgba(10, 12, 18, .62);
  font: inherit;
  line-height: 1.45;
}

.review-revision textarea:focus {
  border-color: rgba(104, 153, 212, .72);
}

.revise-design-btn {
  justify-self: start;
  color: #dbeafe;
}

.confirm-design-btn:disabled,
.revise-design-btn:disabled {
  opacity: .38;
  cursor: not-allowed;
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
