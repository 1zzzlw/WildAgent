import * as THREE from 'three'
import { compileBlueprintComponents } from 'wild-core/compiler'
import { reconstructEntity } from 'wild-core/primitive'
import type { Blueprint } from '../types/blueprint'
import type { BlockPlacementDraft } from '../wild/blockPlacement'
import { meshDataToGeometry } from './meshDataToGeometry'

/** 保留宿主推导上下文，只显示待放置构件；移动预览只更新变换。 */
export class BlockPlacementPreview {
  readonly root = new THREE.Group()
  private material = new THREE.MeshBasicMaterial({ color: 0x35d7ff, transparent: true, opacity: 0.5, depthWrite: false, depthTest: false, side: THREE.DoubleSide })
  private key = ''
  private generation = 0
  private origin = new THREE.Vector3()
  private changed: () => void

  constructor(scene: THREE.Scene, changed: () => void) {
    this.changed = changed
    this.root.name = 'BlockPlacementPreview'
    this.root.visible = false
    scene.add(this.root)
  }

  async update(blueprint: Blueprint, draft: BlockPlacementDraft, displayRoot: THREE.Group): Promise<void> {
    const item = draft.operation.op === 'add_element' ? draft.operation.element : draft.operation.component
    const key = `${item.id}:${draft.hostId || ''}`
    if (key !== this.key) {
      this.clear()
      this.key = key
      this.origin.fromArray(draft.anchor)
      const generation = this.generation
      const host = blueprint.geometry.elements.find(element => element.id === draft.hostId)
      // 兼容未显式定位的旧屋顶；墙转角和屋面收边也依赖周边墙体。
      const needsWalls = host?.type === 'wall' || host?.type === 'roof' || item.type === 'wall' || item.type === 'roof'
      const context = blueprint.geometry.elements.filter(element => element.id === host?.id || (needsWalls && element.type === 'wall'))
      const source = {
        ...blueprint,
        geometry: {
          elements: [...context, ...(draft.operation.op === 'add_element' ? [item] : [])],
          components: draft.operation.op === 'add_component' ? [item] : [],
        },
      }
      const compiled = compileBlueprintComponents(source as any)
      const errors = compiled.diagnostics.filter(diagnostic => diagnostic.level === 'error')
      if (errors.length) throw new Error(errors[0]!.message)
      const entity = await reconstructEntity(compiled.blueprint)
      if (generation !== this.generation) return
      const ids = new Set(compiled.mapping.generatedElementIdsByComponentId[item.id] || [item.id])
      for (const data of entity.meshes) {
        if (!data.elementId || !ids.has(data.elementId)) continue
        const mesh = new THREE.Mesh(meshDataToGeometry(data), this.material)
        mesh.position.fromArray(data.transform.position)
        mesh.rotation.set(...data.transform.rotation)
        mesh.scale.fromArray(data.transform.scale)
        mesh.renderOrder = 1000
        this.root.add(mesh)
      }
      const failure = entity.diagnostics.find(diagnostic => diagnostic.level === 'error')
      if (failure || !this.root.children.length) {
        this.clear()
        throw new Error(failure?.message || '该位置无法生成构件预览')
      }
    }
    this.root.position.copy(displayRoot.position).add(new THREE.Vector3(...draft.anchor).sub(this.origin))
    this.root.visible = this.root.children.length > 0
    this.changed()
  }

  hide() {
    this.clear()
  }

  clear() {
    this.generation++
    this.key = ''
    this.root.traverse(object => { if (object instanceof THREE.Mesh) object.geometry.dispose() })
    this.root.clear()
    this.root.visible = false
    this.changed()
  }

  dispose() {
    this.clear()
    this.root.removeFromParent()
    this.material.dispose()
  }
}
