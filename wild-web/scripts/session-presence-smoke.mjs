import assert from 'node:assert/strict'
import { mkdir, writeFile } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import { createServer } from 'vite'
import { launchEditorBrowser } from './editor-browser.mjs'

const backend = process.env.PRESENCE_TEST_BACKEND || 'http://127.0.0.1:18080'
const info = await fetch(backend + '/api/editor-smoke-info').then(response => response.json())
assert.equal(info.database, 'sqlite', '只允许连接隔离 SQLite 回归服务')
assert.equal(info.redis, 'fakeredis', '只允许使用隔离 Redis 替身')
const output = fileURLToPath(new URL('../.workbuddy/session-presence-regression/', import.meta.url))
const server = await createServer({ root: fileURLToPath(new URL('..', import.meta.url)), server: {
  host: '127.0.0.1', port: 0, proxy: { '/api': { target: backend }, '/ws': { target: backend.replace('http:', 'ws:'), ws: true } },
} })
const checks = []
let actor, observer
try {
  await server.listen()
  const url = server.resolvedUrls.local[0] + 'scripts/session-import-preview.html'
  actor = await launchEditorBrowser(url)
  observer = await launchEditorBrowser(url)
  const a = actor.page, b = observer.page
  await Promise.all([a.wait('window.ready'), b.wait('window.ready')])
  await a.evaluate(`(async () => {
    const t=window.sessionImportTest
    await t.auth.login('lxw@example.com','123456')
    const bp=name=>({meta:{version:'1.0',type:'building',name},geometry:{elements:[{id:'sphere',type:'primitive',shape:'sphere',position:[0,.5,0],radius:.5}],components:[]},materials:{},editor:{revision:1}})
    for(const [id,name] of [['session_presencea','会话甲'],['session_presenceb','会话乙']]) {
      const response=await fetch('/api/scenes/'+id+'.wild',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(bp(name))})
      if(!response.ok) throw Error(await response.text())
    }
    const rows=await (await fetch('/api/sessions')).json()
    t.agent.replaceSessions(rows)
    if(!await t.workspace.openSession('session_presencea')) throw Error('不能打开隔离会话')
    return true
  })()`)
  const sessions = await a.evaluate('fetch("/api/sessions").then(r=>r.json())')
  await b.evaluate(`(async () => {
    const t=window.sessionImportTest
    await t.auth.login('zlw@example.com','123456')
    t.agent.replaceSessions(${JSON.stringify(sessions)})
    t.agent.switchToSession('session_presenceb')
    t.agentBridge.connect()
    return true
  })()`)
  const usageBefore = await a.evaluate('fetch("/api/auth/session").then(r=>r.json()).then(user=>user.usage)')
  await a.evaluate(`(()=>{const t=window.sessionImportTest;t.presenceOriginalNow=Date.now;return import('/src/extensions/presence/store.ts').then(({usePresenceStore})=>{t.presence=usePresenceStore();t.presence.workspaceActive=true;t.agentBridge.connect();return true})})()`)
  await Promise.all([a.wait('window.sessionImportTest.agent.connectionStatus==="connected"'), b.wait('window.sessionImportTest.agent.connectionStatus==="connected"')])
  await b.click('.session-picker')
  await b.wait('document.querySelectorAll(".session-card").length===2')
  const rowText = (id, text) => `Array.from(document.querySelectorAll('.session-card')).find(el=>el.querySelector('.session-id')?.textContent===${JSON.stringify(id)})?.querySelector('.session-presence')?.textContent.includes(${JSON.stringify(text)})`
  await b.wait(rowText('session_presencea','lxw · 操作中'))
  await b.wait(rowText('session_presenceb','空闲 · 无人操作'))
  await b.wait('!document.querySelector(".dialog-fade-enter-active") && !document.querySelector(".el-dialog-fade-enter-active") && document.querySelector(".session-dialog").getAnimations({subtree:true}).every(animation=>animation.playState!=="running")')
  checks.push('真实登录、HTTP 和 WebSocket 同步当前操作用户名与会话')
  await b.screenshot(output + '01-会话操作用户.png')

  await a.evaluate(`(()=>{const t=window.sessionImportTest;Date.now=()=>t.presenceOriginalNow()+61_000;document.dispatchEvent(new Event('visibilitychange'));return true})()`)
  await b.wait(rowText('session_presencea','lxw · 空闲'))
  await a.evaluate('Date.now=window.sessionImportTest.presenceOriginalNow;true')
  await a.send('Input.dispatchMouseEvent',{type:'mouseMoved',x:300,y:120})
  await b.wait(rowText('session_presencea','lxw · 操作中'))
  checks.push('60 秒无操作转为空闲，真实鼠标输入恢复操作中')

  await a.evaluate('window.sessionImportTest.agent.setProcessing(true);true')
  await b.wait(rowText('session_presencea','lxw · 生成中'))
  await a.evaluate('window.sessionImportTest.agent.setProcessing(false);true')
  await b.wait(rowText('session_presencea','lxw · 操作中'))
  checks.push('AI 忙碌状态变化经现有连接实时同步')

  assert.equal(await a.evaluate('window.sessionImportTest.workspace.openSession("session_presenceb")'),true)
  await b.wait(rowText('session_presencea','空闲 · 无人操作'))
  await b.wait(rowText('session_presenceb','lxw · 操作中'))
  await b.wait('document.querySelector(".current-session-presence").textContent.includes("lxw · 操作中")')
  checks.push('切换会话后旧会话释放，新会话与顶部当前会话同步显示')

  await a.evaluate('window.sessionImportTest.presence.workspaceActive=false;true')
  await b.wait(rowText('session_presenceb','空闲 · 无人操作'))
  await a.evaluate('window.sessionImportTest.presence.workspaceActive=true;true')
  await b.wait(rowText('session_presenceb','lxw · 操作中'))
  await a.evaluate('window.sessionImportTest.agentBridge.disconnect();true')
  await b.wait(rowText('session_presenceb','空闲 · 无人操作'))
  checks.push('离开工作台与断开连接立即清除会话占用')
  const after = await a.evaluate('fetch("/api/sessions").then(r=>r.json())')
  assert.deepEqual(after.map(s=>[s.session_id,s.created_at,s.updated_at]), sessions.map(s=>[s.session_id,s.created_at,s.updated_at]))
  assert.deepEqual(await a.evaluate('fetch("/api/auth/session").then(r=>r.json()).then(user=>user.usage)'),usageBefore)
  checks.push('状态上报不改会话时间或排序，也不消耗手工和 AI 额度')

  const lifecycle = await a.evaluate(`(async () => {
    const {trackSessionActivity}=await import('/src/extensions/presence/activity.ts')
    const t=window.sessionImportTest, reports=[]
    t.presence.workspaceActive=true
    const tracker=trackSessionActivity(state=>reports.push(state))
    const initial=reports.at(-1).activity
    t.auth.user={role:'guest',username:'访客'}
    const guest=reports.at(-1).session_id
    tracker.dispose()
    const count=reports.length
    window.dispatchEvent(new Event('pointerdown'))
    t.agent.switchToSession('session_presencea')
    t.agent.setProcessing(true)
    tracker.publish()
    return {initial,guest,disposed:reports.length===count}
  })()`)
  assert.deepEqual(lifecycle,{initial:'active',guest:null,disposed:true})
  checks.push('只读访客不宣称操作会话，释放跟踪器后监听与手动发布均停止')

  await b.evaluate(`(async () => {
    const {usePresenceStore}=await import('/src/extensions/presence/store.ts')
    const t=window.sessionImportTest,presence=usePresenceStore()
    t.agentBridge.disconnect()
    presence.setConnectionStatus('connected')
    const client=(id,user_id,username,activity,can_edit=true)=>({id,user_id,username,display_name:'自定义昵称',can_edit,session_id:'session_presenceb',activity,connected_at:1,region:'测试',masked_ip:'127.0.*.*'})
    presence.updatePresence(4,[client('tab1','one','同一账号','idle'),client('tab2','one','同一账号','generating'),client('other','two','另一位正在操作的建筑设计用户','active'),client('guest','guest','只读访客','active',false)],true)
    t.presence=presence
    return true
  })()`)
  await b.wait(rowText('session_presenceb','同一账号 · 生成中'))
  assert.equal(await b.evaluate('window.sessionImportTest.presence.operatorsBySession.session_presenceb.length'),2)
  assert.equal(await b.evaluate('document.querySelector(".session-cards").textContent.includes("只读访客")'),false)
  await b.resize(390,844)
  assert.equal(await b.evaluate('document.documentElement.scrollWidth<=innerWidth'),true)
  await b.screenshot(output + '02-多人和窄屏.png')
  checks.push('多标签页按账号合并，多人和长用户名可读，窄屏不溢出')
  await b.evaluate('window.sessionImportTest.presence.setConnectionStatus("disconnected");true')
  await b.wait(rowText('session_presenceb','使用状态未连接'))
  await b.evaluate('window.sessionImportTest.presence.setConnectionStatus("connected");window.sessionImportTest.presence.updatePresence(0,[]);true')
  await b.wait(rowText('session_presenceb','使用状态暂不可用'))
  checks.push('断线或旧服务端缺少能力时不误报无人操作')
  assert.deepEqual(a.errors,[]);assert.deepEqual(b.errors,[])
  const result={status:'PASS',checks,backend:info,browserErrors:[],limits:['使用真实 FastAPI、登录、HTTP、WebSocket 与 Chromium；SQL 和 Redis 为隔离 SQLite/fakeredis。','AI 忙碌使用真实前端状态切换，不调用模型。空闲测试推进浏览器时间，不等待真实一分钟。']}
  await mkdir(output,{recursive:true})
  await writeFile(output+'result.json',JSON.stringify(result,null,2)+'\n')
  console.log(JSON.stringify(result,null,2))
} finally {
  await actor?.close();await observer?.close();await server.close()
}
