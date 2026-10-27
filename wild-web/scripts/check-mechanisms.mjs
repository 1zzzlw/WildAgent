import assert from 'node:assert/strict'
import { mkdir, writeFile } from 'node:fs/promises'
import { createServer } from 'vite'
import * as THREE from 'three'
import { Capsule } from 'three/examples/jsm/math/Capsule.js'

const vite = await createServer({ server: { middlewareMode: true }, appType: 'custom', logLevel: 'error' })
const results = []
try {
  const { compileBlueprintComponents } = await vite.ssrLoadModule('../wild-core/src/compiler/index.ts')
  const { reconstructEntity } = await vite.ssrLoadModule('../wild-core/src/primitive/index.ts')
  const { validateBlueprintSchema } = await vite.ssrLoadModule('../wild-core/src/primitive/schema-validator.ts')
  const { createSceneGroupFromEntity, updateSceneGroup, clearSceneObjectResources } = await vite.ssrLoadModule('/src/renderer/renderEntity.ts')
  const { tickMechanisms, interactMechanism } = await vite.ssrLoadModule('/src/renderer/mechanismRuntime.ts')
  const { MaterialCache } = await vite.ssrLoadModule('/src/renderer/materialAdapter.ts')
  const { RoamingCollisionWorld } = await vite.ssrLoadModule('/src/extensions/characterRoaming/RoamingCollisionWorld.ts')
  const build = async bp => {
    const compiled = compileBlueprintComponents(bp)
    assert.deepEqual(compiled.diagnostics, [])
    const entity = await reconstructEntity(compiled.blueprint)
    assert.deepEqual(entity.diagnostics.filter(d => d.level === 'error'), [])
    // 数值测试不创建 Canvas 字体；真实标签与点击另由 Chromium 验证。
    for (const mesh of entity.meshes) delete mesh.label
    return entity
  }
  for (const [floorCount, initialFloor] of [[1, 0], [3, 0], [3, 2], [5, 1]]) {
    const floorHeight = 3.2, y = 0.4 + initialFloor * floorHeight
    const elevator = { type: 'elevator', id: 'lift_with_underscores', position: [2, y, -1], dimensions: { width: 1.8, depth: 1.8, height: 2.5 }, floorHeight, floorCount, initialFloor }
    const bp = { meta: { version: '1.1', type: 'building', name: 'mechanisms' }, geometry: { elements: [], components: [elevator] }, materials: {} }
    assert.deepEqual(validateBlueprintSchema(bp), [])
    const cache = new MaterialCache(), group = createSceneGroupFromEntity(await build(bp), cache)
    const get = suffix => group.getObjectByName(elevator.id + '__' + suffix)
    const cab = get('cab'), hall = get('hall_' + initialFloor)
    assert.ok(interactMechanism(hall, () => {})); for (let i = 0; i < 20; i++) tickMechanisms(group, .05)
    assert.equal(cab.userData.elevatorDoorProgress, 0) // 地板不是门
    assert.equal(get('cab_door_1').userData.elevatorDoorProgress, 1)
    assert.equal(interactMechanism(cab, () => {}), false)
    const world = new RoamingCollisionWorld(group, -10)
    const rider = new Capsule(new THREE.Vector3(2, y + .242, -1), new THREE.Vector3(2, y + 1.5, -1), .24)
    const step = () => {
      tickMechanisms(group, .05); world.carryPlatform(rider); world.syncMoving()
      const support = world.floorHeight(new THREE.Vector3(2, rider.start.y - rider.radius + .08, -1), .2)
      assert.ok(support !== null && Math.abs(support - (cab.position.y + .05)) < 1e-6, '活动地板每帧都有真实碰撞支撑面')
    }
    const target = (initialFloor + 1) % floorCount
    assert.ok(interactMechanism(get('car_button_' + target), () => {}))
    if (floorCount > 1) {
      for (let i = 0; i < 70; i++) step()
      assert.equal(cab.userData.elevatorPhase, 'moving')
      assert.ok(get('cab_door_1').userData.elevatorDoorProgress === 0)
      assert.ok(interactMechanism(get('car_button_' + (floorCount + 0)), () => {})) // 行驶中开门无效
      assert.equal(cab.userData.elevatorPhase, 'moving')
      updateSceneGroup(group, await build(bp), cache)
      assert.equal(get('cab'), cab, '增量重建保留当前设备')
      assert.equal(cab.userData.elevatorPhase, 'moving')
    }
    for (let i = 0; i < 250; i++) step()
    assert.equal(cab.userData.elevatorFloor, target)
    assert.ok(Math.abs(cab.position.y - (.35 + target * floorHeight)) < 1e-7)
    assert.ok(Math.abs(rider.start.y - rider.radius - (.402 + target * floorHeight)) < 1e-7, '上下行乘客跟随地板')
    assert.equal(get('cab_door_1').userData.elevatorDoorProgress, 1)
    if (floorCount > 1) {
      interactMechanism(get('hall_' + initialFloor), () => {})
      for (let i = 0; i < 300; i++) step()
      assert.equal(cab.userData.elevatorFloor, initialFloor)
      assert.ok(Math.abs(rider.start.y - rider.radius - (y + .002)) < 1e-7)
    }
    world.dispose(); clearSceneObjectResources(group)
    results.push({ floorCount, initialFloor, target, passengerRoundTrip: true })
  }
  const bp = { meta: { version: '1.1', type: 'asset', name: 'fans' }, geometry: { elements: [], components: [0, 1].map(i => ({ type: 'fan', id: 'fan' + i, position: [i * 3, 2.6, 0], controlPosition: [i * 3, 1.1, 1], radius: .65 })) }, materials: {} }
  const group = createSceneGroupFromEntity(await build(bp)), switch0 = group.getObjectByName('fan0__control'), blade = group.getObjectByName('fan0__blade_0')
  const initial = blade.position.clone()
  assert.equal(tickMechanisms(group, .05), false)
  interactMechanism(switch0, () => {})
  for (let i = 0; i < 40; i++) tickMechanisms(group, .05)
  assert.ok(blade.position.distanceTo(initial) > .1)
  assert.equal(group.getObjectByName('fan1__hub').userData.rotorLevel, 0)
  const low = blade.userData.rotorSpeed
  interactMechanism(switch0, () => {}); for (let i = 0; i < 40; i++) tickMechanisms(group, .05)
  assert.ok(blade.userData.rotorSpeed > low * 1.8)
  interactMechanism(switch0, () => {}); for (let i = 0; i < 150; i++) tickMechanisms(group, .05)
  assert.equal(tickMechanisms(group, .05), false, '关闭后惯性停止并允许渲染休眠')
  clearSceneObjectResources(group)
  const queueBp = { meta: { version: '1.1', type: 'asset', name: 'queue' }, geometry: { elements: [], components: [{ type: 'elevator', id: 'queued', position: [0, 0, 0], dimensions: { width: 1.8, depth: 1.8, height: 2.5 }, floorHeight: 3.2, floorCount: 3 }] }, materials: {} }
  const queueRoot = createSceneGroupFromEntity(await build(queueBp)), queuedCab = queueRoot.getObjectByName('queued__cab')
  interactMechanism(queueRoot.getObjectByName('queued__car_button_2'), () => {})
  for(let i=0;i<40;i++)tickMechanisms(queueRoot,.05)
  assert.equal(queuedCab.userData.elevatorPhase,'moving')
  interactMechanism(queueRoot.getObjectByName('queued__hall_1'), () => {})
  interactMechanism(queueRoot.getObjectByName('queued__hall_1'), () => {})
  const stops=[]
  for(let i=0;i<500;i++){tickMechanisms(queueRoot,.05);if(queuedCab.userData.elevatorPhase==='opening'&&stops.at(-1)!==queuedCab.userData.elevatorFloor)stops.push(queuedCab.userData.elevatorFloor)}
  assert.deepEqual(stops,[2,1],'途中请求不能跳过当前目的地；重复呼梯只排队一次')
  assert.equal(queuedCab.userData.elevatorFloor,1)
  clearSceneObjectResources(queueRoot)
  const result = { status: 'PASS', elevators: results, queueStops:stops, fan: { independentControls: true, lowHighOff: true, idleSleeps: true } }
  await mkdir('../docs/10月27日/验证', { recursive: true }); await writeFile('../docs/10月27日/验证/动态组件回归.json', JSON.stringify(result, null, 2))
  console.log(JSON.stringify(result, null, 2))
} finally { await vite.close() }
