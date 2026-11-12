import assert from 'node:assert/strict'
import * as THREE from 'three'
import { Capsule } from 'three/examples/jsm/math/Capsule.js'
import { createServer } from 'vite'

const vite = await createServer({ server: { middlewareMode: true }, appType: 'custom', logLevel: 'error' })
try {
  const { CharacterRoamingRuntime } = await vite.ssrLoadModule('/src/extensions/characterRoaming/CharacterRoamingRuntime.ts')
  const { RoamingCollisionWorld } = await vite.ssrLoadModule('/src/extensions/characterRoaming/RoamingCollisionWorld.ts')
  const { buildStair } = await vite.ssrLoadModule('../wild-core/src/primitive/geometry/stair.ts')
  const material = new THREE.MeshBasicMaterial()
  const box = (root, size, position) => {
    const mesh = new THREE.Mesh(new THREE.BoxGeometry(...size), material)
    mesh.position.fromArray(position)
    mesh.userData.materialRef = 'default'
    root.add(mesh)
  }
  const stairs = () => {
    const root = new THREE.Group()
    for (const data of buildStair({ from: [0, 0, 0], to: [0, 2.16, -3.36], stepCount: 12, stepHeight: .18, stepDepth: .28, width: 1.5 })) {
      const geometry = new THREE.BufferGeometry()
      geometry.setAttribute('position', new THREE.BufferAttribute(data.geometry, 3))
      geometry.setIndex(new THREE.BufferAttribute(data.indices, 1))
      const mesh = new THREE.Mesh(geometry, material)
      mesh.position.fromArray(data.transform.position)
      mesh.rotation.fromArray(data.transform.rotation)
      mesh.userData.materialRef = 'default'
      root.add(mesh)
    }
    box(root, [1.5, .2, 4], [0, 2.06, -5.36])
    return root
  }
  // 绕过 DOM/贴图初始化，保留真实移动、胶囊碰撞、相机与 tick；不模拟人工键鼠体验。
  const runtime = (root, feet = [0, .002, .8]) => {
    const rider = Object.create(CharacterRoamingRuntime.prototype)
    Object.assign(rider, {
      options: { camera: new THREE.PerspectiveCamera(), onTargetChange() {} },
      world: new RoamingCollisionWorld(root, 0),
      body: new Capsule(new THREE.Vector3(feet[0], feet[1] + .24, feet[2]), new THREE.Vector3(feet[0], feet[1] + 1.51, feet[2]), .24),
      robot: { root: new THREE.Group(), update() {} },
      velocity: new THREE.Vector3(), keys: new Set(), eye: new THREE.Vector3(), direction: new THREE.Vector3(),
      orientation: new THREE.Euler(0, 0, 0, 'YXZ'), raycaster: new THREE.Raycaster(),
      yaw: 0, pitch: 0, cameraStepOffset: 0, grounded: true, jumpQueued: false, flying: false, view: 'first',
      targetClock: 0, targetLabel: '', disposed: false,
    })
    Object.defineProperty(rider, 'locked', { get: () => true })
    rider.syncAvatar(0)
    rider.updateCamera()
    return rider
  }
  const results = []
  for (const [fps, yaw, view] of [[30, 0, 'first'], [60, 0, 'first'], [120, 0, 'first'], [60, Math.PI / 4, 'third']]) {
    const root = stairs()
    root.rotation.y = yaw
    const rider = runtime(root, [.8 * Math.sin(yaw), .002, .8 * Math.cos(yaw)])
    rider.yaw = yaw
    rider.view = view
    rider.updateCamera()
    const axis = new THREE.Vector3(Math.sin(yaw), 0, Math.cos(yaw))
    rider.keys.add('KeyW')
    let minSpeed = Infinity, maxDrop = 0, maxCameraStep = 0
    for (let frame = 0; frame < fps * 2.5; frame++) {
      const before = rider.body.start.clone(), cameraY = rider.options.camera.position.y
      rider.tick(1 / fps)
      const beforeZ = before.dot(axis)
      if (beforeZ < .3 && beforeZ > -3.4) {
        minSpeed = Math.min(minSpeed, (beforeZ - rider.body.start.dot(axis)) * fps)
        maxDrop = Math.max(maxDrop, before.y - rider.body.start.y)
        maxCameraStep = Math.max(maxCameraStep, Math.abs(rider.options.camera.position.y - cameraY))
      }
    }
    const result = { fps, yaw, view, z: rider.body.start.dot(axis), feet: rider.body.start.y - .24, minSpeed, maxDrop, maxCameraStep }
    results.push(result)
    rider.world.dispose()
    root.traverse(object => object.geometry?.dispose())
  }
  console.log(JSON.stringify(results, null, 2))
  assert.ok(results.every(result => result.z < -4), '人物应能连续走完 12 级标准楼梯')
  assert.ok(results.every(result => result.minSpeed > 2.9), '踏步边缘不能反复削掉水平速度')
  assert.ok(results.every(result => result.maxDrop < .001), '上楼时不能被贴地检测拉回下一层踏步')
  assert.ok(results.every(result => result.maxCameraStep * result.fps < 3), '镜头应平滑跟随台阶高度变化')
  const guards = []
  for (const [name, height, pass] of [['wall', 3, false], ['high-step', .4, false], ['max-step', .32, true]]) {
    const root = new THREE.Group()
    box(root, [2, height, 1], [0, height / 2, -.5])
    const rider = runtime(root)
    rider.keys.add('KeyW')
    let peak = 0
    for (let i = 0; i < 120; i++) {
      rider.tick(1 / 60)
      peak = Math.max(peak, rider.body.start.y - .24)
    }
    guards.push({ name, z: rider.body.start.z, peak })
    if (pass) assert.ok(rider.body.start.z < -2 && peak >= height - .001, '应能迈上 0.32 米以内的踏步')
    else assert.ok(rider.body.start.z > 0, `${name}: 不能走上超过迈步上限的障碍`)
    rider.world.dispose()
    root.traverse(object => object.geometry?.dispose())
  }
  {
    const root = stairs()
    box(root, [2, .2, 1], [0, 1.95, -.5])
    const rider = runtime(root)
    rider.keys.add('KeyW')
    for (let i = 0; i < 120; i++) rider.tick(1 / 60)
    guards.push({ name: 'low-ceiling', z: rider.body.start.z, feet: rider.body.start.y - .24 })
    assert.ok(rider.body.start.z > -.1, '低顶棚下不能穿过头部空间不足的踏步')
    assert.ok(rider.options.camera.position.y < rider.body.end.y + .24, '镜头应保持在碰撞体高度内')
    rider.world.dispose()
    root.traverse(object => object.geometry?.dispose())
  }
  {
    const root = new THREE.Group(), rider = runtime(root)
    rider.jumpQueued = true
    let height = 0
    for (let i = 0; i < 90; i++) {
      rider.tick(1 / 60)
      height = Math.max(height, rider.body.start.y - .24)
    }
    guards.push({ name: 'jump', height })
    assert.ok(height > .9 && height < 1.05, '跳跃仍使用原有起跳速度与重力')
    assert.ok(rider.grounded && rider.body.start.y - .24 < .01, '跳跃后正常落地')
    rider.world.dispose()
  }
  {
    const root = stairs(), rider = runtime(root, [0, 2.162, -4])
    rider.yaw = Math.PI
    rider.keys.add('KeyW')
    for (let i = 0; i < 150; i++) rider.tick(1 / 60)
    guards.push({ name: 'downstairs', z: rider.body.start.z, feet: rider.body.start.y - .24 })
    assert.ok(rider.body.start.z > 2 && rider.body.start.y - .24 < .01, '连续下楼后正常到达地面')
    rider.world.dispose()
    root.traverse(object => object.geometry?.dispose())
  }
  material.dispose()
  console.log(JSON.stringify({ status: 'PASS', guards }, null, 2))
} finally {
  await vite.close()
}
