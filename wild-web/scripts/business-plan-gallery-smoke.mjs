import assert from 'node:assert/strict'
import { mkdir, writeFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { launchEditorBrowser } from './editor-browser.mjs'

const output=resolve('../docs/10月30日/微缩背景修复/商业页面验证')
await mkdir(output,{recursive:true})
const browser=await launchEditorBrowser(`${process.env.EDITOR_URL||'http://127.0.0.1:5196'}/business-plan`)
const p=browser.page,checks=[]
const card=id=>`.project-case:has(img[src="/business-plan/${id}-01.png"])`
try{
  await p.wait('!!document.querySelector(".business-plan-page")');await p.resize(1440,1080)
  await p.evaluate("document.documentElement.dataset.theme='light'")
  assert.equal(await p.evaluate('document.querySelectorAll(".project-case").length'),14)
  assert.match(await p.evaluate('document.querySelector(".showcase-summary").innerText'),/14[\s\S]*28/)
  const images=await p.evaluate(`Promise.all(Array.from(document.querySelectorAll('.project-case img'),async img=>{img.loading='eager';await img.decode();return {src:img.getAttribute('src'),width:img.naturalWidth,height:img.naturalHeight,fit:getComputedStyle(img).objectFit}}))`)
  assert.equal(images.length,28);assert.ok(images.every(i=>i.width>0&&i.height>0&&i.fit==='contain'))
  for(const id of ['shiomi','tomokoji','yukiakari']){
    await p.click(card(id)+' summary')
    await p.wait(`document.querySelector(${JSON.stringify(card(id)+' details')}).open`)
    const size=await p.evaluate(`(()=>{const img=document.querySelector(${JSON.stringify(card(id)+' .project-main img')}),r=img.getBoundingClientRect();return {width:img.naturalWidth,height:img.naturalHeight,ratio:r.width/r.height}})()`)
    assert.equal(size.width,1440);assert.equal(size.height,1080);assert.ok(Math.abs(size.ratio-4/3)<.001)
    await p.click(card(id)+' .project-main button')
    await p.wait(`document.querySelector('.image-viewer').open && document.querySelector('#viewer-image').src.endsWith('${id}-01.png')`)
    await p.click('.viewer-close');await p.wait('!document.querySelector(".image-viewer").open')
    await p.click(card(id)+' summary')
    checks.push({id,completeFrame:true,secondaryView:true,lightbox:true})
  }
  await p.evaluate('document.getElementById("showcase").scrollIntoView({behavior:"instant",block:"start"})')
  await p.evaluate('new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))')
  assert.equal(await p.evaluate('getComputedStyle(document.querySelector(".project-grid")).gridTemplateColumns.split(" ").length'),2)
  await p.screenshot(output+'/01-桌面作品区.png')
  await p.evaluate("document.documentElement.dataset.theme='dark'")
  await p.screenshot(output+'/02-暗色作品区.png')
  await p.evaluate("document.documentElement.dataset.theme='light'")
  await p.resize(390,844)
  await p.evaluate('document.getElementById("showcase").scrollIntoView({behavior:"instant",block:"start"})')
  const mobile=await p.evaluate(`(()=>{const page=document.querySelector('.business-plan-page');return {width:innerWidth,pageWidth:page.scrollWidth,clientWidth:page.clientWidth,bodyWidth:document.documentElement.scrollWidth,columns:getComputedStyle(document.querySelector('.project-grid')).gridTemplateColumns.split(' ').length}})()`)
  assert.ok(mobile.pageWidth<=mobile.clientWidth+1);assert.ok(mobile.bodyWidth<=391);assert.equal(mobile.columns,1)
  await p.screenshot(output+'/03-手机作品区.png')
  await p.evaluate(`(()=>{const page=document.querySelector('.business-plan-page'),el=document.querySelector(${JSON.stringify(card('shiomi'))});page.scrollTo({top:page.scrollTop+el.getBoundingClientRect().top-150,behavior:'instant'})})()`)
  await p.screenshot(output+'/04-手机作品图.png')
  assert.deepEqual(p.errors,[])
  const report={projects:14,views:28,newProjects:checks,mobile,images,errors:p.errors}
  await writeFile(output+'/验证结果.json',JSON.stringify(report,null,2)+'\n')
  console.log(JSON.stringify({projects:14,views:28,checks,mobile,errors:p.errors}))
}catch(error){await p.screenshot(output+'/检查失败.png');throw error}
finally{await browser.close()}
