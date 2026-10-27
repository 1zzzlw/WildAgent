import assert from 'node:assert/strict'
import { readFile, writeFile, mkdir } from 'node:fs/promises'
import { createServer } from 'vite'
import * as THREE from 'three'
import { launchEditorBrowser } from './editor-browser.mjs'

const output = '../docs/10月27日/渲染性能光影与三种别墅/验证'
await mkdir(output, { recursive: true })
const vite = await createServer({ server: { middlewareMode: true }, appType: 'custom', logLevel: 'error' })
const fits = []
try {
  const { WorldLightingRig } = await vite.ssrLoadModule('/src/renderer/lightingRuntime.ts')
  for (const size of [[28, 8, 22], [45, 4, 8], [8, 30, 8]]) for (const elevation of [6, 42, 85, 90]) for (const azimuth of [0, 45, 130]) {
    const scene = new THREE.Scene(), rig = new WorldLightingRig(scene)
    const direction = new THREE.Vector3().setFromSphericalCoords(1, THREE.MathUtils.degToRad(90 - elevation), THREE.MathUtils.degToRad(azimuth))
    const center = new THREE.Vector3(4, size[1] / 2 - 0.8, -3)
    rig.fitToBounds(center, new THREE.Vector3(...size), direction)
    rig.key.updateMatrixWorld(); rig.key.shadow.updateMatrices(rig.key)
    for (const sx of [-1, 1]) for (const sy of [-1, 1]) for (const sz of [-1, 1]) {
      const point = new THREE.Vector3(center.x + sx * size[0] / 2, center.y + sy * size[1] / 2, center.z + sz * size[2] / 2)
      const ground = point.clone().addScaledVector(direction, -(point.y + 0.8) / direction.y)
      for (const p of [point, ground]) {
        p.project(rig.key.shadow.camera)
        assert.ok(Math.max(Math.abs(p.x), Math.abs(p.y), Math.abs(p.z)) <= 1.000001, `阴影裁切 ${JSON.stringify({ size, elevation, azimuth, p })}`)
      }
    }
    const camera = rig.key.shadow.camera
    fits.push({ size, elevation, azimuth, width: camera.right - camera.left, height: camera.top - camera.bottom })
    rig.key.shadow.needsUpdate=false
    assert.equal(rig.setShadowMapSize(1024),true)
    assert.equal(rig.key.shadow.needsUpdate,true,'切换分辨率必须刷新被释放的阴影贴图')
    assert.ok(Math.abs(rig.key.shadow.normalBias-Math.max(.001,1.5*2*rig.extent/1024))<1e-9,'切档后bias仍按纹素推导')
    rig.dispose()
  }
} finally { await vite.close() }

const browser = await launchEditorBrowser('http://127.0.0.1:5178/scripts/material-mechanism-preview.html')
try {
  const p = browser.page
  await p.wait('window.ready')
  const bp = JSON.parse(await readFile('../docs/10月27日/岚石光庭-交互材质别墅.wild', 'utf8'))
  await p.evaluate('window.viewBlueprint(' + JSON.stringify(bp) + ',{quality:"high",camera:[18,11,21],target:[0,2,2]})')
  const reflection = await p.evaluate(`(async()=>{
    const {reflection}=window.renderHarness, {camera,group}=window;
    const initial=reflection.captureCount;window.draw();window.draw();const stable=reflection.captureCount;
    reflection.invalidate();await new Promise(r=>setTimeout(r,40));window.draw();const invalidated=reflection.captureCount;
    camera.position.x+=1;camera.lookAt(0,2,2);reflection.update(camera,true);const moved=reflection.captureCount;
    camera.lookAt(0,10,80);reflection.update(camera);const offscreen={active:reflection.active,visible:reflection.hasVisibleSurface(camera),captures:reflection.captureCount};
    camera.lookAt(0,2,2);group.visible=false;reflection.update(camera);const hidden={active:reflection.active,visible:reflection.hasVisibleSurface(camera)};group.visible=true;
    return {initial,stable,invalidated,moved,offscreen,hidden};
  })()`)
  assert.equal(reflection.stable, reflection.initial)
  assert.equal(reflection.invalidated, reflection.initial + 1)
  assert.equal(reflection.moved, reflection.invalidated + 1)
  assert.deepEqual(reflection.offscreen, { active: false, visible: false, captures: reflection.moved })
  assert.deepEqual(reflection.hidden, { active: false, visible: false })
  const fixtures = await p.evaluate(`(async()=>{
    const {FixtureLightingRuntime}=await import('/src/renderer/fixtureLightingRuntime.ts');const T=window.THREE,renderer=window.renderer;
    const scene=new T.Scene(),root=new T.Group();scene.add(root);
    const eye=new T.PerspectiveCamera(45,1,.05,100);eye.position.set(0,3,8);eye.lookAt(0,1,0);eye.updateMatrixWorld();
    const light=new T.PointLight(0xffffff,20,6);light.position.set(1,2,0);light.userData.fixtureLight=true;root.add(light);
    const remote=new T.PointLight(0xffffff,30,2);remote.position.set(0,0,40);remote.userData.fixtureLight=true;root.add(remote);
    const geometry=new T.BoxGeometry(2,2,2),material=new T.MeshStandardMaterial();const wall=new T.Mesh(geometry,material);wall.castShadow=true;root.add(wall);
    const runtime=new FixtureLightingRuntime();runtime.setRoot(root);
    const initial=runtime.update(eye,'high');renderer.shadowMap.needsUpdate=initial;renderer.render(scene,eye);const map=light.shadow.map;
    const stable=runtime.update(eye,'high');const remoteCulled=!remote.visible;
    runtime.setRoot(root);const geometryDirty=runtime.update(eye,'high');const mapRetained=map===light.shadow.map;renderer.shadowMap.needsUpdate=true;renderer.render(scene,eye);
    light.position.x+=.5;const moved=runtime.update(eye,'high');renderer.shadowMap.needsUpdate=moved;renderer.render(scene,eye);
    runtime.invalidateShadows();const invalidated=runtime.update(eye,'high');
    runtime.dispose();geometry.dispose();material.dispose();return {initial,stable,remoteCulled,geometryDirty,mapRetained,moved,invalidated,released:light.shadow.map===null};
  })()`)
  assert.deepEqual(fixtures, { initial: true, stable: false, remoteCulled: true, geometryDirty: true, mapRetained: true, moved: true, invalidated: true, released: true })
  assert.deepEqual(p.errors, [])
  const result = { status: 'PASS', shadowFits: fits, reflection, fixtures, shaderErrors: p.errors }
  await writeFile(output + '/缓存与阴影范围回归.json', JSON.stringify(result, null, 2))
  console.log(JSON.stringify({ status: result.status, shadowFits: fits.length, reflection, fixtures }))
} finally { await browser.close() }
