import assert from 'node:assert/strict'
import { mkdtemp, mkdir, readFile, writeFile } from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
import ts from 'typescript'
import { parse, compileScript } from '@vue/compiler-sfc'
import { createPinia, setActivePinia } from 'pinia'
import { createSSRApp } from 'vue'
import { renderToString } from '@vue/server-renderer'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const cacheRoot = path.join(root, 'node_modules', '.tmp')
await mkdir(cacheRoot, { recursive: true })
const cache = await mkdtemp(path.join(cacheRoot, 'agent-detail-'))

async function compile(relative, source) {
  const destination = path.join(cache, relative.replace(/\.(ts|vue)$/, '.mjs'))
  await mkdir(path.dirname(destination), { recursive: true })
  const output = ts.transpileModule(source, {
    compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext },
  }).outputText.replace(/(['"])(\.\.?\/[^'"]+)\1/g, '$1$2.mjs$1')
  await writeFile(destination, output)
  return destination
}

for (const file of ['types/agent.ts', 'stores/agentStore.ts', 'agent/protocol.ts']) {
  await compile(file, await readFile(path.join(root, 'src', file), 'utf8'))
}
const storage = new Map()
globalThis.localStorage = {
  getItem: key => storage.get(key) ?? null,
  setItem: (key, value) => storage.set(key, String(value)),
  removeItem: key => storage.delete(key),
}
const { useAgentStore } = await import(pathToFileURL(path.join(cache, 'stores/agentStore.mjs')))
const { BUILDING_DETAIL_LEVELS } = await import(pathToFileURL(path.join(cache, 'types/agent.mjs')))
const { createUserMessageRequest } = await import(pathToFileURL(path.join(cache, 'agent/protocol.mjs')))
setActivePinia(createPinia())
const store = useAgentStore()
assert.equal(store.detailLevel, 'minimal')
assert.equal(store.thinkingMode, true)
assert.ok(!('precisionMode' in store))
storage.set('wild_thinking_mode', 'false')
storage.set('wild_precision_mode', 'true')
setActivePinia(createPinia())
assert.equal(useAgentStore().thinkingMode, true)
store.setThinkingMode(false)
assert.equal(storage.get('wild_graph_thinking_mode'), 'false')
setActivePinia(createPinia())
assert.equal(useAgentStore().thinkingMode, false)
store.appendThinkingContent('节点实际思考', 'architecture')
assert.equal(store.nodeThinkingMap.get('architecture').content, '节点实际思考')
assert.deepEqual(BUILDING_DETAIL_LEVELS.map(level => level.label), ['低', '中', '高', '极高'])
for (const thinking of [false, true]) {
  store.setThinkingMode(thinking)
  for (const { value } of BUILDING_DETAIL_LEVELS) {
    store.setDetailLevel(value)
    assert.equal(storage.get('wild_detail_level'), value)
    const request = createUserMessageRequest('设计建筑', 'session', undefined, 0, {}, [], undefined,
      true, [], store.detailLevel, store.thinkingMode)
    assert.equal(request.detail_level, value)
    assert.ok(!('precision_mode' in request))
    assert.equal(request.thinking_mode, thinking)
    assert.equal(request.procedural_materials_enabled, true)
  }
}
assert.equal(createUserMessageRequest('设计建筑', 'session', undefined, 0, {}, []).thinking_mode, true)
assert.equal(createUserMessageRequest('设计建筑', 'session', undefined, 0, {}, []).detail_level, 'minimal')
setActivePinia(createPinia())
assert.equal(useAgentStore().detailLevel, 'detailed')
storage.set('wild_detail_level', 'obsolete')
setActivePinia(createPinia())
assert.equal(useAgentStore().detailLevel, 'minimal')

const turn = store.startTurn('request', 'session', '设计建筑')
store.setTurnPlan('session', 'request', {
  revision: 1, detail_level: 'detailed', items: [
    { id: 'generate_1', op: 'generate', kind: 'window', label: '窗', status: 'ready',
      params: { design_markers: true, execution_mode: 'parallel', parallel_group: 'drawing' } },
    { id: 'generate_2', op: 'generate', kind: 'roof', label: '屋顶', status: 'ready' },
  ],
})
store.appendTurnThinking('session', 'request', 'plan:generate_1', '窗的执行说明', 'progress')
store.appendTurnThinking('session', 'request', 'plan:generate_1', '窗的模型思考', 'reasoning')
store.appendTurnThinking('session', 'request', 'plan:generate_2', '屋顶的模型思考', 'reasoning')
store.updateTurnStep('session', 'request', {
  node: 'plan:generate_1', label: '窗', stage: 'generating', status: 'done', detail: '落实 1',
})
assert.equal(turn.steps[0].thinking, '窗的执行说明')
assert.equal(turn.steps[0].reasoning, '窗的模型思考')
assert.equal(turn.steps[1].reasoning, '屋顶的模型思考')
assert.equal(turn.steps[0].status, 'done')
assert.equal(turn.steps[1].status, 'running')

const panelPath = path.join(root, 'src/components/panels/AgentExecutionPanel.vue')
const { descriptor } = parse(await readFile(panelPath, 'utf8'), { filename: panelPath })
const compiled = compileScript(descriptor, { id: 'detail-check', inlineTemplate: true })
const componentPath = await compile('components/panels/AgentExecutionPanel.vue', compiled.content)
const { default: Panel } = await import(pathToFileURL(componentPath))
const context = {}
await renderToString(createSSRApp(Panel, { turn }), context)
const planHtml = context.teleports.body
assert.ok(planHtml.includes('粒度：极高'))
assert.ok(planHtml.includes('单批次生成 · 最多 3 项并发'))
assert.ok(planHtml.includes('单批次生成 · 串行'))
assert.ok(planHtml.includes('窗的执行说明') && planHtml.includes('窗的模型思考'))
assert.ok(planHtml.includes('屋顶的模型思考'))
const rows = planHtml.split('class="plan-item-thinking"').slice(1)
assert.equal(rows.length, 2)
assert.ok(!rows[0].slice(0, rows[0].indexOf('>')).includes('open'))
assert.ok(rows[1].slice(0, rows[1].indexOf('>')).includes('open'))
console.log('通过：四档请求与持久化、条目思考隔离、并发标签、结束后保留、真实 Vue 组件渲染与展开状态。')
