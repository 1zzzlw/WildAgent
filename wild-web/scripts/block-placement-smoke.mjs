import assert from 'node:assert/strict'
import { join } from 'node:path'
import { tmpdir } from 'node:os'
import { launchEditorBrowser } from './editor-browser.mjs'

// 先启动serve-editor-smoke.mjs和editor_smoke_server.py；使用隔离临时数据。
const browser = await launchEditorBrowser(process.env.EDITOR_URL || 'http://127.0.0.1:5178/')
const p = browser.page
const evidence = process.env.PLACEMENT_EVIDENCE || join(tmpdir(), 'wild-block-placement')
const vp = code => p.evaluate(`(() => {
  const s = document.querySelector('.canvas-viewport').__vueParentComponent.setupState;
  ${code}
})()`)
const mouse = (type, point, extra = {}) => p.send('Input.dispatchMouseEvent', {
  type, ...point, ...(type === 'mouseMoved' ? {} : { button: 'left', clickCount: 1 }), ...extra,
})
const near = (a, b, tolerance = 1e-5) => a.forEach((v, i) => assert.ok(Math.abs(v - b[i]) < tolerance, `${a} / ${b}`))
const previewBounds = () => vp(`
  s.placementPreview.root.updateMatrixWorld(true);
  const points = [];
  s.placementPreview.root.traverse(mesh => {
    if (!mesh.isMesh) return;
    mesh.geometry.computeBoundingBox();
    const box = mesh.geometry.boundingBox.clone().applyMatrix4(mesh.matrixWorld).translate(s.sceneGroup.position.clone().negate());
    points.push(...box.min.toArray(), ...box.max.toArray());
  });
  return { min: [0,1,2].map(i => Math.min(...points.filter((_,j) => j%6 === i))),
    max: [0,1,2].map(i => Math.max(...points.filter((_,j) => j%6 === i+3))) };
`)
async function checkPlacedBounds(id, expected, tolerance = 1e-5) {
  const actual = await vp(`const box = s.collectElementBounds(s.translationRenderedIds([${JSON.stringify(id)}])).translate(s.sceneGroup.position.clone().negate()); return {min:box.min.toArray(),max:box.max.toArray()};`)
  near(actual.min, expected.min, tolerance); near(actual.max, expected.max, tolerance)
}
const state = () => vp(`return {
  revision: s.sceneStore.document.revision,
  blueprint: JSON.parse(JSON.stringify(s.sceneStore.document.blueprint)),
  pending: !!s.placement.request, preview: !!s.placementPreview?.root.visible,
  draft: s.placementDraft ? JSON.parse(JSON.stringify(s.placementDraft)) : null,
};`)
async function select(label) {
  await p.evaluate(`(() => {
    const item = [...document.querySelectorAll('.block-item')].find(el => el.querySelector('.block-label').textContent === ${JSON.stringify(label)});
    item.scrollIntoView({block: 'nearest'}); item.dataset.placementTest = 'selected';
  })()`)
  await p.click('[data-placement-test=selected]')
  await p.evaluate(`document.querySelector('[data-placement-test=selected]').removeAttribute('data-placement-test')`)
}
async function screen(point) {
  return vp(`
    s.sceneGroup.updateMatrixWorld(true);
    const point = s.sceneGroup.localToWorld(s.sceneBoundsCenter.clone().fromArray(${JSON.stringify(point)})).project(s.camera);
    const rect = s.renderer.domElement.getBoundingClientRect();
    return { x: rect.x + (point.x + 1) * rect.width / 2, y: rect.y + (1 - point.y) * rect.height / 2 };
  `)
}
async function hover(point) {
  const pixel = await screen(point)
  await mouse('mouseMoved', pixel)
  await p.wait(`!!document.querySelector('.canvas-viewport').__vueParentComponent.setupState.placementDraft`)
  return pixel
}
async function click(point) {
  await mouse('mousePressed', point)
  await mouse('mouseReleased', point)
  await p.wait(`!document.querySelector('.canvas-viewport').__vueParentComponent.setupState.sceneStore.isReconstructing`)
  await p.wait(`!document.querySelector('.canvas-viewport').__vueParentComponent.setupState.placement.request`)
}
async function escape() {
  await p.send('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Escape', code: 'Escape', windowsVirtualKeyCode: 27 })
  await p.send('Input.dispatchKeyEvent', { type: 'keyUp', key: 'Escape', code: 'Escape', windowsVirtualKeyCode: 27 })
}
const fixture = {
  meta: { version: '1.1', type: 'building', name: '鼠标放置回归' },
  geometry: { elements: [
    { id: 'floor', type: 'floor', from: [30, 0, 10], to: [50, 0, 25], thickness: .2 },
    { id: 'wall_a', type: 'wall', from: [32, .2, 12], to: [38, 3.4, 12], thickness: .24 },
    { id: 'wall_b', type: 'wall', from: [42, .2, 18], to: [48, 3.4, 18], thickness: .24 },
    { id: 'roof_a', type: 'roof', roofType: 'gable', position: [35, 3.6, 12], span: 7, depth: 4, height: 1.2, thickness: .18 },
    { id: 'roof_b', type: 'roof', roofType: 'gable', position: [45, 3.6, 18], span: 7, depth: 4, height: 1.2, thickness: .18 },
  ], components: [] }, materials: {},
}
async function loadFixture() {
  await vp(`return s.sceneStore.loadBlueprint(${JSON.stringify(fixture)});`)
  await p.wait(`!document.querySelector('.canvas-viewport').__vueParentComponent.setupState.sceneStore.isReconstructing`)
}

