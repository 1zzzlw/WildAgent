import * as THREE from 'three'
import type { ReconstructedEntity } from '../types/scene'
import { MaterialCache } from './materialAdapter'
import { clearSceneObjectResources, updateSceneGroup } from './renderEntity'
import type { BlueprintPresentation } from 'wild-core/types'
import { BlueprintPresentationRuntime } from './blueprintPresentationRuntime'

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
  readonly presentation: BlueprintPresentationRuntime
  private disposed = false

  constructor(
    instanceId: string,
    transform: BlueprintInstanceTransform = {},
  ) {
    if (!instanceId.trim()) throw new Error('Blueprint render instance id cannot be empty')
    this.instanceId = instanceId
    this.root = new THREE.Group()
    this.presentation = new BlueprintPresentationRuntime(this.root)
    this.root.name = `WildBlueprint:${instanceId}`
    this.root.userData.blueprintInstanceId = instanceId
    this.materialScope = new MaterialCache(`blueprint:${instanceId}`)
    this.setTransform(transform)
  }

  update(entity: ReconstructedEntity, presentation?: BlueprintPresentation): void {
    this.assertActive()
    this.presentation.reset()
    updateSceneGroup(this.root, entity, this.materialScope)
    this.root.userData.boundingBox = entity.boundingBox
    this.presentation.setStyle(presentation?.style)
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
    this.presentation.reset()
    clearSceneObjectResources(this.root)
    this.materialScope.clear()
    this.root.removeFromParent()
    this.disposed = true
  }

  private assertActive(): void {
    if (this.disposed) throw new Error(`Blueprint render instance is disposed: ${this.instanceId}`)
  }
}
