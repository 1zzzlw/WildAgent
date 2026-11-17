import assert from 'node:assert/strict'
import { mkdir, writeFile } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import { createServer } from 'vite'
import { launchEditorBrowser } from './editor-browser.mjs'

const output = fileURLToPath(new URL('../.workbuddy/session-import-regression/', import.meta.url))
const server = await createServer({ root: fileURLToPath(new URL('..', import.meta.url)), server: { host: '127.0.0.1', port: 0 } })
let browser
const checks = []
try {
  await server.listen()
  browser = await launchEditorBrowser(server.resolvedUrls.local[0] + 'scripts/session-import-preview.html')
  const p = browser.page
  await p.wait('window.ready')
  await p.evaluate(`(() => {
    const t = window.sessionImportTest
    t.blueprint = (name, radius = .5, revision = 7) => ({meta:{version:'1.0',type:'building',name}, geometry:{elements:[{id:'sphere',type:'primitive',shape:'sphere',position:[0,.5,0],radius}],components:[]},materials:{},editor:{revision}})
    t.rows = [
      {session_id:'session_alpha',filename:'2026-11-01/session_alpha_A.wild',name:'同名建筑',created_at:100,updated_at:9000,status:'saved',elements_count:1},
      {session_id:'session_beta',filename:'2026-11-02/session_beta_B.wild',name:'另一建筑',created_at:200,updated_at:5000,status:'saved',elements_count:1},
    ]
    t.documents = Object.fromEntries(t.rows.map(row => [row.filename,t.blueprint(row.name)]))
    t.writes = []; t.rejectWrites = false; t.rejectList = false
    t.fetchOriginal = window.fetch
    window.fetch = async (input, init = {}) => {
      const path = decodeURIComponent(new URL(String(input), location.href).pathname)
      const json = data => new Response(JSON.stringify(data),{headers:{'Content-Type':'application/json'}})
      if(path === '/api/scenes') return t.rejectList ? new Response('{}',{status:503}) : json(t.rows)
      if(path.startsWith('/api/scenes/')) {
        const filename=path.slice('/api/scenes/'.length)
        if(init.method === 'PUT') {
          if(t.rejectWrites) return new Response(JSON.stringify({detail:'测试保存失败'}),{status:503})
          const bp=JSON.parse(init.body), row=t.rows.find(item=>item.filename===filename)
          const baseRevision=new Headers(init.headers).get('X-Base-Revision')
          if(row && Number(baseRevision)!==t.documents[filename].editor.revision) return new Response(JSON.stringify({detail:'测试版本冲突'}),{status:409})
          t.writes.push({filename,bp,baseRevision})
          t.documents[filename]=bp
          if(row) {row.name=bp.meta.name;row.updated_at=Date.now()}
          else t.rows.push({filename,session_id:t.agent.currentSessionId,name:bp.meta.name,created_at:Date.now(),updated_at:Date.now(),status:'saved',elements_count:1})
          return json({status:'ok'})
        }
        return t.documents[filename] ? json(t.documents[filename]) : new Response('{}',{status:404})
      }
      if(path.startsWith('/api/sessions/')) return json(path.endsWith('/messages') || path.endsWith('/turns') ? [] : t.rows.find(item=>item.session_id===path.split('/')[3]))
      if(path==='/api/auth/session') return json(t.auth.user)
      if(path==='/api/admin/blueprints') return json({page:1,total:30,items:Array.from({length:30},(_,i)=>({filename:'2026-11-17/session_table_'+i+'.wild',name:'管理蓝图 '+i,owner_name:'测试账号',elements_count:100,components_count:20,updated_at:1,locked:false}))})
      return t.fetchOriginal(input,init)
    }
    t.agent.replaceSessions(structuredClone(t.rows))
    t.startImport = (name='同名建筑',filename='session_external_同名建筑.wild',radius=.9,revision=2) => {
      t.pending = t.workspace.importFile(new File([JSON.stringify(t.blueprint(name,radius,revision))],filename,{type:'application/json',lastModified:1}))
      return true
    }
    return true
  })()`)
  const state = expression => p.evaluate(`(() => {const t=window.sessionImportTest;return ${expression}})()`)
  const run = code => p.evaluate(`(async () => {const t=window.sessionImportTest;${code}})()`)
  const dialog = () => p.wait('!!document.querySelector(".blueprint-import-dialog") && document.querySelector(".blueprint-import-dialog").getBoundingClientRect().height>0')
  const finish = async () => {
    const result = await run('return await t.pending')
    await p.wait('!document.querySelector(".blueprint-import-dialog")')
    return result
  }
  const confirm = () => p.click('.blueprint-import-dialog .el-message-box__btns .el-button--primary')
  const cancel = () => p.click('.blueprint-import-dialog .el-message-box__btns .el-button:not(.el-button--primary)')

  assert.equal(await run("return await t.workspace.openSession('session_alpha')"), true)
  assert.deepEqual(await state("[t.agent.sessions[0].created_at,t.agent.sessions[0].updated_at]"), [100,9000])
  checks.push('切换会话不改变创建时间或更新时间')
  await run('t.ui.sessionPickerVisible=true')
  await p.wait('document.querySelectorAll(".session-card").length===2')
  assert.deepEqual(await p.evaluate('Array.from(document.querySelectorAll(".session-name")).map(el=>el.textContent)'), ['另一建筑','同名建筑'])
  assert.equal(await p.evaluate('document.querySelector(".session-list-hint").textContent.includes("按创建时间排序")'), true)
  await run('t.ui.sessionPickerVisible=false')
  await p.wait('!document.querySelector(".session-dialog") || document.querySelector(".session-dialog").getBoundingClientRect().height===0')
  checks.push('会话列表按创建时间排序，更新时间与顺序无关')

  const previous = await state('[t.agent.currentSessionId,t.scene.document.id,t.agent.sessions.length,t.writes.length]')
  await run('return t.startImport()')
  await dialog()
  await p.click('.blueprint-import-dialog .el-radio:first-child')
  await browser.page.screenshot(output + '01-单条重名确认.png')
  await cancel()
  assert.equal(await finish(), false)
  assert.deepEqual(await state('[t.agent.currentSessionId,t.scene.document.id,t.agent.sessions.length,t.writes.length]'), previous)
  checks.push('单条同名记录也要求确认，取消不创建或覆盖蓝图')

  await run('return t.startImport()')
  await dialog(); await confirm()
  assert.equal(await finish(), true)
  assert.deepEqual(await state('[t.writes.at(-1).filename,t.writes.at(-1).baseRevision,t.writes.at(-1).bp.editor.revision,t.agent.sessions.find(s=>s.session_id==="session_alpha").created_at,t.agent.sessions.length]'), ['2026-11-01/session_alpha_A.wild','7',8,100,2])
  checks.push('旧导出文件修改后仍命中同名，覆盖保留原路径、会话、创建时间并推进版本')

  await run(`t.rows.push({session_id:'session_legacy',filename:'2026-10-01/session_legacy_copy.wild',name:'同名建筑',created_at:50,updated_at:2000,status:'saved',elements_count:1});t.documents[t.rows.at(-1).filename]=t.blueprint('同名建筑',.3,4);return t.startImport()`)
  await dialog()
  await p.click('.blueprint-import-dialog .el-select')
  await p.wait('!!document.querySelector(".el-select-dropdown__item")')
  await p.click('.el-select-dropdown__item:last-child')
  await confirm()
  assert.equal(await finish(), true)
  assert.equal(await state('t.writes.at(-1).filename'), '2026-10-01/session_legacy_copy.wild')
  checks.push('多条同名记录可明确选择覆盖目标')

  const keep = await state('JSON.stringify(t.documents["2026-11-01/session_alpha_A.wild"])')
  await run('return t.startImport()')
  await dialog()
  await p.click('.blueprint-import-dialog .el-radio:last-child')
  assert.equal(await p.evaluate('!!document.querySelector(".blueprint-import-dialog .el-select")'), false)
  const started = Date.now()
  await confirm()
  assert.equal(await finish(), true)
  const imported = await state('JSON.parse(JSON.stringify(t.agent.sessions.find(s=>s.session_id===t.agent.currentSessionId)))')
  const browserNow = await p.evaluate('Date.now()')
  assert.ok(Math.abs(imported.created_at - browserNow) < 5000, JSON.stringify({imported,started,browserNow}))
  assert.notEqual(imported.filename, '2026-11-01/session_alpha_A.wild')
  assert.equal(await state('JSON.stringify(t.documents["2026-11-01/session_alpha_A.wild"])'), keep)
  await run('return await t.workspace.openSession(t.agent.currentSessionId)')
  assert.equal(await state('t.agent.sessions.find(s=>s.session_id===t.agent.currentSessionId).created_at'), imported.created_at)
  checks.push('明确选择另存才产生新会话，创建时间取导入时刻，切换后保持不变')

  await run("t.rows.push({session_id:'session_locked',filename:'session_locked.wild',name:'锁定建筑',created_at:1,updated_at:1,status:'saved',elements_count:1,locked:true});return t.startImport('锁定建筑','locked.wild')")
  await dialog()
  assert.equal(await p.evaluate('document.querySelector(".blueprint-import-dialog .el-radio:first-child").classList.contains("is-disabled")'), true)
  assert.equal(await p.evaluate('document.querySelector(".blueprint-import-dialog .el-radio:last-child").classList.contains("is-checked")'), true)
  await cancel(); assert.equal(await finish(), false)
  checks.push('锁定蓝图不能覆盖，可取消或另存')

  await run('t.rejectList=true;return t.startImport()')
  assert.equal(await finish(), false)
  await run('t.rejectList=false;t.rejectWrites=true;return t.startImport("全新建筑","new.wild")')
  assert.equal(await finish(), false)
  assert.equal(await state('t.scene.document.dirty'), true)
  checks.push('查询失败不盲目新建，保存失败保留可恢复草稿')

  await run("t.clearMessages();t.screen.value='admin'")
  await p.wait('document.querySelectorAll(".admin-table tbody tr").length===30')
  await p.resize(1280,720)
  async function wheel(deltaX,deltaY) {
    const pos = await p.evaluate('(()=>{const r=document.querySelector(".admin-table-scroll").getBoundingClientRect();return {x:Math.min(innerWidth-30,r.x+200),y:Math.max(50,Math.min(innerHeight-50,r.y+100))}})()')
    await p.send('Input.dispatchMouseEvent',{type:'mouseWheel',...pos,deltaX,deltaY})
  }
  await wheel(0,600)
  await p.wait('document.querySelector(".admin-layout").scrollTop>100')
  await p.screenshot(output + '02-管理列表滚轮滚动.png')
  await p.resize(390,844)
  await p.evaluate('document.querySelector(".admin-layout").scrollTop=0')
  await wheel(250,0)
  await p.wait('document.querySelector(".admin-table-scroll").scrollLeft>0')
  await wheel(0,500)
  await p.wait('document.querySelector(".admin-layout").scrollTop>100')
  checks.push('桌面和窄屏鼠标置于表格时均能纵向滚动，窄屏横向滚动仍可用')
  assert.deepEqual(p.errors,[])
  const result={status:'PASS',checks,browserErrors:p.errors,limits:['HTTP 使用隔离桩响应，未写入业务数据库。','真实 Vue/Pinia、Core 重建、弹窗点击和鼠标滚轮在 Chromium 执行。']}
  await mkdir(output,{recursive:true})
  await writeFile(output+'result.json',JSON.stringify(result,null,2)+'\n')
  console.log(JSON.stringify(result,null,2))
} finally {
  await browser?.close()
  await server.close()
}
