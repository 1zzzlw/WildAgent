import assert from 'node:assert/strict'
import { join } from 'node:path'
import { tmpdir } from 'node:os'
import { launchEditorBrowser } from './editor-browser.mjs'

// 先运行 serve-editor-smoke.mjs 与 editor_smoke_server.py；使用独立浏览器和临时存储。
const browser = await launchEditorBrowser(process.env.EDITOR_URL || 'http://127.0.0.1:5178/')
const p = browser.page
const viewport = code => p.evaluate(`(() => {
  const s = document.querySelector('.canvas-viewport').__vueParentComponent.setupState;
  ${code}
})()`)
const nextFrame = () => p.evaluate('new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))')
const mouse = (type, point, extra = {}) => p.send('Input.dispatchMouseEvent', {
  type, ...point, ...(type === 'mouseMoved' ? {} : { button: 'left', clickCount: 1 }), ...extra,
})
async function clickAt(point, count = 1, modifiers = 0) {
  await mouse('mouseMoved', point, { modifiers })
  await mouse('mousePressed', point, { clickCount: count, modifiers })
  await mouse('mouseReleased', point, { clickCount: count, modifiers })
  await nextFrame()
}
async function pointFor(id) {
  return viewport(`
    const bounds = s.collectElementBounds(s.translationRenderedIds([${JSON.stringify(id)}]));
    const point = bounds.getCenter(s.sceneBoundsCenter.clone()).project(s.camera);
    const rect = s.renderer.domElement.getBoundingClientRect();
    return { x: rect.x + (point.x + 1) * rect.width / 2, y: rect.y + (1 - point.y) * rect.height / 2 };
  `)
}
async function doubleClick(id, modifiers = 0) {
  await clickAt(await pointFor(id), 1, modifiers)
  await clickAt(await pointFor(id), 2, modifiers)
}
const selected = () => viewport('return { ids: [...s.selectionStore.selectedIds], highlights: s.selectionHelpers.length, movable: !!s.transformControls.object };')
async function dragAndUndo(id, kind) {
  const axis = await viewport(`
    s.transformControls.updateMatrixWorld(true);
    const handle = s.transformControls._gizmo.gizmo.translate.children.find(h => {
      h.geometry.computeBoundingBox();
      return h.name === 'X' && h.visible && h.geometry.boundingBox.max.x > 0.5;
    });
    const point = handle.geometry.boundingBox.getCenter(s.sceneBoundsCenter.clone())
      .applyMatrix4(handle.matrixWorld).project(s.camera);
    const rect = s.renderer.domElement.getBoundingClientRect();
    return {x: rect.x + (point.x + 1) * rect.width / 2, y: rect.y + (1 - point.y) * rect.height / 2};
  `)
  await mouse('mouseMoved', axis)
  assert.equal(await viewport('return s.transformControls.axis;'), 'X')
  const position = () => viewport(`return [...s.sceneStore.document.blueprint.geometry.${kind}.find(e => e.id === ${JSON.stringify(id)}).position];`)
  const before = await position()
  await mouse('mousePressed', axis)
  for (let i = 1; i <= 6; i++) await mouse('mouseMoved', {x: axis.x + i * 8, y: axis.y}, {button: 'left', buttons: 1})
  await mouse('mouseReleased', {x: axis.x + 48, y: axis.y})
  await p.wait('!document.querySelector("button[aria-label=撤销]").disabled')
  await nextFrame()
  const after = await position()
  assert.ok(Math.abs(after[0] - before[0]) > 0.01)
  assert.equal(after[1], before[1]); assert.equal(after[2], before[2])
  await p.click('button[aria-label="撤销"]')
  await nextFrame()
  assert.deepEqual(await position(), before)
}
async function assertFpsLayout() {
  const layout = await p.evaluate(`(() => {
    const button = document.querySelector('.render-tool').getBoundingClientRect();
    const icon = document.querySelector('.render-tool .el-icon').getBoundingClientRect();
    const number = document.querySelector('.fps-number').getBoundingClientRect();
    return { iconX: icon.x + icon.width / 2, numberX: number.x + number.width / 2,
      centerX: button.x + button.width / 2, centerY: button.y + button.height / 2,
      groupY: (icon.top + number.bottom) / 2, iconBottom: icon.bottom, numberTop: number.top,
      inside: icon.top >= button.top && number.bottom <= button.bottom,
      visible: button.left >= 0 && button.top >= 0 && button.right <= innerWidth && button.bottom <= innerHeight
        && !!document.elementFromPoint(button.x + button.width / 2, button.y + button.height / 2)?.closest('.render-tool') };
  })()`)
  assert.ok(layout.inside && layout.iconBottom < layout.numberTop, JSON.stringify(layout))
  assert.ok(layout.visible, JSON.stringify(layout))
  assert.ok(Math.abs(layout.iconX - layout.centerX) < 1 && Math.abs(layout.numberX - layout.centerX) < 1)
  assert.ok(Math.abs(layout.groupY - layout.centerY) < 1, JSON.stringify(layout))
}

