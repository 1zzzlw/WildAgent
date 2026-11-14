import assert from 'node:assert/strict'
import { copyFile, mkdir, mkdtemp, readFile, readdir, writeFile } from 'node:fs/promises'
import { join, resolve } from 'node:path'
import { tmpdir } from 'node:os'
import { launchEditorBrowser } from './editor-browser.mjs'

const origin = process.env.EDITOR_URL || 'http://127.0.0.1:5196'
const output = resolve('../docs/11月2日/登录与游客权限')
const downloads = await mkdtemp(join(tmpdir(), 'wild-auth-download-'))
await mkdir(resolve(output, '下载验证'), { recursive: true })
// 仅对隔离回归服务种入样例，不连接用户的实际存储。
assert.equal((await fetch(`${origin}/api/editor-smoke-storage`)).status, 200)
const login = await fetch(`${origin}/api/auth/login`, {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email:'zlw@example.com',password:'123456'})})
assert.equal(login.status, 200)
const cookie = login.headers.get('set-cookie').split(';')[0]
const fixture = JSON.parse(await readFile(resolve('scripts/fixtures/presentation.json'), 'utf8'))
fixture.meta.name = '登录权限回归建筑'
const filename = '2026-11-02/session_9001_login-smoke.wild'
assert.equal((await fetch(`${origin}/api/scenes/${filename}`, {method:'PUT',headers:{Cookie:cookie,'Content-Type':'application/json'},body:JSON.stringify(fixture)})).status, 200)
await fetch(`${origin}/api/auth/logout`, {method:'POST',headers:{Cookie:cookie}})

