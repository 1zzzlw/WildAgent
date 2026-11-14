import assert from 'node:assert/strict'
import { mkdir, writeFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { createServer } from 'vite'
import { launchEditorBrowser } from './editor-browser.mjs'

const server = await createServer({ server: { host: '127.0.0.1', port: 0 }, logLevel: 'error' })
let browser
try {
  await server.listen()
  const address = server.httpServer.address()
  browser = await launchEditorBrowser(`http://127.0.0.1:${address.port}/scripts/behavior-preview.html`)
  const page = browser.page
  await page.wait('window.ready')
  await page.click('#prepare')
  await page.wait('window.report().meshes === 2')
  await page.click('#play')
  await page.wait('window.report().time > .2 && window.report().decodedFrames > 2')
  const playing = await page.evaluate('window.report()')
  playing.visibleTextPixels = await page.evaluate('window.whitePixels()')
  assert.ok(playing.visibleTextPixels > 50, '屏幕须显示完整视频中的白色文字，不能沿用建筑 UV 裁切掉内容')
  const output = resolve('../.workbuddy/behavior-runtime')
  await mkdir(output, { recursive: true })
  await page.screenshot(resolve(output, 'video-playing.png'))
  await page.click('#play')
  await page.wait('window.report().paused === true')
  const paused = await page.evaluate('(async () => { const a=window.report(); await new Promise(r=>setTimeout(r,250)); return {before:a,after:window.report()} })()')
  assert.ok(Math.abs(paused.after.time-paused.before.time)<.05)
  await page.click('#replace')
  await page.wait('window.report().previousReleased === true')
  const replaced = await page.evaluate('window.report()')
  await page.click('#play')
  await page.wait('window.report().time > .1 && window.report().decodedFrames > 0')
  await page.click('#dispose')
  await page.wait('window.report().meshes === 0 && window.report().textures === 0')
  const cleared = await page.evaluate('window.report()')
  assert.deepEqual(page.errors, [])
  const result = { status: 'PASS', playing, paused, replaced, cleared,
    scope: '独立 Chromium + 本地生成 WebM：真实解码、WebGL 视频纹理、播放暂停、换源和资源释放；未调用模型或外部视频服务' }
  await writeFile(resolve(output, 'browser-result.json'), JSON.stringify(result, null, 2))
  console.log(JSON.stringify(result, null, 2))
} finally {
  await browser?.close()
  await server.close()
}
