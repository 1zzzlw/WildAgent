import type { MaterialDef } from '../types/blueprint'

const base: Pick<MaterialDef, 'metallic' | 'albedo' | 'lightingCondition'> = {
  metallic: 0, albedo: 1, lightingCondition: 'D65_noon',
}

/** These presets persist only numeric parameters; no image or model payload. */
export const SURFACE_MATERIAL_PRESETS: Array<{ id: string; name: string; description: string; material: MaterialDef }> = [
  { id: 'quartz_ivory', name: '暖白石英石', description: '细密晶粒、柔和浅色、轻微抛光反射', material: {
    ...base, baseColor: [0.88, 0.86, 0.8], roughness: 0.22, surfaceFamily: 'mineral', surfacePattern: 'quartz',
    materialClass: 'clearcoat', clearcoat: 0.22, clearcoatRoughness: 0.18,
  } },
  { id: 'quartz_grey', name: '浅灰石英石', description: '冷灰晶粒与克制高光，适合台面及墙地面', material: {
    ...base, baseColor: [0.58, 0.6, 0.61], roughness: 0.26, surfaceFamily: 'mineral', surfacePattern: 'quartz',
    materialClass: 'clearcoat', clearcoat: 0.18, clearcoatRoughness: 0.2,
  } },
  { id: 'planks_oak', name: '浅橡木板', description: '错缝拼板、细木纹与板间色差', material: {
    ...base, baseColor: [0.65, 0.46, 0.27], roughness: 0.48, surfaceFamily: 'wood', surfacePattern: 'planks',
    materialClass: 'clearcoat', clearcoat: 0.12, clearcoatRoughness: 0.32,
  } },
  { id: 'planks_walnut', name: '胡桃木板', description: '深棕木纹、低光泽，适合柜体与地板', material: {
    ...base, baseColor: [0.29, 0.16, 0.085], roughness: 0.5, surfaceFamily: 'wood', surfacePattern: 'planks',
    materialClass: 'clearcoat', clearcoat: 0.1, clearcoatRoughness: 0.35,
  } },
  { id: 'glass_clear', name: '清透玻璃', description: '清透折射与轻微冷色吸收', material: {
    ...base, baseColor: [0.92, 0.97, 1], roughness: 0.055, surfaceFamily: 'glass', materialClass: 'glass',
    transmission: 0.94, ior: 1.5, thickness: 0.012, attenuationColor: [0.88, 0.96, 1], attenuationDistance: 6,
  } },
  { id: 'glass_frosted', name: '磨砂玻璃', description: '保留透光，弱化清晰透视', material: {
    ...base, baseColor: [0.88, 0.94, 0.95], roughness: 0.42, surfaceFamily: 'glass', materialClass: 'glass',
    transmission: 0.85, ior: 1.5, thickness: 0.016,
  } },
  { id: 'metal_brushed', name: '拉丝金属', description: '冷灰金属与柔和环境高光', material: {
    ...base, baseColor: [0.4, 0.43, 0.46], roughness: 0.32, metallic: 0.85, surfaceFamily: 'metal',
  } },
]
