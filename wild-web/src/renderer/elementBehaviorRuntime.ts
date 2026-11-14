import * as THREE from 'three'
import type { ExtensionElementBehavior } from 'wild-core/types'
import { getExtensionBehaviorCapabilities, validateElementBehavior } from 'wild-core/compiler'
import { createVideoBehavior } from './videoBehavior'

export interface ElementBehaviorInstance {
  label: string
  interact: () => void
  tick?: (delta: number) => boolean
  dispose: () => void
}

export interface ElementBehaviorContext {
  requestRender: () => void
}

type Factory = (mesh: THREE.Mesh, behavior: ExtensionElementBehavior, context: ElementBehaviorContext) => ElementBehaviorInstance
const factories = new Map<string, Factory>()
const instances = new WeakMap<THREE.Object3D, ElementBehaviorInstance>()
const roots = new WeakMap<THREE.Object3D, Array<{ mesh: THREE.Mesh; instance: ElementBehaviorInstance }>>()
let invalidate: () => void = () => {}

/** 新能力注册处理器；渲染器主流程不按物品名称分支。 */
export function registerElementBehaviorRuntime(capability: string, factory: Factory): void {
  if (!getExtensionBehaviorCapabilities().some(item => item.name === capability) || factories.has(capability)) {
    throw new Error(`行为运行时未声明能力或重复注册: ${capability}`)
  }
  factories.set(capability, factory)
}

export function configureElementBehaviorRendering(requestRender: () => void): void {
  invalidate = requestRender
}

/** 在场景增量更新时同步，逐帧只访问实际具有扩展行为的网格。 */
export function syncElementBehaviorRuntimes(root: THREE.Object3D): void {
  const active: Array<{ mesh: THREE.Mesh; instance: ElementBehaviorInstance }> = []
  root.traverse(mesh => {
    if (!(mesh instanceof THREE.Mesh) || mesh.userData.interaction?.kind !== 'extension') return
    let instance = instances.get(mesh)
    if (!instance) {
      const behavior = mesh.userData.interaction as ExtensionElementBehavior
      validateElementBehavior(behavior)
      const factory = factories.get(behavior.capability)
      if (!factory) throw new Error(`未加载行为运行时: ${behavior.capability}`)
      instance = factory(mesh, behavior, { requestRender: () => invalidate() })
      instances.set(mesh, instance)
    }
    active.push({ mesh, instance })
  })
  roots.set(root, active)
}

export function interactElementBehavior(mesh: THREE.Object3D): boolean {
  const instance = instances.get(mesh)
  if (!instance) return false
  instance.interact()
  invalidate()
  return true
}

export function elementBehaviorLabel(mesh: THREE.Object3D): string {
  return instances.get(mesh)?.label || ''
}

export function tickElementBehaviors(root: THREE.Object3D | null, delta: number): boolean {
  let active = false
  for (const entry of root ? roots.get(root) || [] : []) {
    if (instances.get(entry.mesh) === entry.instance) active = (entry.instance.tick?.(delta) || false) || active
  }
  return active
}

export function disposeElementBehavior(mesh: THREE.Object3D): void {
  roots.delete(mesh)
  const instance = instances.get(mesh)
  instances.delete(mesh)
  instance?.dispose()
}

registerElementBehaviorRuntime('video', createVideoBehavior)