try {
  await p.wait('!!document.querySelector(".enter-button")')
  // 模拟世界环境已存在、编辑视口刚挂载，不能继续把本地默认 day 当成实际时段。
  await p.evaluate(`import('/src/renderer/worldEnvironmentRuntime.ts').then(m => m.updateWorldEnvironmentState({timeOfDay: 0}))`)
  await p.evaluate(`(() => {
    const input = document.querySelector('input[aria-label="访客名称"]');
    input.value = '视口交互回归'; input.dispatchEvent(new Event('input', {bubbles: true}));
  })()`)
  await p.click('.enter-button')
  await p.wait('!!document.querySelector(".canvas-viewport canvas")')
  assert.equal(await viewport('return s.timeOfDay;'), 'night')
  await p.click('button[aria-label="视口"]')
  await p.click('button[aria-label="光照时段"]')
  for (const [label, value, hour] of [['白天', 'day', 12], ['白天', 'day', 12], ['黄昏', 'sunset', 18], ['夜晚', 'night', 0], ['白天', 'day', 12]]) {
    await p.click(`button[aria-label="光照时段：${label}"]`)
    await p.wait(`document.querySelector('button[aria-label="光照时段：${label}"]').getAttribute('aria-pressed') === 'true'`)
    assert.equal(await viewport('return s.timeOfDay;'), value)
    assert.equal(await p.evaluate(`import('/src/renderer/worldEnvironmentRuntime.ts').then(m => m.getWorldEnvironmentState().timeOfDay)`), hour)
    assert.ok(await viewport('return s.directionalLight.intensity > 0 && s.renderer.toneMappingExposure > 0;'))
  }
  console.log('PASS initial world time, repeat noon selection, day/sunset/night switching')

  await p.click('button[aria-label="场景环境"]')
  for (const [label, value] of [['极简', 'minimal'], ['草地', 'meadow'], ['雪山', 'alpine'], ['沙漠', 'desert'], ['秋林', 'autumn']]) {
    const selector = `button[aria-label="场景环境：${label}"]`
    assert.equal(await p.evaluate(`document.querySelector('${selector} svg')?.dataset.environment`), value)
    await p.click(selector)
    await nextFrame()
    assert.equal(await p.evaluate('document.querySelector("button[aria-label=场景环境] svg").dataset.environment'), value)
    assert.equal(await viewport('return s.environmentPresetId;'), value)
  }
  await assertFpsLayout()
  await p.screenshot(join(tmpdir(), 'wild-viewport-environments.png'))
  await p.click('button[aria-label="场景环境：极简"]')
  await p.click('button[aria-label="视口"]')
  console.log('PASS environment icons match each preset and current category')

  assert.equal(await viewport(`return s.sceneStore.loadBlueprint({
    meta: {version: '1.0', type: 'building', name: '视口交互回归'},
    geometry: {
      elements: [{id: 'sphere', type: 'primitive', shape: 'sphere', position: [-2, 1, 0], radius: 0.8, material: 'default'}],
      components: [{id: 'lamp', type: 'light', fixtureType: 'table_lamp', position: [2, 0, 0], height: 1.5, shadeRadius: 0.5, draggable: true}]
    }, materials: {}, behaviors: {}
  });`), true)
  await nextFrame()
  await clickAt(await pointFor('sphere'))
  assert.deepEqual(await selected(), {ids: ['sphere'], highlights: 1, movable: false})
  await doubleClick('sphere')
  assert.deepEqual(await selected(), {ids: ['sphere'], highlights: 1, movable: true})
  await p.screenshot(join(tmpdir(), 'wild-viewport-double-click.png'))

  // 真正拖动移动轴；验证生成的 Patch 与撤销，避免只检查控件可见性。
  await dragAndUndo('sphere', 'elements')

  await clickAt(await pointFor('lamp'))
  assert.deepEqual(await selected(), {ids: ['lamp'], highlights: 1, movable: false})
  await doubleClick('lamp')
  assert.deepEqual(await selected(), {ids: ['lamp'], highlights: 1, movable: true})
  await dragAndUndo('lamp', 'components')
  await clickAt(await pointFor('sphere'), 1, 8) // Shift 多选只高亮。
  assert.deepEqual(await selected(), {ids: ['lamp', 'sphere'], highlights: 2, movable: false})
  await doubleClick('sphere', 8)
  assert.deepEqual(await selected(), {ids: ['lamp', 'sphere'], highlights: 2, movable: true})
  await doubleClick('lamp')
  assert.equal((await selected()).movable, true)

  await p.click('button[aria-label="视口"]'); await p.click('button[aria-label="视图模式"]')
  await p.click('button[aria-label="视图模式：展示"]'); await nextFrame()
  assert.equal((await selected()).movable, false)
  await p.click('button[aria-label="视图模式：编辑"]'); await nextFrame()
  assert.deepEqual(await selected(), {ids: ['lamp'], highlights: 1, movable: false})
  await p.click('button[aria-label="视口"]')
  await doubleClick('lamp')
  const blank = await viewport('const r=s.renderer.domElement.getBoundingClientRect(); return {x:r.right-120,y:r.top+90};')
  await clickAt(blank)
  assert.deepEqual(await selected(), {ids: [], highlights: 0, movable: false})
  // 在空处拖动相机不应误选或启用移动轴。
  await mouse('mousePressed', blank)
  await mouse('mouseMoved', {x: blank.x - 45, y: blank.y + 15}, {button: 'left', buttons: 1})
  await mouse('mouseReleased', {x: blank.x - 45, y: blank.y + 15})
  assert.deepEqual(await selected(), {ids: [], highlights: 0, movable: false})
  console.log('PASS click highlight, double-click gizmo, native/component drag, undo, multiselect, mode and blank/orbit reset')

  await p.click('button[aria-label="收起左侧面板"]')
  await p.wait('document.querySelector(".dock-panel").getBoundingClientRect().width < 1')
  await doubleClick('lamp')
  assert.deepEqual(await selected(), {ids: ['lamp'], highlights: 1, movable: true})
  assert.equal(await viewport('return s.uiStore.panelOpen;'), false)
  await p.resize(740, 480); await nextFrame(); await assertFpsLayout()
  await p.screenshot(join(tmpdir(), 'wild-viewport-compact.png'))
  assert.deepEqual(p.errors, [], '浏览器运行时或着色器错误')
  console.log('PASS FPS icon/number centered at desktop and compact sizes; no runtime/shader errors')
} finally {
  await browser.close()
}
