import * as THREE from 'three'
import type { ReconstructedEntity } from '../types/scene'
import { MaterialCache } from './materialAdapter'
import { updateSceneGroup } from './renderEntity'

export interface BlueprintInstanceTransform {
  position?: [number, number, number]
  rotation?: [number, number, number]
  scale?: [number, number, number]
}

/**
 * 一份蓝图的渲染边界：几何根节点和可变状态隔离，材质资源通过全局注册表共享。
 */
export class BlueprintRenderInstance {
  readonly root: THREE.Group
  readonly materialScope: MaterialCache
  readonly instanceId: string
  private disposed = false

  constructor(
    instanceId: string,
    transform: BlueprintInstanceTransform = {},
  ) {
    if (!instanceId.trim()) throw new Error('Blueprint render instance id cannot be empty')
    this.instanceId = instanceId
    this.root = new THREE.Group()
    this.root.name = `WildBlueprint:${instanceId}`
    this.root.userData.blueprintInstanceId = instanceId
    this.materialScope = new MaterialCache(`blueprint:${instanceId}`)
    this.setTransform(transform)
  }

  update(entity: ReconstructedEntity): void {
    this.assertActive()
    updateSceneGroup(this.root, entity, this.materialScope)
    this.root.userData.boundingBox = entity.boundingBox
  }

  setTransform(transform: BlueprintInstanceTransform): void {
    this.assertActive()
    this.root.position.fromArray(transform.position || [0, 0, 0])
    this.root.rotation.fromArray(transform.rotation || [0, 0, 0])
    this.root.scale.fromArray(transform.scale || [1, 1, 1])
    this.root.updateMatrixWorld(true)
  }

  dispose(): void {
    if (this.disposed) return
    disposeGeometryTree(this.root)
    this.materialScope.clear()
    this.root.removeFromParent()
    this.disposed = true
  }

  private assertActive(): void {
    if (this.disposed) throw new Error(`Blueprint render instance is disposed: ${this.instanceId}`)
  }
}

function disposeGeometryTree(root: THREE.Object3D): void {
  const geometries = new Set<THREE.BufferGeometry>()
  root.traverse(object => {
    if (object instanceof THREE.Mesh || object instanceof THREE.InstancedMesh) {
      geometries.add(object.geometry)
      if (object.userData.ownsMaterial) {
        const materials = Array.isArray(object.material) ? object.material : [object.material]
        materials.forEach(material => material.dispose())
      }
    }
  })
  geometries.forEach(geometry => geometry.dispose())
  root.clear()
}