const browser = await launchEditorBrowser(origin)
const p = browser.page
const viewport = code => p.evaluate(`(()=>{const s=document.querySelector('.canvas-viewport').__vueParentComponent.setupState;${code}})()`)
const documentState = () => viewport('return {json:JSON.stringify(s.sceneStore.document.blueprint),revision:s.sceneStore.document.revision,dirty:s.sceneStore.document.dirty};')
const storage = () => p.evaluate(`fetch('/api/editor-smoke-storage').then(r=>r.json())`)
const waitLogin = () => p.wait('document.querySelector("#login-email") && !document.querySelector("#login-email").disabled')
const waitScene = () => p.wait('!!document.querySelector(".canvas-viewport") && document.querySelector(".canvas-viewport").__vueParentComponent.setupState.sceneStore.reconstructed?.meshes.length > 0')
async function fill(selector, value) {
  await p.click(selector)
  await p.send('Input.dispatchKeyEvent', {type:'keyDown',key:'a',code:'KeyA',modifiers:2,windowsVirtualKeyCode:65})
  await p.send('Input.dispatchKeyEvent', {type:'keyUp',key:'a',code:'KeyA',modifiers:2,windowsVirtualKeyCode:65})
  await p.send('Input.insertText', {text:value})
}
async function signIn(username, password='123456') {
  await waitLogin()
  await fill('#login-email', username + '@example.com')
  await fill('#login-password', password)
  await p.click('button[type="submit"]')
}
async function logout() {
  const previous = await p.evaluate('performance.timeOrigin')
  await clickUncovered('[aria-label="退出登录"]')
  await p.wait(`performance.timeOrigin > ${previous}`)
  await waitLogin()
}
async function clickUncovered(selector) {
  await p.send('Input.dispatchMouseEvent', {type:'mouseMoved',x:700,y:800})
  await p.wait(`(()=>{const el=document.querySelector(${JSON.stringify(selector)});if(!el||el.disabled)return false;
    el.scrollIntoView({block:'nearest',inline:'nearest'});const r=el.getBoundingClientRect();
    return el.contains(document.elementFromPoint(r.x+r.width/2,r.y+r.height/2));})()`)
  await p.click(selector)
}
async function waitDownload(extension) {
  for (let i=0;i<100;i++) {
    const files = (await readdir(downloads)).filter(name=>name.endsWith(extension))
    if (files.length) return resolve(downloads, files[0])
    await new Promise(r=>setTimeout(r,100))
  }
  throw Error('未收到下载文件 '+extension)
}
try {
  await waitLogin()
  await p.wait('document.querySelector(".presence-tag")?.textContent.includes("1 人在线")')
  await p.screenshot(output + '/01-密码与游客登录.png')
  await p.resize(390, 844)
  assert.equal(await p.evaluate('document.documentElement.scrollWidth<=innerWidth'), true)
  await p.screenshot(output + '/02-手机登录.png')
  await p.resize(390,600)
  assert.equal(await p.evaluate('document.querySelector(".login-page").scrollHeight>600 && document.querySelector("#login-email").getBoundingClientRect().top>0'),true)
  await p.resize(1440,1000)
  await p.click('[aria-label="切换为暗色主题"]')
  await p.screenshot(output + '/03-暗色登录.png')
  await p.click('[aria-label="切换为亮色主题"]')

  // 旧访客名称不能代替新认证。
  await p.evaluate("localStorage.setItem('wild_presence_visitor_name','zlw')")
  await p.send('Page.reload')
  await waitLogin()
  await signIn('zlw', 'wrong-password')
  await p.wait('document.querySelector("[role=alert]")?.textContent.includes("邮箱或密码错误")')
  assert.equal(await p.evaluate('!!document.querySelector(".editor-header")'), false)

  await p.click('.guest-button')
  await waitScene()
  await viewport('s.finishEntrance();return true;')
  assert.equal(await viewport('return s.auth.isGuest && !s.auth.canEdit'), true)
  const hidden = ['新建场景','打开 WILD','保存到服务器','导出 WILD','撤销','重做','构件库','属性','材质','模型配置','AI 对话']
  for (const label of hidden) assert.equal(await p.evaluate(`!!document.querySelector('[aria-label="${label}"]')`),false,label)
  await p.wait('document.querySelector(".presence-tag")?.textContent.includes("1 人在线")')
  await p.evaluate(`window.extraPresenceSocket=new WebSocket(location.origin.replace('http','ws')+'/ws/agent?visitor_name=回归访客')`)
  await p.wait('document.querySelector(".presence-tag")?.textContent.includes("2 人在线")')
  await clickUncovered('.presence-tag')
  await p.wait('Array.from(document.querySelectorAll(".presence-client-name")).some(e=>e.textContent==="回归访客")')
  await p.screenshot(output + '/04-游客与在线列表.png')
  await p.evaluate('extraPresenceSocket.close()')
  await p.wait('document.querySelector(".presence-tag")?.textContent.includes("1 人在线")')
  await logout()
  await p.click('.guest-button')
  await waitScene()
  await viewport('s.finishEntrance();return true;')

  const saved = await documentState(), savedStorage = await storage()
  const patch = await viewport(`return {type:'scene_patch',patch_id:'permission-test',base_revision:s.sceneStore.document.revision,source:'user',mode:'apply',requires_confirmation:false,operations:[{op:'update_element',id:'base',changes:{dimensions:[7,.4,6]}}]};`)
  assert.equal(await viewport(`return s.sceneStore.applyPatch(${JSON.stringify(patch)})`),false)
  assert.equal(await viewport('return s.sceneStore.restoreBlueprint(s.sceneStore.document.blueprint)'),false)
  assert.equal(await viewport('return s.sceneStore.exportWild()'),'')
  assert.equal(await p.evaluate(`import('/src/stores/workspaceStore.ts').then(async m=>{const w=m.useWorkspaceStore();return await w.saveScene() || await w.newScene()})`),false)
  assert.equal(await p.evaluate(`import('/src/agent/agentBridge.ts').then(m=>m.agentBridge.sendUserMessage('不得发起模型请求'))`),null)
  await viewport('s.placement.begin({});s.renderPanel.requestScreenshot();return true;')
  assert.equal(await viewport('return s.placement.request'),null)
  assert.equal(await viewport('return s.renderPanel.screenshotNonce'),0)
  await p.send('Input.dispatchKeyEvent',{type:'keyDown',key:'s',code:'KeyS',modifiers:2,windowsVirtualKeyCode:83})
  await p.send('Input.dispatchKeyEvent',{type:'keyUp',key:'s',code:'KeyS',modifiers:2,windowsVirtualKeyCode:83})
  for (const method of ['PUT','DELETE']) {
    assert.equal(await p.evaluate(`fetch('/api/scenes/${filename}',{method:'${method}',headers:{'Content-Type':'application/json'},body:${method==='PUT'?JSON.stringify(JSON.stringify(fixture)):'undefined'}}).then(r=>r.status)`),403)
  }
  const wsResult=await p.evaluate(`new Promise((resolve,reject)=>{
    const w=new WebSocket(location.origin.replace('http','ws')+'/ws/agent');const seen={};
    const timeout=setTimeout(()=>{w.close();reject(Error('WS权限验证超时'))},8000);
    w.onopen=()=>{w.send(JSON.stringify({type:'ping',timestamp:42}));w.send(JSON.stringify({type:'user_message',request_id:'guest-blocked',session_id:'session_9001',message:'blocked'}))};
    w.onmessage=e=>{const d=JSON.parse(e.data);if(d.type==='pong')seen.pong=d.timestamp;if(d.code==='permission_denied')seen.denied=true;if(seen.pong&&seen.denied){clearTimeout(timeout);w.close();resolve(seen)}};
  })`)
  assert.deepEqual(wsResult,{pong:42,denied:true})
  assert.deepEqual(await documentState(),saved)
  assert.deepEqual(await storage(),savedStorage)
  await p.click('[aria-label="切换会话"]')
  await p.wait('document.querySelector(".session-dialog")?.textContent.includes("登录权限回归建筑")')
  assert.equal(await p.evaluate('!!document.querySelector(".menu-trigger")'),false)
  await p.click('.el-dialog__headerbtn')
  await p.wait('!Array.from(document.querySelectorAll(".el-overlay")).some(e=>e.checkVisibility())')
  await p.resize(390,844)
  assert.equal(await p.evaluate('document.querySelector(".presence-tag").getBoundingClientRect().right<=innerWidth'),true)
  await p.screenshot(output + '/05-游客手机顶部在线人数.png')
  await p.resize(1440,1000)
  await p.send('Browser.setDownloadBehavior',{behavior:'allow',downloadPath:downloads})
  await p.evaluate(`window.authDownloads=[];const click=HTMLAnchorElement.prototype.click;
    HTMLAnchorElement.prototype.click=function(){window.authDownloads.push(this.download);return click.call(this)};`)
  await p.click('[aria-label="导出 GLB"]')
  await p.wait('window.authDownloads.some(name=>name.endsWith(".glb"))')
  const glbPath = await waitDownload('.glb')
  const glb = await readFile(glbPath)
  await copyFile(glbPath, resolve(output, '下载验证/游客导出.glb'))
  assert.equal(glb.subarray(0,4).toString(),'glTF')
  assert.ok(glb.length>100)
  await logout()

  const accounts=[]
  for (const username of ['zlw','lxw','mf']) {
    await signIn(username)
    await waitScene()
    assert.equal(await p.evaluate('document.querySelector(".wild-editor").__vueParentComponent.setupState.editorReady'),true)
    assert.equal(await viewport('return s.auth.canEdit && s.auth.user.username'),username)
    assert.equal(await p.evaluate(`!!document.querySelector('[aria-label="保存到服务器"]') && !!document.querySelector('[aria-label="导出 WILD"]')`),true)
    accounts.push(username)
    if (username==='zlw') {
      await p.evaluate(`window.authSaveActions=[];import('/src/stores/workspaceStore.ts').then(m=>m.useWorkspaceStore().$onAction(({name,after})=>{if(name==='saveScene')after(result=>window.authSaveActions.push(result))}))`)
      const memberPatch = await viewport(`return {...${JSON.stringify(patch)},base_revision:s.sceneStore.document.revision};`)
      assert.equal(await viewport(`return s.sceneStore.applyPatch(${JSON.stringify(memberPatch)})`),true)
      await clickUncovered('[aria-label="保存到服务器"]')
      await p.wait('!document.querySelector(".canvas-viewport").__vueParentComponent.setupState.sceneStore.document.dirty')
      assert.equal((await storage())[filename].geometry.elements.find(e=>e.id==='base').dimensions[0],7)
      await p.click('[aria-label="导出 WILD"]')
      const wildPath = await waitDownload('.wild')
      assert.equal(JSON.parse(await readFile(wildPath,'utf8')).geometry.elements.find(e=>e.id==='base').dimensions[0],7)
      await copyFile(wildPath, resolve(output, '下载验证/账号导出.wild'))
      await p.send('Page.reload')
      await waitScene()
      assert.equal(await viewport('return s.auth.canEdit'),true)
      await viewport('s.finishEntrance();return true;')
      await p.screenshot(output + '/06-密码登录编辑工作台.png')
    }
    await logout()
  }
  await p.send('Page.navigate',{url:origin+'/business-plan'})
  await p.wait('document.querySelectorAll(".project-case").length===14')
  assert.deepEqual(p.errors,[])
  const report={checks:{loginPage:true,mobileAndDarkTheme:true,oldVisitorNameDoesNotAuthenticate:true,invalidPassword:true,
    guestReadOnly:true,storeAndKeyboardGuards:true,backendWriteDenied:true,websocketGuestDenied:true,
    guestGlbDownloaded:true,memberSaveAndWildExport:true,sessionRestored:true,logout:true,publicBusinessPage:true,
    presenceOnLoginAndWorkbench:true,presenceConnectDisconnect:true,mobilePresenceVisible:true,noRuntimeOrShaderErrors:true},accounts,glbBytes:glb.length,errors:p.errors}
  await writeFile(output+'/浏览器验证.json',JSON.stringify(report,null,2)+'\n')
  console.log(JSON.stringify(report,null,2))
} catch(error) {
  console.error(await p.evaluate(`({downloads:window.authDownloads,saveActions:window.authSaveActions,messages:Array.from(document.querySelectorAll('.el-message__content')).map(e=>e.textContent),nonce:document.querySelector('.canvas-viewport')?.__vueParentComponent.setupState.renderPanel.glbExportNonce,exporting:document.querySelector('.canvas-viewport')?.__vueParentComponent.setupState.renderPanel.exportingGlb})`))
  await p.screenshot(output+'/failure.png')
  throw error
} finally {await browser.close()}
