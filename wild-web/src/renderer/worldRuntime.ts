import * as THREE from 'three'
import type { ReconstructedEntity } from '../types/scene'
import type {
  WorldBlueprintInstance,
  WorldDocument,
  WorldTheme,
} from '../wild-core/src/world'
import { validateWorldDocument } from '../wild-core/src/world'
import { BlueprintRenderInstance } from './blueprintRenderInstance'

export interface WorldRuntimeStats {
  instances: number
  loadedChunks: number
  visibleInstances: number
}

/** 多蓝图几何隔离边界；材质继续通过 BlueprintRenderInstance 的全局缓存共享。 */
export class WorldRuntime {
  readonly root = new THREE.Group()
  readonly worldId: string
  private instances = new Map<string, BlueprintRenderInstance>()
  private definitions = new Map<string, WorldBlueprintInstance>()
  private loadedChunks = new Set<string>()
  private theme: WorldTheme | undefined

  constructor(worldId: string) {
    if (!worldId.trim()) throw new Error('World runtime id cannot be empty')
    this.worldId = worldId
    this.root.name = `WildWorld:${worldId}`
    this.root.userData.worldId = worldId
  }

  mountDocument(document: WorldDocument): void {
    const issues = validateWorldDocument(document)
    if (issues.length) throw new Error(`Invalid world document: ${issues.join('; ')}`)
    if (document.worldId !== this.worldId) throw new Error('World document id does not match runtime')
    this.disposeInstances()
    this.definitions = new Map(document.instances.map(instance => [instance.instanceId, instance]))
    this.loadedChunks = new Set(document.chunks.map(chunk => chunk.chunkId))
    this.theme = document.theme
  }

  ensureInstance(definition: WorldBlueprintInstance): BlueprintRenderInstance {
    const existing = this.instances.get(definition.instanceId)
    if (existing) {
      existing.setTransform(definition.transform)
      existing.root.visible = definition.visible !== false && this.loadedChunks.has(definition.chunkId)
      this.definitions.set(definition.instanceId, definition)
      return existing
    }
    const instance = new BlueprintRenderInstance(definition.instanceId, definition.transform)
    instance.root.visible = definition.visible !== false && this.loadedChunks.has(definition.chunkId)
    instance.root.userData.chunkId = definition.chunkId
    instance.root.userData.blueprintId = definition.blueprintId
    this.instances.set(definition.instanceId, instance)
    this.definitions.set(definition.instanceId, definition)
    this.root.add(instance.root)
    return instance
  }

  updateInstance(instanceId: string, entity: ReconstructedEntity): void {
    const instance = this.instances.get(instanceId)
    if (!instance) throw new Error(`World instance is not mounted: ${instanceId}`)
    instance.update(entity)
  }

  unloadChunk(chunkId: string): number {
    this.loadedChunks.delete(chunkId)
    let released = 0
    for (const [instanceId, definition] of this.definitions) {
      if (definition.chunkId !== chunkId) continue
      const instance = this.instances.get(instanceId)
      if (!instance) continue
      instance.dispose()
      this.instances.delete(instanceId)
      released++
    }
    return released
  }

  loadChunk(chunkId: string): void {
    this.loadedChunks.add(chunkId)
  }

  removeInstance(instanceId: string): boolean {
    this.definitions.delete(instanceId)
    const instance = this.instances.get(instanceId)
    if (!instance) return false
    instance.dispose()
    this.instances.delete(instanceId)
    return true
  }

  setTheme(theme: WorldTheme | undefined): void {
    this.theme = theme
  }

  resolveMaterialSlot(slot: string, fallback: string): string {
    return this.theme?.materialSlots[slot] || fallback
  }

  getInstance(instanceId: string): BlueprintRenderInstance | undefined {
    return this.instances.get(instanceId)
  }

  getStats(): WorldRuntimeStats {
    return {
      instances: this.instances.size,
      loadedChunks: this.loadedChunks.size,
      visibleInstances: [...this.instances.values()].filter(instance => instance.root.visible).length,
    }
  }

  dispose(): void {
    this.disposeInstances()
    this.root.removeFromParent()
  }

  private disposeInstances(): void {
    this.instances.forEach(instance => instance.dispose())
    this.instances.clear()
    this.root.clear()
  }
}
