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
      <span class="summary-chevron">›</span>
    </summary>

    <div class="execution-body">
      <div v-if="turn.interruption_reason" class="interruption-notice">
        {{ turn.interruption_reason }}
      </div>
      <section v-if="turn.execution_plan" class="execution-plan-review" :class="{ active: isPlanReview }">
        <div class="execution-plan-header">
          <strong>执行计划 v{{ turn.execution_plan.version }}</strong>
          <span>
            {{ plannerSourceLabel(turn.execution_plan.planner_source) }}
            · {{ planStatusLabel(turn.execution_plan.status) }}
          </span>
        </div>
        <div class="execution-plan-goal">{{ turn.execution_plan.goal }}</div>
        <div v-if="turn.execution_plan.planner_summary" class="execution-plan-summary">
          {{ turn.execution_plan.planner_summary }}
        </div>
        <div v-if="turn.execution_plan.change_summary?.length" class="plan-change-summary">
          <strong>本版变化</strong>
          <span v-for="item in turn.execution_plan.change_summary" :key="item">{{ item }}</span>
        </div>
        <div v-if="turn.execution_plan.dynamic_tasks?.length" class="dynamic-plan-tasks">
          <div class="plan-section-title">本次建筑任务</div>
          <div
            v-for="task in turn.execution_plan.dynamic_tasks"
            :key="task.id"
            :class="['dynamic-plan-task', `plan-${task.status}`]"
          >
            <span class="plan-step-mark">{{ planStepMark(task.status) }}</span>
            <span class="plan-step-main">
              <strong>{{ task.title }}</strong>
              <small>{{ task.objective }}</small>
              <em>依据：{{ task.basis }}</em>
              <em>验收：{{ task.acceptance.join('；') }}</em>
            </span>
            <span class="plan-phase">{{ planPhaseLabel(task.phase) }}</span>
          </div>
        </div>
        <details class="plan-constraints">
          <summary>系统安全主流程（{{ turn.execution_plan.steps.length }} 步）</summary>
          <div class="execution-plan-steps">
            <div
              v-for="step in turn.execution_plan.steps"
              :key="step.id"
              :class="['execution-plan-step', `plan-${step.status}`]"
            >
              <span class="plan-step-mark">{{ planStepMark(step.status) }}</span>
              <span class="plan-step-main">
                <strong>{{ step.title }}</strong>
                <small>{{ step.detail || step.description }}</small>
              </span>
              <span class="plan-permission">{{ step.permission === 'read' ? '分析/审核' : '写入产物' }}</span>
            </div>
          </div>
        </details>
        <details class="plan-constraints">
          <summary>不可绕过的约束</summary>
          <div v-for="constraint in turn.execution_plan.constraints" :key="constraint">· {{ constraint }}</div>
        </details>
        <div v-if="turn.execution_feedback_queued_count" class="floor-plan-note">
          已排队 {{ turn.execution_feedback_queued_count }} 条运行中意见，将在下一节点边界处理。
        </div>
        <div v-if="isPlanReview" class="floor-plan-actions">
          <button
            type="button"
            class="confirm-plan-btn"
            :disabled="!turn.execution_plan.valid"
            @click="$emit('confirm-execution-plan', turn.request_id)"
          >批准计划并开始执行</button>
          <span>批准前不会生成三维</span>
        </div>
        <div v-if="isPlanReview" class="floor-plan-revision">
          <textarea
            v-model="planFeedback"
            rows="3"
            placeholder="例如：先检查玻璃幕墙材质能力；底部改为三层商业基座；保留平面确认步骤。"
          ></textarea>
          <button
            type="button"
            class="revise-plan-btn"
            :disabled="!planFeedback.trim()"
            @click="submitPlanRevision"
          >根据意见重新制定计划</button>
        </div>
      </section>
      <details v-if="floorPlanImageUrl" class="floor-plan-preview" open>
        <summary>
          平面方案（审核版）
          <span>· {{ floorPlanSummary }}</span>
        </summary>
        <div class="floor-plan-note">红色为门、蓝色为窗；平面确认前可以在聊天输入框反复发送修改意见。</div>
        <div v-if="floorPlanLevels.length > 1" class="level-tabs">
          <button
            v-for="item in floorPlanLevels"
            :key="item.level"
            type="button"
            :class="{ active: item.level === selectedLevel }"
            @click="selectedLevel = item.level"
          >第 {{ item.level }} 层</button>
        </div>
        <img :src="floorPlanImageUrl" :alt="`建筑第 ${selectedLevel} 层平面审核图`" />
        <div v-if="turn.floor_plan_notice" class="floor-plan-notice">
          {{ turn.floor_plan_notice }}
        </div>
        <details v-if="floorPlanRuleFindings.length" class="floor-plan-rules">
          <summary>
            工程预审 {{ floorPlanRuleFindings.length }} 项
            <span v-if="floorPlanRuleFailureCount" class="validation-error">· {{ floorPlanRuleFailureCount }} 项未通过</span>
          </summary>
          <div
            v-for="(finding, index) in floorPlanRuleFindings"
            :key="`${finding.gate}-${finding.entity_id || index}`"
            :class="['validation-line', finding.passed ? 'status-ok' : 'status-error']"
          >
            {{ finding.passed ? '✓' : '!' }} {{ ruleGateLabel(finding.gate) }}：{{ finding.message }}
          </div>
          <div class="floor-plan-note">方案阶段辅助检查，不替代所在地法定施工图审查。</div>
        </details>
        <div v-if="!turn.floor_plan_can_confirm && turn.floor_plan_fallback_reason" class="floor-plan-warning">
          当前是不可确认的降级轮廓：{{ turn.floor_plan_fallback_reason }}。请在输入框说明问题，让 Agent 重新生成。
        </div>
        <div v-if="isFloorReview" class="floor-plan-actions">
          <button
            v-if="turn.floor_plan_can_confirm"
            type="button"
            class="confirm-plan-btn"
            @click="$emit('confirm-floor-plan', turn.request_id)"
          >确认平面并生成三维</button>
          <button
            v-else
            type="button"
            class="retry-plan-btn"
            @click="$emit('retry-floor-plan', turn.request_id)"
          >重新生成可确认方案</button>
          <span>版本 {{ (turn.floor_plan_revision || 0) + 1 }}</span>
        </div>
        <div v-if="isFloorReview" class="floor-plan-revision">
          <textarea
            v-model="revisionFeedback"
            rows="3"
            placeholder="例如：把厨房移到北侧；主卧增加南向窗；一层改成 L 形，并保留中庭。"
          ></textarea>
          <button
            type="button"
            class="revise-plan-btn"
            :disabled="!revisionFeedback.trim()"
            @click="submitRevision"
          >按修改意见重新设计平面</button>
          <div class="floor-plan-note">
            修改意见会回到同一个平面设计节点生成新版本；也可以直接在聊天输入框发送修改要求。
          </div>
        </div>
      </details>
      <section v-if="turn.style_options?.length" class="style-review" :class="{ active: isStyleReview }">
        <div class="style-review-title">建筑风格（二次确认）</div>
        <div class="floor-plan-note">
          主体 G1-G6 已通过。请选择风格；确认后才会装配屋顶外观、檐口、入口雨棚和柱列，并执行 G7。
        </div>
        <label
          v-for="option in turn.style_options"
          :key="option.id"
          :class="['style-option', { selected: selectedStyleId === option.id }]"
        >
          <input
            v-model="selectedStyleId"
            type="radio"
            :value="option.id"
            :disabled="!isStyleReview"
          />
          <span><strong>{{ option.name }}</strong><small>{{ option.description }}</small></span>
        </label>
        <div v-if="isStyleReview" class="style-actions">
          <button
            type="button"
            class="confirm-plan-btn"
            :disabled="!selectedStyleId"
            @click="$emit('confirm-style', turn.request_id, selectedStyleId)"
          >确认风格并完成三维</button>
          <span>版本 {{ (turn.style_revision || 0) + 1 }}</span>
        </div>
        <div v-if="isStyleReview" class="floor-plan-revision">
          <textarea
            v-model="styleFeedback"
            rows="2"
            placeholder="例如：改成新中式，屋檐更明显；或者改成克制的欧式风格。"
          ></textarea>
          <button
            type="button"
            class="revise-plan-btn"
            :disabled="!styleFeedback.trim()"
            @click="submitStyleRevision"
          >按意见调整风格</button>
        </div>
      </section>
      <details
        v-for="step in turn.steps"
        :key="step.node"
        :id="`agent-step-${turn.turn_id}-${step.node}`"
        class="execution-step"
        :open="step.status === 'running' || (turn.status === 'waiting_review' && step.node === 'floor_plan_design')"
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
          <span v-if="turn.metrics.plan_mode">
            计划 v{{ turn.metrics.plan_version || 1 }} · 重规划 {{ turn.metrics.plan_replan_count || 0 }} 次
          </span>
        </div>
      </details>
    </div>
  </details>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import MarkdownIt from 'markdown-it'
