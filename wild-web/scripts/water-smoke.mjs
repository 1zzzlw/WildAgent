import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { launchEditorBrowser } from './editor-browser.mjs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
const hash=value=>createHash('sha256').update(value).digest('hex');
const browser=await launchEditorBrowser((process.env.EDITOR_URL || 'http://127.0.0.1:5178')+'/scripts/water-preview.html');
try {const p=browser.page;await p.wait('window.ready');assert.deepEqual(await p.evaluate('window.diagnostics.filter(d=>d.level==="error")'),[]);assert.equal(await p.evaluate('window.waterCount'),1);
 const changedSince=name=>p.evaluate(`(()=>{const a=window[${JSON.stringify(name)}],b=window.readPixels();let n=0;for(let i=0;i<a.length;i+=4)if(Math.max(Math.abs(a[i]-b[i]),Math.abs(a[i+1]-b[i+1]),Math.abs(a[i+2]-b[i+2]))>3)n++;return n})()`);
 const directory=join(tmpdir(),'wild-water-regression')+'/';
 // 比较实际 RGBA 像素，避免把 PNG 编码差异误当成画面变化。
 const frame=async(time,enabled)=>{const programs=await p.evaluate(`window.frame(${time},${enabled})`);assert.ok(programs.every(p=>p.runnable!==false));return p.evaluate(`crypto.subtle.digest('SHA-256',window.readPixels()).then(b=>Array.from(new Uint8Array(b),v=>v.toString(16).padStart(2,'0')).join(''))`)};
 const first=await frame(0,true);await p.evaluate('(window.firstWaterPixels=window.readPixels(), true)');await p.screenshot(directory+'09-动态水面-T0.png');const second=await frame(2,true);await p.screenshot(directory+'10-动态水面-T2.png');assert.notEqual(hash(first),hash(second),'开启时水面需要随时间变化');
 const changedPixels=await p.evaluate('(()=>{const a=window.firstWaterPixels,b=window.readPixels();let changed=0;for(let i=0;i<a.length;i+=4)if(Math.max(Math.abs(a[i]-b[i]),Math.abs(a[i+1]-b[i+1]),Math.abs(a[i+2]-b[i+2]))>3)changed++;return changed})()');
 assert.ok(changedPixels>1000, '动态水面应产生足够可见的像素变化：'+changedPixels);
 await p.evaluate('(window.dynamicWaterPixels=window.readPixels(),true)');
 const frozen=await frame(0,false);assert.equal(await changedSince('dynamicWaterPixels'),0,'关闭动态应冻结当前波纹，不应突然变成平面');
 const stopped=await p.evaluate('({time:window.waterUniforms.wildWaterTime.value,enabled:window.waterUniforms.wildWaterEnabled.value})');
 await frame(4,false);
 assert.equal(stopped.enabled,0);assert.deepEqual(await p.evaluate('({time:window.waterUniforms.wildWaterTime.value,enabled:window.waterUniforms.wildWaterEnabled.value})'),stopped,'关闭后时间 uniform 必须冻结');
 await p.evaluate(`window.setWaterAppearance(0,0.65)`);
 const opaque=await frame(4,false);assert.notEqual(hash(opaque),hash(frozen),'透明度应改变真实渲染');
 await p.evaluate(`window.setWaterAppearance(1,0)`);
 const flat=await frame(4,true);await p.evaluate('(window.flatWaterPixels=window.readPixels(),true)');await frame(8,true);assert.equal(await changedSince('flatWaterPixels'),0,'波纹强度为零时水面不随时间波动');
 await p.evaluate(`window.setWaterAppearance(1,0.65)`);
 assert.notEqual(hash(flat),hash(await frame(8,true)),'波纹强度需要改变画面');
 assert.deepEqual(p.errors,[]);
 console.log('WATER_RENDER_PASS',JSON.stringify({first:createHash('sha256').update(first).digest('hex'),second:createHash('sha256').update(second).digest('hex'),changedPixels,disabledTimeFrozen:true}));
} finally {await browser.close()}
