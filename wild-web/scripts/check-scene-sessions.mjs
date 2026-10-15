import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import ts from 'typescript'
import { parse, compileScript, compileTemplate } from '@vue/compiler-sfc'
import { createPinia, setActivePinia } from 'pinia'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const projectRequire = createRequire(path.join(root, 'package.json'))
const storage = new Map()
globalThis.localStorage = {
  getItem: key => storage.get(key) ?? null,
  setItem: (key, value) => storage.set(key, String(value)),
  removeItem: key => storage.delete(key),
}
const messages = []
let input
globalThis.document = { createElement: () => (input = { click() {} }) }
const scene = {
  document: null,
  validate: () => [],
  async loadBlueprint(blueprint, name) {
    this.document = { id: name, name, revision: 1, blueprint, dirty: false }
    return true
  },
  markSaved() { this.document.dirty = false },
}
const history = { clear() {} }
const modules = new Map()
function load(file) {
  file = path.resolve(root, 'src', file)
  if (!path.extname(file)) file += '.ts'
  if (file.endsWith('stores/sceneStore.ts') || file.endsWith('stores\\sceneStore.ts')) {
    return { useSceneStore: () => scene }
  }
  if (file.endsWith('stores/historyStore.ts') || file.endsWith('stores\\historyStore.ts')) {
    return { useHistoryStore: () => history }
  }
  if (file.endsWith('.vue') && !/EditorTopBar|SessionListPanel/.test(file)) return { default: {} }
  if (modules.has(file)) return modules.get(file).exports
  const module = { exports: {} }
  modules.set(file, module)
  let source = readFileSync(file, 'utf8')
  if (file.endsWith('.vue')) {
    const { descriptor, errors } = parse(source, { filename: file })
    assert.deepEqual(errors, [])
    const script = compileScript(descriptor, { id: file })
    assert.deepEqual(compileTemplate({ source: descriptor.template.content, filename: file,
      id: file, compilerOptions: { bindingMetadata: script.bindings } }).errors, [])
    source = script.content
  }
  const js = ts.transpileModule(source.replaceAll('import.meta.hot', 'undefined'), { compilerOptions: {
    target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS, esModuleInterop: true,
  } }).outputText
  new Function('require', 'module', 'exports', js)(specifier => {
    if (specifier.endsWith('/style/css')) return {}
    if (specifier === 'element-plus') return {
      ...projectRequire(specifier),
      ElMessage: { success: text => messages.push(text), error: text => messages.push(text) },
    }
    return specifier.startsWith('.') ? load(path.resolve(path.dirname(file), specifier)) : projectRequire(specifier)
  }, module, module.exports)
  return module.exports
}

setActivePinia(createPinia())
const { useAgentStore } = load('stores/agentStore.ts')
const { agentBridge } = load('agent/agentBridge.ts')
const agent = useAgentStore()
agent.switchToSession('session_100')
const toolbar = load('components/layout/EditorTopBar.vue').default.setup({}, { expose() {} })
const blueprint = { meta: { version: '1.0', type: 'building', name: '导入建筑' },
  geometry: { elements: [] }, materials: {} }
async function openFile(content) {
  toolbar.handleOpen()
  await input.onchange({ target: { files: [{ name: 'external.wild', text: async () => content }] } })
}

await openFile('{invalid json')
assert.equal(agent.currentSessionId, 'session_100', '无效文件不应切换会话')
await openFile(JSON.stringify(blueprint))
const importedId = agent.currentSessionId
assert.notEqual(importedId, 'session_100', '本地导入使用独立会话')
assert.equal(scene.document.dirty, true, '未经编辑的本地文件也可以保存')
assert.equal(agent.sessions.find(s => s.session_id === importedId).status, 'draft')

const files = new Map()
const requests = []
let saveOK = false
globalThis.fetch = async (url, options) => {
  requests.push({ url, options })
  if (options?.method === 'PUT') {
    if (saveOK) files.set(url, JSON.parse(options.body))
    return { ok: saveOK, status: saveOK ? 200 : 503 }
  }
  return { ok: files.has(url), json: async () => files.get(url) }
}
await toolbar.handleSave()
assert.equal(scene.document.dirty, true, '保存失败仍可重试')
assert.equal(agent.sessions.find(s => s.session_id === importedId).filename, undefined)
saveOK = true
await toolbar.handleSave()
assert.equal(scene.document.dirty, false)
const imported = agent.sessions.find(s => s.session_id === importedId)
assert.equal(imported.status, 'saved', '空蓝图也应记录已保存状态')
assert.ok(imported.filename.includes(importedId))
assert.ok(!imported.filename.includes('session_100'), '导入不能覆盖原会话')
assert.deepEqual((await agentBridge.loadSessionBlueprint(importedId)).meta, blueprint.meta,
  '保存后可以按记录的路径重新打开')
const savedPath = requests.find(r => r.options?.method === 'PUT').url
scene.document.blueprint.meta.name = '改名后的建筑'
scene.document.dirty = true
await toolbar.handleSave()
assert.equal(requests.at(-1).url, savedPath, '再次保存沿用同一文件路径')

let finishSave
globalThis.fetch = () => new Promise(resolve => { finishSave = resolve })
scene.document.dirty = true
const saving = toolbar.handleSave()
agent.switchToSession('session_200')
await scene.loadBlueprint({ ...blueprint, meta: { ...blueprint.meta, name: '其他草稿' } }, '其他草稿')
scene.document.dirty = true
finishSave({ ok: true })
await saving
assert.equal(scene.document.dirty, true, '迟到的保存响应不能把新会话草稿标为已保存')
assert.equal(agent.sessions.find(s => s.session_id === 'session_200').status, 'draft')

const events = []
const picker = load('components/panels/SessionListPanel.vue').default.setup({}, {
  expose() {}, emit: (...args) => events.push(args),
})
const previousOrder = agent.sessions.map(s => s.session_id)
picker.openPicker()
assert.equal(picker.pickerVisible.value, true)
picker.searchQuery.value = '  SESSION_100  '
assert.deepEqual(picker.filteredSessions.value.map(s => s.session_id), ['session_100'])
picker.searchQuery.value = '不存在的名称'
assert.equal(picker.filteredSessions.value.length, 0)
picker.openPicker()
assert.equal(picker.searchQuery.value, '')
assert.deepEqual(agent.sessions.map(s => s.session_id), previousOrder, '列表排序不应修改 Store 顺序')
picker.selectSession(importedId)
assert.deepEqual(events.at(-1), ['switch', importedId])
assert.equal(picker.pickerVisible.value, false)
picker.createSession()
assert.deepEqual(events.at(-1), ['new'])
console.log('场景导入、保存重试、重新打开、保存期间切换及会话搜索检查通过')
