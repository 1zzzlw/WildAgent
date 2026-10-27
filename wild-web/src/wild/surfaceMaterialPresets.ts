import { BUILTIN_MATERIAL_PRESETS } from 'wild-core/materials'
import type { MaterialDef } from '../types/blueprint'

export const SURFACE_MATERIAL_PRESETS = BUILTIN_MATERIAL_PRESETS.map(preset => ({
  ...preset, material: preset.material as unknown as MaterialDef,
}))
