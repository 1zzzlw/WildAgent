import assert from 'node:assert/strict'
import { createServer } from 'vite'
import { launchEditorBrowser } from './editor-browser.mjs'
import { resolve } from 'node:path'
import { mkdir,writeFile } from 'node:fs/promises'

const output=resolve('../.workbuddy/database-validation')
await mkdir(output,{recursive:true})
assert.equal((await fetch('http://127.0.0.1:18080/api/editor-smoke-storage')).status,200)
const server=await createServer({server:{host:'127.0.0.1',port:0,proxy:{
  '/api':{target:'http://127.0.0.1:18080',changeOrigin:true},
  '/ws':{target:'ws://127.0.0.1:18080',ws:true}
}},logLevel:'error'})
let browser
try{
  await server.listen()
  browser=await launchEditorBrowser(`http://127.0.0.1:${server.httpServer.address().port}/`)
  const p=browser.page
  const email='preview-'+Date.now()+'@example.com'
  const initialMail=await (await fetch('http://127.0.0.1:18080/api/editor-smoke-mail')).json()
  await p.wait('document.querySelector("#login-email") && !document.querySelector("#login-email").disabled')
  await p.click('.account-switch button')
  await p.wait('document.activeElement.id === "register-username"')
  async function fill(selector,value){
    await p.click(selector)
    await p.evaluate(`document.querySelector(${JSON.stringify(selector)}).select()`)
    await p.send('Input.dispatchKeyEvent',{type:'keyDown',key:'Backspace',code:'Backspace',windowsVirtualKeyCode:8})
    await p.send('Input.dispatchKeyEvent',{type:'keyUp',key:'Backspace',code:'Backspace',windowsVirtualKeyCode:8})
    await p.send('Input.insertText',{text:value})
    await p.evaluate('new Promise(requestAnimationFrame)')
  }
  await fill('#register-username','注册体验账号')
  await fill('#register-email',email)
  await p.click('.code-button')
  await p.wait('document.querySelector(".registration-notice")?.textContent.includes("已发送")')
  assert.equal(await p.evaluate('document.querySelector(".code-button").disabled'),true)
  const mail=await p.evaluate('fetch("/api/editor-smoke-mail").then(r=>r.json())')
  assert.equal(mail.count,initialMail.count+1)
  await fill('#register-code',mail.code)
  await fill('#register-password','Browser-preview-2026')
  await fill('#register-confirm-password','Other-preview-2026')
  await p.click('h1')
  await p.wait('document.querySelector("#confirm-password-error")?.textContent.includes("不一致")')
  await p.click('.register-form button[type="submit"]')
  assert.equal(await p.evaluate('document.activeElement.id'),'register-confirm-password')
  await fill('#register-confirm-password','Browser-preview-2026')
  await p.click('h1')
  await p.screenshot(resolve(output,'registration-light.png'))
  await p.click('.theme-button')
  await p.wait('document.documentElement.dataset.theme === "dark"')
  await p.screenshot(resolve(output,'registration-dark.png'))
  await p.resize(375,812)
  assert.equal(await p.evaluate('document.documentElement.scrollWidth <= innerWidth'),true)
  await p.evaluate('document.querySelector(".login-page").scrollTop=0')
  await p.screenshot(resolve(output,'registration-mobile.png'))
  await p.resize(1440,1000)
  await p.click('.register-form button[type="submit"]')
  await p.wait('!!document.querySelector(".canvas-viewport")',40000)
  const user=await p.evaluate('fetch("/api/auth/session").then(r=>r.json())')
  assert.equal(user.username,'注册体验账号');assert.equal(user.role,'editor');assert.equal(user.identity,1);assert.ok(user.id)
  assert.equal(await p.evaluate('!!document.querySelector("[aria-label=模型配置]")'),true)
  const beforeReload=await p.evaluate('performance.timeOrigin')
  await p.send('Page.reload')
  await p.wait('performance.timeOrigin > '+beforeReload)
  await p.wait('!!document.querySelector(".canvas-viewport")',40000)
  assert.equal(await p.evaluate('!!document.querySelector("#login-email")'),false)
  const restored=await p.evaluate('fetch("/api/auth/session").then(r=>r.json())')
  assert.equal(restored.id,user.id)
  await p.evaluate("import('/src/stores/agentStore.ts').then(m=>m.useAgentStore(document.querySelector('#app').__vue_app__.config.globalProperties.$pinia).addUserMessage('账号隔离测试消息'))")
  let beforeLogout=await p.evaluate('performance.timeOrigin')
  await p.click('[aria-label="退出登录"]')
  await p.wait('performance.timeOrigin > '+beforeLogout)
  await p.wait('document.querySelector("#login-email") && !document.querySelector("#login-email").disabled')
  await fill('#login-email',email)
  await fill('#login-password','Browser-preview-2026')
  await p.click('button[type="submit"]')
  await p.wait('!!document.querySelector(".canvas-viewport")',40000)
  assert.equal((await p.evaluate('fetch("/api/auth/session").then(r=>r.json())')).id,user.id)
  beforeLogout=await p.evaluate('performance.timeOrigin')
  await p.click('[aria-label="退出登录"]')
  await p.wait('performance.timeOrigin > '+beforeLogout)
  await p.wait('document.querySelector("#login-email") && !document.querySelector("#login-email").disabled')
  await fill('#login-email','zlw@example.com')
  await fill('#login-password','123456')
  await p.click('button[type="submit"]')
  await p.wait('!!document.querySelector("[aria-label=模型配置]")',40000)
  assert.equal((await p.evaluate('fetch("/api/auth/session").then(r=>r.json())')).identity,2)
  assert.equal(await p.evaluate("import('/src/stores/agentStore.ts').then(m=>m.useAgentStore(document.querySelector('#app').__vue_app__.config.globalProperties.$pinia).session.messages.some(v=>v.content==='账号隔离测试消息'))"),false)
  assert.deepEqual(p.errors,[])
  const info=await (await fetch('http://127.0.0.1:18080/api/editor-smoke-info')).json()
  const result={status:'PASS',...info,
    checks:['真实 Vue 注册表单','验证码发送 API 与成功后倒计时','确认密码阻止提交','亮暗主题与手机布局','注册身份固定普通用户','邮箱密码登录','普通用户与管理员拥有相同功能入口','刷新后 Redis Cookie 会话恢复','切换账号隔离本地消息缓存'],browserErrors:p.errors}
  await writeFile(resolve(output,'browser-result.json'),JSON.stringify(result,null,2)+'\n')
  console.log(JSON.stringify(result,null,2))
}catch(error){await browser?.page.screenshot(resolve(output,'failure.png'));throw error}
finally{await browser?.close();await server.close()}
