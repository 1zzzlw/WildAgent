import assert from 'node:assert/strict'
import { createServer } from 'vite'

const vite = await createServer({ server: { middlewareMode: true }, appType: 'custom', logLevel: 'error' })
const previousDocument = globalThis.document
const players = []
let rejectPlay = false
let frameCallbacks = true
class Video extends EventTarget {
  paused = true
  ended = false
  readyState = 4
  HAVE_CURRENT_DATA = 2
  error = null
  callbacks = new Map()
  sequence = 0
  loads = 0
  constructor() {
    super()
    if (!frameCallbacks) this.requestVideoFrameCallback = undefined
    players.push(this)
  }
  play() {
    if (rejectPlay) return Promise.reject(new Error('play rejected'))
    this.paused = false
    this.dispatchEvent(new Event('play'))
    return Promise.resolve()
  }
  pause() { this.paused = true; this.dispatchEvent(new Event('pause')) }
  load() { this.loads++ }
  removeAttribute(name) { if (name === 'src') this.src = '' }
  requestVideoFrameCallback(callback) { const id = ++this.sequence; this.callbacks.set(id, callback); return id }
  cancelVideoFrameCallback(id) { this.callbacks.delete(id) }
  frame() {
    const callbacks = [...this.callbacks.values()]
    this.callbacks.clear()
    callbacks.forEach(callback => callback(0, {}))
  }
}
globalThis.document = { createElement(name) { assert.equal(name, 'video'); return new Video() } }
try {
  const compiler = await vite.ssrLoadModule('../wild-core/src/compiler/index.ts')
  const registry = await vite.ssrLoadModule('../wild-core/src/compiler/declarative/registry.ts')
  const core = await vite.ssrLoadModule('../wild-core/src/primitive/index.ts')
  const renderer = await vite.ssrLoadModule('/src/renderer/renderEntity.ts')
  const runtime = await vite.ssrLoadModule('/src/renderer/elementBehaviorRuntime.ts')
  const { MaterialCache } = await vite.ssrLoadModule('/src/renderer/materialAdapter.ts')
  const { buildComponentEntries } = await vite.ssrLoadModule('/src/wild/componentDisplay.ts')
  let renders = 0
  runtime.configureElementBehaviorRendering(() => renders++)
  const source = (src, type = 'video_screen') => ({ meta: { version: '1.1', type: 'asset', name: 'behavior' },
    geometry: { elements: [], components: [{ type, id: 'screen', position: [0, 0, 0], src }] }, materials: {} })
  const build = async input => {
    const parsed = core.parseBlueprint(JSON.stringify(input))
    const compiled = compiler.compileBlueprintComponents(parsed)
    assert.deepEqual(compiled.diagnostics, [])
    assert.ok(compiled.blueprint.materials.__wild_component_frame, '配方声明的内置默认材质必须自动补入')
    const result = await core.reconstructEntity(compiled.blueprint)
    assert.deepEqual(result.diagnostics.filter(item => item.level === 'error'), [])
    return result
  }
  assert.ok(buildComponentEntries().some(item => item.type === 'video_screen'))
  for (const src of ['C:\\video.mp4', 'file:///video.mp4', 'javascript:alert(1)']) {
    assert.ok(compiler.compileBlueprintComponents(source(src)).diagnostics.length, '拒绝不可访问的视频地址')
  }
  assert.throws(() => compiler.validateElementBehavior({ kind: 'extension', capability: 'missing', config: {} }))
  assert.throws(() => compiler.validateElementBehavior({ kind: 'extension', capability: 'video', config: { src: '', loop: 'true' } }))

  const cache = new MaterialCache(), initial = await build(source('/first.webm'))
  const group = renderer.createSceneGroupFromEntity(initial, cache)
  const screen = group.getObjectByName('screen__screen'), frame = group.getObjectByName('screen__frame')
  const first = players.at(-1), texture = screen.material.map
  assert.notEqual(screen.material, frame.material, '视频表面不能改写共享框架材质')
  assert.equal(first.crossOrigin, 'anonymous')
  assert.equal(first.muted, true)
  assert.equal(first.loop, true)
  assert.equal(first.callbacks.size, 0, '暂停的视频不创建额外帧循环')
  renderer.toggleRuntimeInteraction(screen)
  await Promise.resolve()
  assert.equal(first.paused, false)
  assert.equal(first.callbacks.size, 1)
  const version = texture.version, beforeRender = renders
  first.frame()
  assert.ok(texture.version > version && renders > beforeRender)
  assert.equal(first.callbacks.size, 1)
  assert.equal(runtime.tickElementBehaviors(group, .016), false, '有视频帧回调时不强制连续渲染')
  renderer.toggleRuntimeInteraction(screen)
  assert.equal(first.paused, true)
  renderer.updateSceneGroup(group, initial, cache)
  assert.equal(group.getObjectByName('screen__screen'), screen, '无关增量更新保留播放器与暂停状态')
  let released = false
  texture.addEventListener('dispose', () => { released = true })
  renderer.updateSceneGroup(group, await build(source('/second.webm')), cache)
  assert.equal(group.getObjectByName('screen__frame'), frame)
  assert.notEqual(group.getObjectByName('screen__screen'), screen)
  assert.equal(first.callbacks.size, 0)
  assert.equal(first.src, '')
  assert.ok(first.loads > 0 && released, '换源须释放旧播放器、纹理和回调')
  renderer.clearSceneObjectResources(group)
  cache.clear()
  assert.equal(players.at(-1).src, '')

  const blankCount = players.length
  const blank = renderer.createSceneGroupFromEntity(await build(source('')))
  assert.equal(players.length, blankCount)
  assert.match(runtime.elementBehaviorLabel(blank.getObjectByName('screen__screen')), /填写/)
  renderer.clearSceneObjectResources(blank)

  frameCallbacks = false
  const fallback = renderer.createSceneGroupFromEntity(await build(source('/fallback.webm')))
  const fallbackScreen = fallback.getObjectByName('screen__screen')
  rejectPlay = true
  renderer.toggleRuntimeInteraction(fallbackScreen)
  await Promise.resolve(); await Promise.resolve()
  assert.equal(fallbackScreen.userData.mediaState, 'error')
  rejectPlay = false
  renderer.toggleRuntimeInteraction(fallbackScreen)
  await Promise.resolve()
  assert.equal(runtime.tickElementBehaviors(fallback, .016), true, '旧浏览器复用视口 RAF 更新视频')
  renderer.toggleRuntimeInteraction(fallbackScreen)
  assert.equal(runtime.tickElementBehaviors(fallback, .016), false)
  renderer.clearSceneObjectResources(fallback)

  // 新能力通过注册接入；两种不同业务组件使用同一能力，渲染器没有按组件名称分支。
  compiler.registerExtensionBehaviorCapability({ name: 'pulse_probe', description: '测试能力', validate() {} })
  let created = 0, interacted = 0, disposed = 0
  runtime.registerElementBehaviorRuntime('pulse_probe', () => {
    created++
    return { label: 'pulse', interact() { interacted++ }, tick: () => true, dispose() { disposed++ } }
  })
  const recipe = compiler.getRecipe('video_screen')
  registry.registerRecipeCompilers(['display_probe', 'sign_probe'].map(type => ({ ...recipe, type,
    elements: recipe.elements.map(node => node.behavior
      ? { ...node, behavior: { kind: 'extension', capability: 'pulse_probe', config: {} } } : node) })))
  for (const type of ['display_probe', 'sign_probe']) {
    const root = renderer.createSceneGroupFromEntity(await build(source('', type)))
    assert.equal(runtime.elementBehaviorLabel(root.getObjectByName('screen__screen')), 'pulse')
    renderer.toggleRuntimeInteraction(root.getObjectByName('screen__screen'))
    assert.equal(runtime.tickElementBehaviors(root, .016), true)
    renderer.clearSceneObjectResources(root)
    assert.equal(runtime.tickElementBehaviors(root, .016), false)
  }
  assert.deepEqual([created, interacted, disposed], [2, 2, 2])
  console.log('PASS: 配方/材质/能力注册/播放暂停/换源释放/增量保留/帧回调降级；媒体 DOM 为替身，未冒充浏览器播放验证')
} finally {
  globalThis.document = previousDocument
  await vite.close()
}
