import assert from 'node:assert/strict'
import { fileURLToPath } from 'node:url'
import { createServer } from 'vite'
import { launchEditorBrowser } from './editor-browser.mjs'

const server = await createServer({
  root: fileURLToPath(new URL('..', import.meta.url)),
  server: { host: '127.0.0.1', port: 5186, strictPort: true },
})
let browser
try {
  await server.listen()
  browser = await launchEditorBrowser('http://127.0.0.1:5186/scripts/presentation-preview.html')
  await browser.page.wait('window.ready')
  const result = await browser.page.evaluate(`(async () => {
    const {nextTick} = await import('/node_modules/.vite/deps/vue.js')
    const client = await import('/src/renderer/reconstructionClient.ts')
    const {validateBlueprint} = await import('/src/wild/sceneValidator.ts')
    const {useWorkspaceStore} = await import('/src/stores/workspaceStore.ts')
    const {useAgentStore} = await import('/src/stores/agentStore.ts')
    const {useAuthStore} = await import('/src/stores/authStore.ts')
    const {agentBridge} = await import('/src/agent/agentBridge.ts')
    const {scene, render} = window.presentationTest
    const auth = useAuthStore(), agent = useAgentStore(), workspace = useWorkspaceStore()
    const check = (value, message) => { if (!value) throw Error(message) }
    auth.user = {id:'loading-test', username:'loading-test', identity:2, role:'editor'}
    await nextTick()
    render.entranceEnabled = false
    const blueprint = (name, radius = .5) => ({
      meta:{version:'1.0', type:'building', name},
      geometry:{elements:[{id:'sphere', type:'primitive', shape:'sphere', position:[0,1,0], radius, material:'stone'}]},
      materials:{stone:{baseColor:[.5,.4,.3], roughness:.7, metallic:0, albedo:1}}
    })
    let workerRequests = 0, terminatedWorkers = 0
    const post = Worker.prototype.postMessage, terminate = Worker.prototype.terminate
    Worker.prototype.postMessage = function(message, ...args) {
      if (message.blueprintJson) workerRequests++
      return post.call(this, message, ...args)
    }
    Worker.prototype.terminate = function(...args) { terminatedWorkers++; return terminate.apply(this, args) }
    const fetchOriginal = window.fetch
    try {
      client.clearReconstructionCache()
      const a = blueprint('A'), b = blueprint('B', .8)
      check(await scene.loadBlueprint(a), 'A 加载失败')
      await nextTick()
      const first = scene.reconstructed
      check(JSON.stringify(scene.validationIssues) === JSON.stringify(validateBlueprint(a)), 'Worker 校验结果改变')
      check(await scene.loadBlueprint(b), 'B 加载失败')
      const beforeRepeat = workerRequests
      check(await scene.loadBlueprint(a), '重复加载 A 失败')
      check(scene.reconstructed === first && workerRequests === beforeRepeat, '切回 A 没有复用重建结果')
      const previousDocument = scene.document.id
      check(await scene.loadBlueprint(a), '相同蓝图再次打开失败')
      await nextTick()
      const viewport = document.querySelector('.canvas-viewport').__vueParentComponent.setupState
      check(scene.document.id !== previousDocument && viewport.hasFramedScene, '相同缓存结果没有重置新会话视口')
      const changed = blueprint('A', .9)
      check(await scene.loadBlueprint(changed), '修改后的 A 加载失败')
      check(scene.reconstructed !== first && workerRequests === beforeRepeat + 1, '蓝图内容变化没有失效缓存')

      client.clearReconstructionCache()
      const same = blueprint('coalesced')
      const beforeShared = workerRequests
      const [sharedA, sharedB] = await Promise.all([client.reconstructScene(same), client.reconstructScene(same)])
      check(sharedA === sharedB && workerRequests === beforeShared + 1, '相同并发请求没有合并')
      client.clearReconstructionCache()
      const recent = []
      for (const name of ['lru-a','lru-b','lru-c','lru-d']) recent.push(await client.reconstructScene(blueprint(name)))
      check(await client.reconstructScene(blueprint('lru-d')) === recent[3], '近期结果没有保留')
      check(await client.reconstructScene(blueprint('lru-a')) !== recent[0], '缓存未淘汰旧场景')

      const slow = blueprint('cancelled')
      slow.geometry.elements.push(...Array.from({length:8000}, (_, i) => ({id:'slow-'+i, type:'primitive', shape:'box', position:[i%100,0,Math.floor(i/100)], dimensions:[.2,.2,.2]})))
      const abandoned = scene.loadBlueprint(slow)
      const latest = scene.loadBlueprint(blueprint('latest'))
      check(await abandoned === false && await latest === true, '过期 Worker 结果覆盖了新场景')
      check(scene.document.name === 'latest' && terminatedWorkers > 0, '离开的场景仍在 Worker 排队')

      const sources = {session_load_a:blueprint('Session A'), session_load_b:blueprint('Session B')}
      const versions = {session_load_a:1, session_load_b:1}
      const events = [], messageGates = []
      let slowBlueprint = '', failBlueprint = '', notModified = 0, bodies = 0, aborted = 0
      const wait = (signal, done, delay) => new Promise((resolve, reject) => {
        const finish = () => { signal?.removeEventListener('abort', abort); resolve(done()) }
        const timer = delay === undefined ? undefined : setTimeout(finish, delay)
        const abort = () => { clearTimeout(timer); aborted++; reject(new DOMException('cancelled', 'AbortError')) }
        signal?.addEventListener('abort', abort, {once:true})
        if (delay === undefined) messageGates.push(finish)
        if (signal?.aborted) abort()
      })
      window.fetch = async (input, init = {}) => {
        const path = new URL(String(input), location.href).pathname
        if (path.startsWith('/api/sessions/')) {
          const id = path.split('/')[3]
          events.push({path, started:performance.now()})
          return wait(init.signal, () => new Response(JSON.stringify(path.endsWith('/messages')
            ? [{id:'message-'+id, role:'agent', content:'restored', timestamp:1}] : [])), undefined)
        }
        if (path.startsWith('/api/scenes/')) {
          const id = path.split('/').pop().replace('.wild','')
          events.push({path, started:performance.now()})
          const respond = () => {
            if (id === failBlueprint || auth.user?.id !== 'loading-test') return new Response('{}', {status:503})
            const etag = '"' + id + ':' + versions[id] + '"'
            if (new Headers(init.headers).get('If-None-Match') === etag) {
              notModified++; return new Response(null, {status:304, headers:{ETag:etag}})
            }
            bodies++; return new Response(JSON.stringify(sources[id]), {headers:{ETag:etag}})
          }
          return wait(init.signal, respond, id === slowBlueprint ? 300 : 5)
        }
        return fetchOriginal(input, init)
      }
      agent.replaceSessions(Object.keys(sources).map(id => ({session_id:id, filename:id+'.wild', name:id, status:'saved', created_at:1, updated_at:1, elements_count:1})))
      render.entranceEnabled = true
      const opening = workspace.openSession('session_load_a')
      check(scene.isLoading && !scene.canModify, '读取新会话期间仍允许编辑旧蓝图')
      const opened = await Promise.race([opening, new Promise((_, reject) => setTimeout(() => reject(Error('蓝图等待聊天记录')), 5000))])
      check(opened && agent.currentSessionId === 'session_load_a', '会话 A 未打开')
      const assembly = viewport.worldRuntime.getInstance('editor:active-blueprint').assembly
      check(!assembly.active, '历史会话重复播放组装动画')
      render.requestReplayEntrance()
      await nextTick()
      check(assembly.active, '历史会话不能手动重播入场动画')
      viewport.finishEntrance()
      check(!agent.session.messages.some(m => m.id === 'message-session_load_a'), '聊天记录没有独立恢复')
      const starts = events.slice(0, 3).map(e => e.started)
      check(Math.max(...starts) - Math.min(...starts) < 50, '请求没有并行发起')
      messageGates.splice(0).forEach(release => release())
      await new Promise(resolve => setTimeout(resolve, 20))
      check(agent.session.messages.some(m => m.id === 'message-session_load_a'), '后台聊天记录没有合并')
      await workspace.openSession('session_load_b')
      await workspace.openSession('session_load_a')
      check(notModified > 0 && bodies === 2, '重复切换仍下载蓝图正文')
      const oldEntity = scene.reconstructed
      versions.session_load_a++
      sources.session_load_a = blueprint('Session A updated', .95)
      await workspace.openSession('session_load_a')
      check(scene.document.name === 'Session A updated' && scene.reconstructed !== oldEntity, '服务端变更没有刷新缓存')

      slowBlueprint = 'session_load_b'
      const oldLoad = workspace.openSession('session_load_b')
      const newestLoad = workspace.openSession('session_load_a')
      check(await oldLoad === false && await newestLoad === true, '快速切换没有取消旧请求')
      check(agent.currentSessionId === 'session_load_a' && aborted > 0, '迟到响应覆盖了当前会话')
      failBlueprint = 'session_load_b'; slowBlueprint = ''
      check(await workspace.openSession('session_load_b') === false, '失败的蓝图被当成空场景加载')
      check(agent.currentSessionId === 'session_load_a' && scene.document.name === 'Session A updated', '读取失败丢失原会话')
      check(!scene.isLoading, '读取失败后加载状态未恢复')
      slowBlueprint = 'session_load_b'; failBlueprint = ''
      const accountLoad = workspace.openSession('session_load_b')
      auth.user = {id:'another-account', username:'another', role:'editor'}
      await nextTick()
      check(await accountLoad === false, '账号变更后仍采用旧请求结果')
      const rejected = await agentBridge.loadSessionBlueprint('session_load_a')
      check(rejected === null, '跨账号复用了蓝图正文缓存')
      return {cacheReused:true, changedContentInvalidated:true, coalesced:true, lruEviction:true,
        obsoleteWorkerCancelled:true, requestsParallel:true, messagesIndependent:true,
        conditionalResponses:notModified, failedLoadPreservesScene:true, accountIsolation:true,
        historyShownImmediately:true, manualEntrancePreserved:true}
    } finally {
      window.fetch = fetchOriginal
      Worker.prototype.postMessage = post
      Worker.prototype.terminate = terminate
      window.presentationTest.app.unmount()
    }
  })()`)
  assert.deepEqual(browser.page.errors, [])
  console.log(JSON.stringify({status:'PASS', ...result, browserErrors:browser.page.errors}, null, 2))
} finally {
  await browser?.close()
  await server.close()
}
