import assert from 'node:assert/strict';
import { launchEditorBrowser } from './editor-browser.mjs';
const browser=await launchEditorBrowser('http://127.0.0.1:5178/scripts/opening-preview.html');
try{const p=browser.page;await p.wait('window.ready');assert.deepEqual(await p.evaluate('window.diagnostics.filter(d=>d.level==="error")'),[]);
const directory='E:/AgentProject/WildAgent/docs/10月22日/03-前端与门窗优化/浏览器验证/';
await p.screenshot(directory+'07-门窗关闭.png');await p.evaluate('window.openAll()');await p.wait('window.state().filter(m=>m.name.startsWith("double")).every(m=>m.progress===1)');await p.screenshot(directory+'08-门窗打开.png');
await p.evaluate('window.openAll()');await p.wait('window.state().filter(m=>m.name.startsWith("double")).every(m=>m.progress===0)');
assert.deepEqual(p.errors,[]);console.log('OPENING_RENDER_PASS',JSON.stringify(await p.evaluate('window.state()')));
}finally{await browser.close()}
