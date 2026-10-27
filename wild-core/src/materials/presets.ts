import catalog from '../../material-presets.json'
import type { MaterialDef } from '../../types'

export interface BuiltinMaterialPreset {
  id: string
  name: string
  description: string
  recommendedRoles: string[]
  material: MaterialDef
}

/** 编辑器、作者工具和后端部署副本使用同一组可执行材质配方。 */
export const BUILTIN_MATERIAL_PRESETS = catalog as BuiltinMaterialPreset[]