import type { AgentTurn } from '../../types/agent'

const props = defineProps<{ turn: AgentTurn }>()
const emit = defineEmits<{
  (event: 'confirm-floor-plan', requestId: string): void
  (event: 'retry-floor-plan', requestId: string): void
  (event: 'revise-floor-plan', requestId: string, feedback: string): void
  (event: 'confirm-style', requestId: string, stylePackageId: string): void
  (event: 'revise-style', requestId: string, feedback: string): void
  (event: 'confirm-execution-plan', requestId: string): void
  (event: 'revise-execution-plan', requestId: string, feedback: string): void
}>()
const clock = ref(Date.now())
const selectedLevel = ref('1')
const revisionFeedback = ref('')
const styleFeedback = ref('')
const selectedStyleId = ref('')
const planFeedback = ref('')
let timer: number | undefined

const md = new MarkdownIt({ html: false, breaks: true, linkify: false })

const durationMs = computed(() => {
  const end = props.turn.completed_at || clock.value
  return Math.max(0, end - props.turn.started_at)
})

const summaryTitle = computed(() => {
  if (props.turn.status === 'running') return '正在处理'
  if (isPlanReview.value) return '等待批准执行计划'
  if (isStyleReview.value) return '等待确认建筑风格'
  if (props.turn.status === 'waiting_review') return '等待确认平面'
  if (props.turn.status === 'error') return '处理未完成'
  return '处理完成'
})

