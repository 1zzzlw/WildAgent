import assert from 'node:assert/strict'
import { mkdir, mkdtemp, readFile, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { resolve, join } from 'node:path'
import { launchEditorBrowser } from './editor-browser.mjs'

const output = resolve(process.env.GLB_EVIDENCE || '../docs/10月28日/GLB模型导出/浏览器验证')
await mkdir(output, { recursive: true })
const downloads = await mkdtemp(join(tmpdir(), 'wild-glb-download-'))
const browser = await launchEditorBrowser(process.env.EDITOR_URL || 'http://127.0.0.1:5184/')
const p = browser.page
try {
  // 导出是纯前端操作；隔离真实服务器的会话恢复与协作推送。
  await p.send('Network.enable')
  await p.send('Network.setBlockedURLs', { urls: ['*/api/*', '*/ws/*'] })
  await p.wait('!!document.querySelector(".enter-button")')
  await p.evaluate(`(() => { const input = document.querySelector('input'); input.value = 'GLB导出回归'; input.dispatchEvent(new Event('input', {bubbles:true})); })()`)
  await p.click('.enter-button')
  await p.wait(`!!document.querySelector('button[aria-label="导出 GLB"]')`)
  assert.equal(await p.evaluate(`document.querySelector('button[aria-label="导出 GLB"]').disabled`), true)
  const roundTrip = await p.evaluate(`(async () => {
    const threeUrl = performance.getEntriesByType('resource').map(entry => entry.name)
      .find(url => new URL(url).pathname.endsWith('/.vite/deps/three.js'));
    const THREE = await import(threeUrl);
    const { exportBuildingGlb } = await import('/src/renderer/glbExport.ts');
    const { GLTFLoader } = await import('/node_modules/three/examples/jsm/loaders/GLTFLoader.js');
    const root = new THREE.Group();
    root.position.set(-100, 0, -200); root.visible = false;
    root.userData.runtime = root;
    const canvas = document.createElement('canvas'); canvas.width = canvas.height = 4;
    canvas.getContext('2d').fillRect(0, 0, 4, 4);
    const material = new THREE.MeshPhysicalMaterial({
      map: new THREE.CanvasTexture(canvas), roughness: .35, metalness: .2,
      transmission: .6, ior: 1.45, thickness: .02,
    });
    material.userData.runtime = material;
    material.onBeforeCompile = () => {};
    const geometry = new THREE.BoxGeometry(1, 1, 1);
    geometry.setAttribute('color', new THREE.Float32BufferAttribute(new Array(geometry.attributes.position.count * 3).fill(.7), 3));
    material.vertexColors = true;
    let disposed = 0;
    material.addEventListener('dispose', () => disposed++);
    geometry.addEventListener('dispose', () => disposed++);
    const nested = new THREE.Group(); nested.position.set(10, 0, 5); root.add(nested);
    const box = new THREE.Mesh(geometry, material); box.name = 'textured-box';
    box.position.set(1, .5, 0); box.userData.elementId = 'box'; nested.add(box);
    const instances = new THREE.InstancedMesh(geometry, material, 3); instances.name = 'repeated';
    for (let i = 0; i < 3; i++) instances.setMatrixAt(i, new THREE.Matrix4().makeTranslation(20 + i * 2, 1, 8));
    root.add(instances);
    const hidden = new THREE.Mesh(geometry, material); hidden.name = 'hidden'; hidden.visible = false; root.add(hidden);
    root.add(new THREE.GridHelper(10, 10), new THREE.PointLight());
    const result = await exportBuildingGlb(root, 'round-trip');
    const gltf = await new GLTFLoader().parseAsync(result.data, '');
    gltf.scene.updateMatrixWorld(true);
    const loaded = gltf.scene.getObjectByName('textured-box');
    const repeated = gltf.scene.getObjectByName('repeated');
    const errors = [];
    for (const candidate of [new THREE.Group(), new THREE.Group().add(new THREE.Mesh(geometry, new THREE.ShaderMaterial())),
      new THREE.Group().add(new THREE.Mesh(geometry, new THREE.MeshStandardMaterial({ map: new THREE.Texture() })))]) {
      try { const exported = await exportBuildingGlb(candidate, 'compatible'); errors.push(exported.warnings.join(';')); }
      catch (error) { errors.push(error.message); }
    }
    return {
      bytes: result.data.byteLength, simplified: result.simplifiedMaterials,
      position: loaded.getWorldPosition(new THREE.Vector3()).toArray(),
      elementId: loaded.userData.elementId, instances: repeated.children.length,
      lastInstance: repeated.children[2].getWorldPosition(new THREE.Vector3()).toArray(),
      requiresInstancing: !!gltf.parser.json.extensionsRequired?.includes('EXT_mesh_gpu_instancing'),
      textureWidth: loaded.material.map.image.width, vertexColors: !!loaded.geometry.attributes.color,
      transmission: loaded.material.transmission, roughness: loaded.material.roughness,
      hiddenExported: !!gltf.scene.getObjectByName('hidden'),
      liveUnchanged: !root.visible && root.position.x === -100 && material.userData.runtime === material && disposed === 0,
      errors,
    };
  })()`)
  assert.ok(roundTrip.bytes > 1000)
  assert.equal(roundTrip.simplified, true)
  assert.deepEqual(roundTrip.position, [11, .5, 5])
  assert.equal(roundTrip.elementId, 'box')
  assert.equal(roundTrip.instances, 3)
  assert.equal(roundTrip.requiresInstancing, false)
  assert.deepEqual(roundTrip.lastInstance, [24, 1, 8])
  assert.equal(roundTrip.textureWidth, 4)
  assert.equal(roundTrip.vertexColors, true)
  assert.equal(roundTrip.transmission, .6)
  assert.equal(roundTrip.roughness, .35)
  assert.equal(roundTrip.hiddenExported, false)
  assert.equal(roundTrip.liveUnchanged, true)
  assert.match(roundTrip.errors[0], /没有可导出/)
  assert.match(roundTrip.errors[1], /转换为标准 PBR/)
  assert.match(roundTrip.errors[2], /贴图尚未就绪/)
  console.log('PASS textured GLB round-trip, physical material, vertex colors, instances, coordinates, failure cleanup')

  const fixture = {
    meta: { version: '1.1', type: 'building', name: 'GLB导出验证.wild' },
    geometry: { elements: [
      { id: 'floor', type: 'floor', from: [30, 0, 10], to: [40, 0, 18], thickness: .2 },
      { id: 'wall', type: 'wall', from: [30, .2, 10], to: [40, 3.2, 10], thickness: .24 },
    ] }, materials: {},
  }
  await p.evaluate(`(async () => {
    const s = document.querySelector('.canvas-viewport').__vueParentComponent.setupState;
    await s.sceneStore.loadBlueprint(${JSON.stringify(fixture)});
    s.renderPanel.showEdges = true;
    s.renderPanel.sectionEnabled = true;
    window.beforeGlb = JSON.stringify(s.sceneStore.document);
    const original = HTMLAnchorElement.prototype.click;
    HTMLAnchorElement.prototype.click = function () {
      if (this.download.endsWith('.glb')) {
        window.exportedName = this.download;
        window.exportedGlb = fetch(this.href).then(response => response.arrayBuffer());
      }
      return original.call(this);
    };
  })()`)
  await p.wait(`!document.querySelector('button[aria-label="导出 GLB"]').disabled`)
  await p.send('Browser.setDownloadBehavior', { behavior: 'allow', downloadPath: downloads })
  await p.screenshot(join(output, '01-导出按钮.png'))
  await p.click('button[aria-label="导出 GLB"]')
  await p.wait(`!!window.exportedGlb && !document.querySelector('button[aria-label="导出 GLB"]').disabled`)
  const ui = await p.evaluate(`(async () => {
    const { GLTFLoader } = await import('/node_modules/three/examples/jsm/loaders/GLTFLoader.js');
    const buffer = await window.exportedGlb;
    const gltf = await new GLTFLoader().parseAsync(buffer, '');
    const names = []; gltf.scene.traverse(object => { if (object.isMesh) names.push(object.name); });
    const s = document.querySelector('.canvas-viewport').__vueParentComponent.setupState;
    return { name: window.exportedName, bytes: buffer.byteLength, names,
      unchanged: JSON.stringify(s.sceneStore.document) === window.beforeGlb,
      edgesStillEnabled: s.renderPanel.showEdges && !s.sceneGroup.visible,
      sectionStillEnabled: s.renderPanel.sectionEnabled };
  })()`)
  assert.equal(ui.name, 'GLB导出验证.glb')
  assert.deepEqual(ui.names.sort(), ['floor', 'wall'])
  assert.equal(ui.unchanged, true)
  assert.equal(ui.edgesStillEnabled, true)
  assert.equal(ui.sectionStillEnabled, true)
  let downloaded
  for (let i = 0; i < 100; i++) {
    try { downloaded = await readFile(join(downloads, ui.name)); break } catch { await new Promise(resolve => setTimeout(resolve, 100)) }
  }
  assert.ok(downloaded, '浏览器应实际下载 GLB 文件')
  assert.equal(downloaded.readUInt32LE(0), 0x46546c67)
  assert.equal(downloaded.readUInt32LE(4), 2)
  assert.equal(downloaded.length, ui.bytes)
  await writeFile(join(output, ui.name), downloaded)
  assert.deepEqual(p.errors, [])
  await p.screenshot(join(output, '02-导出完成.png'))
  await writeFile(join(output, '验证结果.json'), JSON.stringify({ roundTrip, ui, shaderErrors: p.errors }, null, 2))
  console.log('PASS toolbar download, empty-state guard, edge/section independence, no helpers, unchanged WILD document')
} finally { await browser.close() }
