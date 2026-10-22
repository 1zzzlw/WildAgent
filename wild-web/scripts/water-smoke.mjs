import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { launchEditorBrowser } from './editor-browser.mjs';
const hash=value=>createHash('sha256').update(value).digest('hex');
const browser=await launchEditorBrowser('http://127.0.0.1:5178/scripts/water-preview.html');
try {const p=browser.page;await p.wait('window.ready');assert.deepEqual(await p.evaluate('window.diagnostics.filter(d=>d.level==="error")'),[]);assert.equal(await p.evaluate('window.waterCount'),1);
 const directory='E:/AgentProject/WildAgent/docs/10月22日/03-前端与门窗优化/浏览器验证/';
 const frame=async(time,enabled)=>{const programs=await p.evaluate(`window.frame(${time},${enabled})`);assert.ok(programs.every(p=>p.runnable!==false));return p.evaluate('document.querySelector("canvas").toDataURL()')};
 const first=await frame(0,true);await p.evaluate('(window.firstWaterPixels=window.readPixels(), true)');await p.screenshot(directory+'09-动态水面-T0.png');const second=await frame(2,true);await p.screenshot(directory+'10-动态水面-T2.png');assert.notEqual(hash(first),hash(second),'开启时水面需要随时间变化');
 const changedPixels=await p.evaluate('(()=>{const a=window.firstWaterPixels,b=window.readPixels();let changed=0;for(let i=0;i<a.length;i+=4)if(Math.max(Math.abs(a[i]-b[i]),Math.abs(a[i+1]-b[i+1]),Math.abs(a[i+2]-b[i+2]))>3)changed++;return changed})()');
 assert.ok(changedPixels>1000, '动态水面应产生足够可见的像素变化：'+changedPixels);
 await frame(0,false);
 const stopped=await p.evaluate('({time:window.waterUniforms.wildWaterTime.value,enabled:window.waterUniforms.wildWaterEnabled.value})');
 await frame(4,false);
 assert.equal(stopped.enabled,0);assert.deepEqual(await p.evaluate('({time:window.waterUniforms.wildWaterTime.value,enabled:window.waterUniforms.wildWaterEnabled.value})'),stopped,'关闭后时间 uniform 必须冻结');
 assert.deepEqual(p.errors,[]);
 console.log('WATER_RENDER_PASS',JSON.stringify({first:createHash('sha256').update(first).digest('hex'),second:createHash('sha256').update(second).digest('hex'),changedPixels,disabledTimeFrozen:true}));
} finally {await browser.close()}
