import assert from 'node:assert/strict'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { createServer } from 'vite'
import { createSSRApp } from 'vue'
import { renderToString } from '@vue/server-renderer'
import { createPinia, setActivePinia } from 'pinia'
import ElementPlus, { ID_INJECTION_KEY, ZINDEX_INJECTION_KEY } from 'element-plus'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const storage = new Map()
globalThis.localStorage = {
  getItem: key => storage.get(key) ?? null,
  setItem: (key, value) => storage.set(key, String(value)),
  removeItem: key => storage.delete(key),
}
globalThis.WebSocket = { OPEN: 1 }
const writes = []
globalThis.fetch = async (url, options) => {
  if (options?.body) writes.push({ url, body: JSON.parse(options.body) })
  return { ok: true }
}
const server = await createServer({ root, logLevel: 'error', server: { middlewareMode: true }, appType: 'custom' })
try {
  const { useAgentStore } = await server.ssrLoadModule('/src/stores/agentStore.ts')
  const { useSceneStore } = await server.ssrLoadModule('/src/stores/sceneStore.ts')
  const { agentBridge: bridge } = await server.ssrLoadModule('/src/agent/agentBridge.ts')
  const { default: Panel } = await server.ssrLoadModule('/src/components/panels/AIChatPanel.vue')
  const pinia = createPinia()
  setActivePinia(pinia)
  const store = useAgentStore()
  const scene = useSceneStore()
  scene.document = { id: 'scene', revision: 0, blueprint: {
    meta: { name: 'test' }, geometry: { elements: [], components: [] }, materials: {}, assets: {},
  } }
  const sent = []
  bridge.ws = { readyState: 1, send: data => sent.push(JSON.parse(data)) }
  store.setConnectionStatus('connected')
  store.setThinkingMode(false)
  store.switchToSession('session_other')
  const otherId = bridge.sendUserMessage('另一个会话')
  assert.ok(otherId)
  assert.equal(sent.at(-1).thinking_mode, false)
  store.switchToSession('session_stop')

  async function button() {
    const app = createSSRApp(Panel).use(pinia).use(ElementPlus)
    app.provide(ID_INJECTION_KEY, { prefix: 1024, current: 0 })
    app.provide(ZINDEX_INJECTION_KEY, { current: 0 })
    const html = await renderToString(app)
    const result = html.match(/<button\b[^>]*class="[^"]*\bsend-btn\b[^>]*>[\s\S]*?<\/button>/)
    assert.ok(result, '实际聊天面板应有发送/停止按钮')
    return result[0]
  }

  assert.ok((await button()).includes('发送'))
  const requestId = bridge.sendUserMessage('生成别墅')
  assert.ok(requestId)
  assert.equal(sent.at(-1).thinking_mode, false)
  const turn = store.currentTurns[0]
  store.appendTurnThinking(turn.session_id, requestId, 'architecture', '已有模型输出', 'reasoning')
  const runningButton = await button()
  assert.ok(runningButton.includes('停止') && runningButton.includes('stop-btn'))
  assert.ok(!/^<button[^>]*\bdisabled/.test(runningButton), '输入框为空时，停止仍可点击')
  assert.equal(bridge.stopCurrentGeneration(), true)
  assert.equal(bridge.stopCurrentGeneration(), false, '停止等待期间不应重复提交')
  assert.deepEqual(sent.at(-1), {
    protocol_version: '1.0', type: 'stop_generation', request_id: requestId, session_id: 'session_stop',
  })
  const waitingButton = await button()
  assert.ok(waitingButton.includes('停止中') && /^<button[^>]*\bdisabled/.test(waitingButton))
  const pending = JSON.parse(storage.get('wild_turns_session_stop'))[0]
  assert.equal(pending.stop_requested, true)
  assert.equal(pending.steps[0].reasoning, '已有模型输出')
  const ack = { type: 'generation_stopped', request_id: requestId, session_id: 'session_stop',
    status: 'stopped', content: '已停止，已有执行记录已保存。' }
  bridge.handleMessage(ack)
  const messageCount = store.session.messages.length
  const stoppedAt = turn.completed_at
  bridge.handleMessage(ack)
  assert.equal(store.session.messages.length, messageCount, '重复确认不应重复添加停止消息')
  assert.equal(turn.status, 'stopped')
  assert.equal(turn.completed_at, stoppedAt)
  assert.equal(turn.steps[0].status, 'stopped')
  assert.equal(turn.steps[0].reasoning, '已有模型输出')
  assert.equal(store.getTurnsForSession('session_other')[0].status, 'running')
  assert.ok((await button()).includes('发送'))
  assert.equal(JSON.parse(storage.get('wild_turns_session_stop'))[0].status, 'stopped')
  await bridge.syncConversationState('session_stop')
  assert.ok(writes.some(write => write.body.turns?.some(item => item.status === 'stopped')))
  store.switchToSession('session_other')
  store.setTurnStopRequested('session_other', otherId, true)
  bridge.resumeActiveGenerations()
  assert.equal(sent.at(-1).type, 'stop_generation')
  assert.equal(sent.at(-1).request_id, otherId, '重连后只重发尚未确认的停止请求')
  setActivePinia(createPinia())
  const restored = useAgentStore()
  restored.switchToSession('session_stop')
  assert.equal(restored.currentTurns[0].status, 'stopped')
  assert.equal(restored.currentTurns[0].steps[0].reasoning, '已有模型输出')
  console.log('通过：实际发送后切换停止按钮、空输入可停止、防重复点击、会话隔离、停止确认与本地/服务端快照、重连重发、刷新恢复。')
} finally {
  await server.close()
}