const isFloorReview = computed(() =>
  props.turn.status === 'waiting_review' && props.turn.floor_plan_review_status === 'pending',
)
const isStyleReview = computed(() =>
  props.turn.status === 'waiting_review' && props.turn.style_review_status === 'pending',
)
const isPlanReview = computed(() =>
  props.turn.status === 'waiting_review'
  && props.turn.execution_plan_review_status === 'pending',
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

const floorPlanLevels = computed(() => {
  const svgs = props.turn.floor_plan_svgs || {}
  const entries = Object.entries(svgs)
    .sort(([left], [right]) => Number(left) - Number(right))
    .map(([level, svg]) => ({ level, svg }))
  if (!entries.length && props.turn.floor_plan_svg) {
    entries.push({ level: '1', svg: props.turn.floor_plan_svg })
  }
  return entries
})

const floorPlanImageUrl = computed(() => {
  const svg = floorPlanLevels.value.find(item => item.level === selectedLevel.value)?.svg
    || floorPlanLevels.value[0]?.svg
  return svg ? `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}` : ''
})

watch(floorPlanLevels, levels => {
  if (levels.length && !levels.some(item => item.level === selectedLevel.value)) {
    selectedLevel.value = levels[0].level
  }
}, { immediate: true })

watch(
  () => [props.turn.request_id, props.turn.floor_plan_revision],
  () => { revisionFeedback.value = '' },
)

watch(
  () => [props.turn.request_id, props.turn.style_revision, props.turn.selected_style_id] as const,
  () => {
    styleFeedback.value = ''
    selectedStyleId.value = props.turn.selected_style_id || props.turn.style_options?.[0]?.id || ''
  },
  { immediate: true },
)

watch(
  () => [props.turn.request_id, props.turn.execution_plan?.version] as const,
  () => { planFeedback.value = '' },
)

function submitRevision() {
  const feedback = revisionFeedback.value.trim()
  if (!feedback) return
  emit('revise-floor-plan', props.turn.request_id, feedback)
  revisionFeedback.value = ''
}

function submitStyleRevision() {
  const feedback = styleFeedback.value.trim()
  if (!feedback) return
  emit('revise-style', props.turn.request_id, feedback)
  styleFeedback.value = ''
}

function submitPlanRevision() {
  const feedback = planFeedback.value.trim()
  if (!feedback) return
  emit('revise-execution-plan', props.turn.request_id, feedback)
  planFeedback.value = ''
}

function planStepMark(status: string): string {
  return ({
    pending: '·',
    in_progress: '→',
    completed: '✓',
    failed: '!',
    skipped: '–',
  } as Record<string, string>)[status] || '·'
}

function planStatusLabel(status: string): string {
  return ({
    draft: '草案', reviewing: '待审核', approved: '已批准',
    executing: '执行中', revising: '重新规划', completed: '已完成', failed: '失败',
  } as Record<string, string>)[status] || status
}

function plannerSourceLabel(source?: string): string {
  if (source === 'llm') return '模型动态规划'
  if (source === 'fallback') return '语义回退计划'
  return '兼容计划'
}

function planPhaseLabel(phase: string): string {
  return ({
    architecture: '总体方案',
    floor_plan_design: '平面设计',
    material_plan: '材质方案',
    skeleton: '主体装配',
    decor_assembly: '装饰装配',
    final_validate: '最终校验',
    patch: '场景修改',
  } as Record<string, string>)[phase] || phase
}

const floorPlanSummary = computed(() => {
  const plan = props.turn.floor_plan
  if (!plan) return '等待空间数据'
  const levels = Array.isArray(plan.levels) ? plan.levels : []
  const spaceCount = levels.reduce((total, level) => {
    if (!level || typeof level !== 'object') return total
    const spaces = (level as Record<string, unknown>).spaces
    return total + (Array.isArray(spaces) ? spaces.length : 0)
  }, 0)
  const source = plan.source === 'model'
    ? '模型方案'
    : plan.source === 'deterministic_template' ? '确定性基础方案' : '安全回退'
  return `${levels.length} 层 · ${spaceCount} 个空间 · ${source}`
})

interface FloorPlanRuleFinding {
  gate: string
  passed: boolean
  message: string
  entity_id?: string | null
}

const floorPlanRuleFindings = computed<FloorPlanRuleFinding[]>(() => {
  const report = props.turn.floor_plan?.rule_review
  if (!report || typeof report !== 'object') return []
  const findings = (report as Record<string, unknown>).findings
  return Array.isArray(findings) ? findings.filter((item): item is FloorPlanRuleFinding => (
    !!item && typeof item === 'object'
    && typeof (item as FloorPlanRuleFinding).gate === 'string'
    && typeof (item as FloorPlanRuleFinding).passed === 'boolean'
    && typeof (item as FloorPlanRuleFinding).message === 'string'
  )) : []
})

const floorPlanRuleFailureCount = computed(() =>
  floorPlanRuleFindings.value.filter(item => !item.passed).length,
)

function ruleGateLabel(gate: string): string {
  return ({
    elevator: '电梯覆盖',
    egress: '疏散距离',
    daylight: '采光面积',
    symmetry: '轴线对称',
    opening_corner: '洞口距墙角',
    functional_flow: '功能流线',
  } as Record<string, string>)[gate] || gate
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

.execution-plan-review {
  display: grid;
  gap: 8px;
  margin: 4px 0 10px;
  padding: 10px;
  border: 1px solid rgba(104, 153, 212, .2);
  border-radius: 7px;
  background: rgba(104, 153, 212, .035);
}

.execution-plan-review.active { border-color: rgba(250, 204, 21, .38); }
.execution-plan-header { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.execution-plan-header strong { color: #dedee3; font-size: 12px; }
.execution-plan-header span { color: #9ca3af; font-size: 10.5px; }
.execution-plan-goal { color: #aeb7c7; font-size: 11px; line-height: 1.5; }
.execution-plan-summary {
  padding: 7px 8px;
  color: #b9c8dc;
  font-size: 10.5px;
  line-height: 1.55;
  border-left: 2px solid rgba(104, 153, 212, .55);
  background: rgba(104, 153, 212, .06);
}
.plan-change-summary { display: grid; gap: 2px; color: #a8afba; font-size: 10px; }
.plan-change-summary strong, .plan-section-title { color: #d8d8dd; font-size: 10.5px; }
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
.dynamic-plan-task.plan-in_progress { border-color: rgba(104, 153, 212, .38); background: rgba(104, 153, 212, .12); }
.dynamic-plan-task.plan-completed .plan-step-mark { color: #6bbf9b; }
.dynamic-plan-task.plan-failed .plan-step-mark { color: #e07060; }
.dynamic-plan-task .plan-step-main small { white-space: normal; }
.plan-step-main em { color: #697789; font-size: 9.5px; font-style: normal; line-height: 1.4; }
.plan-phase { color: #7f9dc0; font-size: 9.5px; white-space: nowrap; }
.execution-plan-steps { display: grid; gap: 4px; }
.execution-plan-step {
  display: grid;
  grid-template-columns: 16px minmax(0, 1fr) auto;
  gap: 7px;
  align-items: start;
  padding: 6px 7px;
  border-radius: 5px;
  background: rgba(255, 255, 255, .025);
}
.execution-plan-step.plan-in_progress { background: rgba(104, 153, 212, .12); }
.execution-plan-step.plan-completed .plan-step-mark { color: #6bbf9b; }
.execution-plan-step.plan-failed .plan-step-mark { color: #e07060; }
.plan-step-mark { color: #8aa8cf; font-weight: 700; }
.plan-step-main { display: grid; min-width: 0; gap: 2px; }
.plan-step-main strong { color: #d8d8dd; font-size: 11px; }
.plan-step-main small { overflow: hidden; color: #777781; font-size: 10px; text-overflow: ellipsis; white-space: nowrap; }
.plan-permission { color: #687386; font-size: 9.5px; }
.plan-constraints { color: #85858e; font-size: 10.5px; }
.plan-constraints > summary { cursor: pointer; }
.plan-constraints > div { padding: 3px 0 0 10px; }

.interruption-notice {
  margin: 4px 0 8px;
  padding: 7px 9px;
  color: #d59a91;
  background: rgba(224, 112, 96, .08);
  border-radius: 6px;
  font-size: 11px;
}

.floor-plan-preview {
  margin: 4px 0 8px;
  padding: 8px 10px 10px;
  border: 1px solid rgba(250, 204, 21, .16);
  border-radius: 7px;
  background: rgba(250, 204, 21, .025);
}

.style-review {
  display: grid;
  gap: 7px;
  margin: 4px 0 9px;
  padding: 9px 10px;
  border: 1px solid rgba(104, 153, 212, .16);
  border-radius: 7px;
  background: rgba(104, 153, 212, .025);
}

.style-review.active { border-color: rgba(250, 204, 21, .32); }
.style-review-title { color: #d8d8dd; font-size: 11.5px; font-weight: 600; }
.style-option {
  display: flex;
  gap: 7px;
  align-items: flex-start;
  padding: 7px 8px;
  border: 1px solid rgba(255, 255, 255, .06);
  border-radius: 6px;
  cursor: pointer;
}
.style-option.selected { border-color: rgba(104, 153, 212, .58); background: rgba(104, 153, 212, .1); }
.style-option input { margin-top: 2px; }
.style-option span { display: grid; gap: 2px; }
.style-option strong { color: #d8d8dd; font-size: 11.5px; }
.style-option small { color: #777781; font-size: 10.5px; line-height: 1.4; }
.style-actions { display: flex; align-items: center; justify-content: space-between; color: #777781; font-size: 10.5px; }

.floor-plan-preview > summary {
  cursor: pointer;
  color: #d8d8dd;
  font-size: 11.5px;
  font-weight: 600;
}

.floor-plan-preview > summary span,
.floor-plan-note {
  color: #777781;
  font-weight: 400;
}

.floor-plan-note {
  margin: 6px 0;
  font-size: 10.5px;
}

.floor-plan-preview img {
  display: block;
  width: 100%;
  max-height: 360px;
  object-fit: contain;
  border-radius: 5px;
  background: #111118;
}

.level-tabs,
.floor-plan-actions {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 7px 0;
}

.level-tabs button,
.confirm-plan-btn,
.retry-plan-btn,
.revise-plan-btn {
  border: 1px solid rgba(104, 153, 212, .35);
  border-radius: 5px;
  padding: 4px 9px;
  color: #aeb7c7;
  background: rgba(104, 153, 212, .08);
  cursor: pointer;
}

.level-tabs button.active {
  color: #e5e7eb;
  border-color: #6899d4;
  background: rgba(104, 153, 212, .2);
}

.floor-plan-warning {
  margin-top: 7px;
  padding: 7px 9px;
  color: #e6b36a;
  border-radius: 5px;
  background: rgba(230, 179, 106, .08);
  font-size: 10.5px;
}

.floor-plan-notice {
  margin-top: 7px;
  padding: 7px 9px;
  color: #d8c386;
  border-radius: 5px;
  background: rgba(216, 195, 134, .08);
  font-size: 10.5px;
  line-height: 1.5;
}

.floor-plan-actions {
  justify-content: space-between;
  color: #777781;
  font-size: 10.5px;
}

.confirm-plan-btn {
  color: #dff6e9;
  border-color: rgba(107, 191, 155, .5);
  background: rgba(107, 191, 155, .13);
}

.retry-plan-btn {
  color: #f3d9a3;
  border-color: rgba(230, 179, 106, .5);
  background: rgba(230, 179, 106, .12);
}

.floor-plan-revision {
  display: grid;
  gap: 6px;
  margin-top: 9px;
  padding-top: 9px;
  border-top: 1px solid rgba(255, 255, 255, .06);
}

.floor-plan-revision textarea {
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

.floor-plan-revision textarea:focus {
  border-color: rgba(104, 153, 212, .72);
}

.revise-plan-btn {
  justify-self: start;
  color: #dbeafe;
}

.confirm-plan-btn:disabled,
.revise-plan-btn:disabled {
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

.floor-plan-rules,
.validation-details,
.developer-details {
  margin-top: 7px;
  padding-top: 7px;
  border-top: 1px solid rgba(255, 255, 255, .04);
  color: #85858e;
  font-size: 11px;
}

.floor-plan-rules > summary,
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
