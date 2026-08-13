import type { MaterialDef } from '../types/blueprint'

export interface ProceduralMaterialPreset {
  id: string
  name: string
  description: string
  material: MaterialDef
}

export const PROCEDURAL_BRICK_PRESETS: ProceduralMaterialPreset[] = [
  preset('brick_new_red', '新红砖', '颜色整齐、轻微烧制色差，无明显老化', {
    baseColor: [0.54, 0.12, 0.055], secondaryColor: [0.68, 0.2, 0.08],
    colorVariation: 0.1, roughnessVariation: 0.1, edgeWear: 0.025,
    weathering: { amount: 0.04, scale: 1.8, efflorescence: 0, verticalStreaks: 0, baseDampness: 0 },
  }),
  preset('brick_aged_red', '自然旧红砖', '连续风化、少量雨痕和边缘磨损', {
    baseColor: [0.52, 0.11, 0.055], secondaryColor: [0.68, 0.19, 0.08],
    colorVariation: 0.14, roughnessVariation: 0.16, edgeWear: 0.06,
    weathering: { amount: 0.28, scale: 1.8, efflorescence: 0.1, verticalStreaks: 0.14, baseDampness: 0.08 },
  }),
  preset('brick_salt_weathered', '潮湿盐碱红砖', '墙脚潮湿、盐碱泛白和竖向流痕', {
    baseColor: [0.46, 0.095, 0.045], secondaryColor: [0.62, 0.16, 0.065],
    colorVariation: 0.16, roughnessVariation: 0.19, edgeWear: 0.08,
    weathering: { amount: 0.48, scale: 1.35, efflorescence: 0.46, verticalStreaks: 0.24, baseDampness: 0.34 },
  }),
]

export function cloneMaterial<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T
}

function preset(
  id: string,
  name: string,
  description: string,
  values: {
    baseColor: [number, number, number]
    secondaryColor: [number, number, number]
    colorVariation: number
    roughnessVariation: number
    edgeWear: number
    weathering: NonNullable<NonNullable<MaterialDef['procedural']>['weathering']>
  },
): ProceduralMaterialPreset {
  return {
    id,
    name,
    description,
    material: {
      baseColor: values.baseColor,
      roughness: 0.84,
      metallic: 0,
      albedo: 1,
      lightingCondition: 'D65_noon',
      side: 'front',
      procedural: {
        type: 'brick',
        seed: 42,
        brickSize: [0.24, 0.065],
        mortarWidth: 0.01,
        mortarDepth: 0.006,
        bond: 'running',
        secondaryColor: values.secondaryColor,
        colorVariation: values.colorVariation,
        roughnessVariation: values.roughnessVariation,
        edgeWear: values.edgeWear,
        weathering: values.weathering,
      },
    },
  }
}
