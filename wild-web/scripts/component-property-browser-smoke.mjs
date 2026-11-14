import assert from 'node:assert/strict'
import { createServer } from 'vite'
import { resolve } from 'node:path'
import { mkdir, writeFile } from 'node:fs/promises'
import { launchEditorBrowser } from './editor-browser.mjs'

const server=await createServer({server:{host:'127.0.0.1',port:0},logLevel:'error'})
let browser
try{
  await server.listen()
  browser=await launchEditorBrowser(`http://127.0.0.1:${server.httpServer.address().port}/scripts/component-property-preview.html`)
  const page=browser.page;await page.wait('window.ready')
  const selector=await page.evaluate(`(()=>{const row=[...document.querySelectorAll('.property-row')].find(r=>r.querySelector('label')?.textContent==='视频资源地址');return '#'+CSS.escape(row.querySelector('input').id)})()`)
  await page.click(selector)
  const path='/videos/villa.mp4'
  for(const char of path){
    await page.send('Input.insertText',{text:char})
    await page.evaluate('new Promise(requestAnimationFrame)')
  }
  assert.equal(await page.evaluate(`document.querySelector(${JSON.stringify(selector)}).value`),path,'输入期间不能被旧的 modelValue 清空')
  assert.equal(await page.evaluate('window.propertyTest.source()'),'','编辑草稿不能逐字符重建场景')
  await page.click('.section-title')
  await page.wait('window.propertyTest.source()==='+JSON.stringify(path))
  assert.equal(await page.evaluate('window.propertyTest.history.entries.length'),1,'一次提交只有一条撤销记录')
  await page.evaluate('window.propertyTest.undo()');await page.wait('window.propertyTest.source()===""')
  await page.evaluate('window.propertyTest.redo()');await page.wait('window.propertyTest.source()==='+JSON.stringify(path))
  await page.click(selector)
  await page.evaluate(`document.querySelector(${JSON.stringify(selector)}).select()`)
  await page.send('Input.dispatchKeyEvent',{type:'keyDown',key:'Backspace',code:'Backspace',windowsVirtualKeyCode:8})
  await page.send('Input.dispatchKeyEvent',{type:'keyUp',key:'Backspace',code:'Backspace',windowsVirtualKeyCode:8})
  assert.equal(await page.evaluate(`document.querySelector(${JSON.stringify(selector)}).value`),'')
  await page.click('.section-title');await page.wait('window.propertyTest.source()===""')
  await page.evaluate('window.propertyTest.selection.select("screen_b")')
  await page.wait(`document.querySelector('.property-row:has(input[aria-label="视频资源地址"]) input')?.value==='/second.webm'`)
  assert.deepEqual(page.errors,[])
  const out=resolve('../.workbuddy/component-property');await mkdir(out,{recursive:true})
  await page.screenshot(resolve(out,'property-panel.png'))
  const result={status:'PASS',checks:['真实 Element Plus 逐字符输入','失焦提交','单次撤销记录','撤销重做','清空资源地址','切换组件重置草稿'],browserErrors:page.errors}
  await writeFile(resolve(out,'result.json'),JSON.stringify(result,null,2));console.log(JSON.stringify(result,null,2))
}finally{await browser?.close();await server.close()}
