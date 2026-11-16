import assert from 'node:assert/strict'
import { fileURLToPath } from 'node:url'
import { createServer } from 'vite'
import { launchEditorBrowser } from './editor-browser.mjs'

const server = await createServer({
  root: fileURLToPath(new URL('..', import.meta.url)),
  server: { host:'127.0.0.1', port:5186, strictPort:true },
})
let browser
try {
  await server.listen()
  browser = await launchEditorBrowser('http://127.0.0.1:5186/scripts/presentation-preview.html')
  const page = browser.page
  await page.wait('window.ready')
  await page.evaluate(`(async () => {
    const {createApp, nextTick} = await import('/node_modules/.vite/deps/vue.js')
    const {useUIStore} = await import('/src/stores/uiStore.ts')
    const {useAuthStore} = await import('/src/stores/authStore.ts')
    const {useItemCatalogStore} = await import('/src/stores/itemCatalogStore.ts')
    const {agentBridge} = await import('/src/agent/agentBridge.ts')
    const {default:LeftPanel} = await import('/src/components/layout/LeftPanel.vue')
    const elements = await import('/node_modules/.vite/deps/element-plus.js')
    await import('/src/style.css')
    useAuthStore().user = {id:'lazy-panel', username:'fixture', role:'editor', identity:2}
    useUIStore().activePanel = 'aiChat'
    useUIStore().panelOpen = true
    agentBridge.fetchSessionList = async () => []
    useItemCatalogStore().load = async () => {}
    const host = document.createElement('div')
    host.style.cssText = 'position:fixed;inset:0 auto 0 0;width:460px;z-index:1000'
    document.body.append(host)
    const pinia = window.presentationTest.pinia
    if (!pinia) throw Error('测试 Pinia 未初始化')
    const app = createApp(LeftPanel).use(pinia)
    for (const name of ['ElButton','ElColorPicker','ElDropdown','ElDropdownItem','ElDropdownMenu','ElIcon','ElInput','ElInputNumber','ElOption','ElPopover','ElSelect','ElSlider','ElSwitch','ElTag']) {
      if (!elements[name]) throw Error('缺少测试组件：'+name)
      app.use(elements[name])
    }
    app.mount(host)
    window.panelLoadingApp = app
    await nextTick()
  })()`)
  assert.equal(await page.evaluate("!!document.querySelector('.library-panel,.material-workspace,.look-panel')"), false, '隐藏面板不应在启动时挂载')
  await page.click('button[aria-label="构件库"]')
  await page.wait("!!document.querySelector('.library-panel')")
  await page.evaluate("window.loadedLibrary = document.querySelector('.library-panel')")
  await page.click('.library-panel .tabs button:nth-child(2)')
  await page.wait("document.querySelector('.library-panel .tabs .active')?.textContent.includes('物品')")
  await page.click('button[aria-label="AI 对话"]')
  await page.click('button[aria-label="构件库"]')
  assert.equal(await page.evaluate("document.querySelector('.library-panel') === window.loadedLibrary && document.querySelector('.library-panel .tabs .active').textContent.includes('物品')"), true, '首次打开后应保留面板状态')
  assert.equal(await page.evaluate("!!document.querySelector('.material-workspace')"), false, '未打开材质面板时不应生成缩略图')
  await page.evaluate("window.panelLoadingApp.unmount();window.presentationTest.app.unmount()")
  assert.deepEqual(page.errors, [])
  console.log(JSON.stringify({status:'PASS', panelsLazy:true, firstOpenMounted:true, panelStateRetained:true, hiddenMaterialNotMounted:true}, null, 2))
} finally {
  await browser?.close()
  await server.close()
}