try {
  await p.wait(`!!document.querySelector('.enter-button')`)
  await p.evaluate(`(() => { const input = document.querySelector('input'); input.value = '构件放置回归'; input.dispatchEvent(new Event('input', {bubbles:true})); })()`)
  await p.click('.enter-button')
  await p.wait(`!!document.querySelector('.canvas-viewport canvas')`)
  await p.click('button[aria-label=构件库]')
  const empty = await state()
  await select('通用球体')
  assert.equal((await state()).revision, empty.revision)
  let pixel = await hover([3, 0, 2])
  const first = await state()
  assert.equal(first.blueprint.geometry.elements.length, 0)
  near(first.draft.operation.element.position, [3, .5, 2])
  await p.screenshot(join(evidence, '01-empty-preview.png'))
  await click(pixel)
  assert.equal((await state()).blueprint.geometry.elements.length, 1)
  const projected = await screen([3, 0, 2])
  assert.ok(Math.hypot(projected.x - pixel.x, projected.y - pixel.y) < 1, '确认后显示位置保持不变')
  await p.click('button[aria-label=撤销]')
  await p.wait(`document.querySelector('.canvas-viewport').__vueParentComponent.setupState.sceneStore.document.blueprint.geometry.elements.length === 0`)
  console.log('PASS empty scene, preview without mutation, cursor placement, stable view, undo')

  await loadFixture()
  await select('通用球体')
  const before = await state()
  await hover([37, .2, 23])
  const a = await state()
  pixel = await hover([39, .2, 23])
  const b = await state()
  assert.equal(b.revision, before.revision)
  assert.notDeepEqual(a.draft.anchor, b.draft.anchor)
  near(b.draft.operation.element.position, [39, .7, 23])
  await p.screenshot(join(evidence, '02-position-preview.png'))
  await click(pixel)
  const after = await state()
  assert.deepEqual(after.blueprint.geometry.elements.find(e => e.id === b.draft.operation.element.id), b.draft.operation.element)
  assert.equal(after.revision, before.revision + 1)
  assert.equal(after.preview, false)
  console.log('PASS moving preview, model surface elevation, off-origin coordinates, exact commit')

  for (const label of ['招牌', '墙体', '柱子', '地板', '屋顶', '栏杆', '坡道', '烟囱', '灯泡', '台灯']) {
    await loadFixture(); await select(label)
    pixel = await hover([37, .2, 23])
    const draft = (await state()).draft.operation
    const bounds = await previewBounds()
    await click(pixel)
    const bp = (await state()).blueprint, item = draft.element || draft.component
    assert.deepEqual([...bp.geometry.elements, ...bp.geometry.components || []].find(e => e.id === item.id), item, label)
    // 正式招牌额外贴一层偏移2mm的文字面；幽灵预览只显示构件实体。
    await checkPlacedBounds(item.id, bounds, label === '招牌' ? .0021 : 1e-5)
  }
  console.log('PASS all free-standing library types preview and commit')

  for (const label of ['门', '窗', '雨棚', '阳台', '凸窗']) {
    await loadFixture(); await select(label)
    pixel = await hover([46, 1.6, 18.12])
    const bounds = await previewBounds()
    const draft = (await state()).draft.operation.component
    assert.equal(draft.parentWall, 'wall_b', label + ' follows hovered wall')
    await hover([44, 1.4, 18.12])
    assert.notEqual((await state()).draft.operation.component.from[0], draft.from[0], label)
    pixel = await hover([46, 1.6, 18.12])
    if (label === '窗') await p.screenshot(join(evidence, '03-wall-window-preview.png'))
    await click(pixel)
    assert.deepEqual((await state()).blueprint.geometry.components[0], draft)
    await checkPlacedBounds(draft.id, bounds)
  }
  console.log('PASS all wall components: hovered host and wall-local position')

  await loadFixture(); await select('檐口')
  pixel = await hover([45, 4.8, 18])
  assert.equal((await state()).draft.operation.component.parentRoof, 'roof_b')
  const corniceBounds = await previewBounds()
  const corniceId = (await state()).draft.operation.component.id
  await click(pixel)
  await checkPlacedBounds(corniceId, corniceBounds)
  console.log('PASS cornice uses hovered roof')

  const implicit = structuredClone(fixture)
  implicit.geometry.elements = [
    ...[[[32,12],[38,12]],[[38,12],[38,18]],[[38,18],[32,18]],[[32,18],[32,12]]].map(([a,b],i) => (
      {id:'w'+i,type:'wall',from:[a[0],.2,a[1]],to:[b[0],3.4,b[1]],thickness:.24}
    )),
    {id:'implicit_roof',type:'roof',roofType:'gable',span:8,depth:8,height:1.2,thickness:.18},
  ]
  await vp(`return s.sceneStore.loadBlueprint(${JSON.stringify(implicit)});`)
  await select('檐口')
  pixel = await hover([35,4.6,15])
  const implicitBounds = await previewBounds(), implicitId = (await state()).draft.operation.component.id
  await click(pixel)
  await checkPlacedBounds(implicitId, implicitBounds)
  console.log('PASS implicit roof origin: preview geometry matches final geometry')

  await loadFixture(); await select('门')
  pixel = await screen([37, .2, 23]); await mouse('mouseMoved', pixel)
  await p.wait(`document.querySelector('.placement-hint')?.textContent.includes('直线墙面')`)
  assert.equal((await state()).draft, null)
  const invalid = await state()
  await mouse('mousePressed', pixel); await mouse('mouseReleased', pixel)
  assert.equal((await state()).revision, invalid.revision)
  await escape()
  assert.equal((await state()).pending, false)
  assert.equal((await state()).preview, false)

  await select('柱子'); await hover([37, .2, 23])
  const cancelBefore = await state()
  await mouse('mouseMoved', { x: 30, y: 30 })
  assert.equal((await state()).preview, false)
  pixel = await hover([37, .2, 23])
  await mouse('mousePressed', pixel, { button: 'right' }); await mouse('mouseReleased', pixel, { button: 'right' })
  assert.equal((await state()).pending, false)
  assert.equal((await state()).revision, cancelBefore.revision)
  await select('柱子'); pixel = await hover([37, .2, 23])
  await mouse('mousePressed', pixel)
  await mouse('mouseMoved', { x: pixel.x + 20, y: pixel.y }, { buttons: 1 })
  await mouse('mouseReleased', { x: pixel.x + 20, y: pixel.y })
  assert.equal((await state()).revision, cancelBefore.revision, '拖动不误放置')
  await loadFixture()
  assert.equal((await state()).pending, false)
  assert.deepEqual(p.errors, [], 'runtime/shader errors')
  await p.screenshot(join(evidence, '04-finished.png'))
  console.log('PASS invalid host, Escape/right-click, pointer leave, drag protection, scene switch; no runtime/shader errors')
} catch (error) {
  console.error(await state().catch(() => null))
  await p.screenshot(join(evidence, 'failure.png')).catch(() => {})
  throw error
} finally {
  await browser.close()
}
