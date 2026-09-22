import type { ComponentSpec, MaterialDef } from '../wild-core/types'

export const COMPONENT_MATERIAL = {
  frame: '__wild_component_frame',
  glass: '__wild_component_glass',
  wood: '__wild_component_wood',
  concrete: '__wild_component_concrete',
  metal: '__wild_component_metal',
  bulbGlass: '__wild_component_bulb_glass',
  bulbEmitter: '__wild_component_bulb_emitter',
  lampShade: '__wild_component_lamp_shade',
} as const

const BUILTIN_MATERIALS: Record<string, MaterialDef> = {
  [COMPONENT_MATERIAL.frame]: standard([0.08, 0.1, 0.13], 0.32, 0.72),
  [COMPONENT_MATERIAL.glass]: glass([0.78, 0.9, 1], 0.06, 0.92, 0.012),
  [COMPONENT_MATERIAL.wood]: standard([0.34, 0.16, 0.07], 0.56, 0),
  [COMPONENT_MATERIAL.concrete]: standard([0.54, 0.56, 0.59], 0.72, 0),
  [COMPONENT_MATERIAL.metal]: standard([0.1, 0.12, 0.15], 0.3, 0.78),
  [COMPONENT_MATERIAL.bulbGlass]: glass([1, 0.88, 0.68], 0.08, 0.86, 0.008),
  [COMPONENT_MATERIAL.bulbEmitter]: {
    ...standard([1, 0.72, 0.36], 0.18, 0),
    emissive: [1, 0.62, 0.24],
    emissiveIntensity: 3.5,
  },
  [COMPONENT_MATERIAL.lampShade]: {
    ...standard([0.84, 0.72, 0.56], 0.72, 0),
    materialClass: 'fabric',
    side: 'double',
    sheen: 0.25,
    sheenColor: [1, 0.9, 0.76],
  },
}

/** 为没有显式材质的组合构件补充共享语义材质；用户/AI 指定的材质始终优先。 */
export function applyComponentMaterialDefaults(
  components: ComponentSpec[],
  materials: Record<string, MaterialDef>,
): void {
  const required = new Set<string>()
  const fallback = <T extends ComponentSpec, K extends keyof T>(
    component: T,
    field: K,
    material: string,
  ) => {
    if (!component[field]) {
      component[field] = material as T[K]
      required.add(material)
    }
  }

  for (const component of components) {
    switch (component.type) {
      case 'door':
        fallback(component, 'frameMaterial', COMPONENT_MATERIAL.frame)
        fallback(component, 'leafMaterial', COMPONENT_MATERIAL.wood)
        break
      case 'window':
      case 'bay_window':
        fallback(component, 'frameMaterial', COMPONENT_MATERIAL.frame)
        fallback(component, 'glassMaterial', COMPONENT_MATERIAL.glass)
        break
      case 'railing':
        fallback(component, 'material', COMPONENT_MATERIAL.metal)
        break
      case 'canopy':
        fallback(component, 'material', COMPONENT_MATERIAL.concrete)
        fallback(component, 'supportMaterial', COMPONENT_MATERIAL.metal)
        break
      case 'balcony':
      case 'ramp':
        fallback(component, 'material', COMPONENT_MATERIAL.concrete)
        fallback(component, 'railingMaterial', COMPONENT_MATERIAL.metal)
        break
      case 'cornice':
        fallback(component, 'material', COMPONENT_MATERIAL.concrete)
        break
      case 'chimney':
        fallback(component, 'material', COMPONENT_MATERIAL.concrete)
        fallback(component, 'capMaterial', COMPONENT_MATERIAL.metal)
        break
      case 'light':
        fallback(component, 'material', COMPONENT_MATERIAL.bulbGlass)
        fallback(component, 'baseMaterial', COMPONENT_MATERIAL.metal)
        fallback(component, 'shadeMaterial', COMPONENT_MATERIAL.lampShade)
        required.add(COMPONENT_MATERIAL.bulbEmitter)
        break
    }
  }

  for (const id of required) {
    if (!materials[id]) materials[id] = clone(BUILTIN_MATERIALS[id])
  }
}

function standard(baseColor: MaterialDef['baseColor'], roughness: number, metallic: number): MaterialDef {
  return { baseColor, roughness, metallic, albedo: 1, lightingCondition: 'D65_noon' }
}

function glass(
  baseColor: MaterialDef['baseColor'],
  roughness: number,
  transmission: number,
  thickness: number,
): MaterialDef {
  return {
    ...standard(baseColor, roughness, 0),
    materialClass: 'glass',
    side: 'double',
    transmission,
    ior: 1.5,
    thickness,
    attenuationColor: baseColor,
    attenuationDistance: 3,
  }
}

function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T
}
