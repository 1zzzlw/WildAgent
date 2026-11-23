import assert from 'node:assert/strict'
import { createPinia } from 'pinia'
import { createServer } from 'vite'

const vite = await createServer({ server: { middlewareMode: true }, appType: 'custom', logLevel: 'error' })
const thinkingKey = 'wild_graph_thinking_mode'
const detailKey = 'wild_detail_level'
const shaderKey = 'wild_procedural_materials_enabled'
const historyKey = 'wild_msgs_session_example:guest'
const history = '[{"id":"existing-message"}]'
const saved = new Map([[historyKey, history]])
let quotaExceeded = false
const storage = {
  getItem(key) { return saved.get(key) ?? null },
  setItem(key, value) {
    if (quotaExceeded) throw new DOMException('Storage is full', 'QuotaExceededError')
    saved.set(key, value)
  },
}
let storageBlocked = false
Object.defineProperty(globalThis, 'localStorage', {
  configurable: true,
  get() {
    if (storageBlocked) throw new DOMException('Storage is unavailable', 'SecurityError')
    return storage
  },
})

try {
  const { useAgentStore } = await vite.ssrLoadModule('/src/stores/agentStore.ts')
  const store = useAgentStore(createPinia())
  assert.deepEqual([store.thinkingMode, store.detailLevel, store.proceduralMaterialsEnabled], [false, 'minimal', false])

  quotaExceeded = true
  store.setThinkingMode(true)
  store.setDetailLevel('standard')
  store.setProceduralMaterialsEnabled(true)
  assert.deepEqual([store.thinkingMode, store.detailLevel, store.proceduralMaterialsEnabled], [true, 'standard', true])
  assert.deepEqual([...saved], [[historyKey, history]])

  quotaExceeded = false
  store.setThinkingMode(true)
  store.setDetailLevel('detailed')
  store.setProceduralMaterialsEnabled(true)
  assert.deepEqual([saved.get(thinkingKey), saved.get(detailKey), saved.get(shaderKey)], ['true', 'detailed', 'true'])
  const restored = useAgentStore(createPinia())
  assert.deepEqual([restored.thinkingMode, restored.detailLevel, restored.proceduralMaterialsEnabled], [true, 'detailed', true])

  storageBlocked = true
  const blocked = useAgentStore(createPinia())
  assert.deepEqual([blocked.thinkingMode, blocked.detailLevel, blocked.proceduralMaterialsEnabled], [false, 'minimal', false])
  blocked.setThinkingMode(true)
  assert.equal(blocked.thinkingMode, true)
  console.log('Agent 偏好回归通过：配额耗尽、历史保留、恢复持久化、存储不可用')
} finally {
  delete globalThis.localStorage
  await vite.close()
}
