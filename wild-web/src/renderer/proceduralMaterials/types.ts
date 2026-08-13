import type { ProceduralBrickMaterial } from '../../wild-core/types'

export interface NormalizedProceduralBrickMaterial {
  type: 'brick'
  seed: number
  brickSize: [number, number]
  mortarWidth: number
  mortarDepth: number
  bond: 'running' | 'stack'
  secondaryColor: [number, number, number]
  colorVariation: number
  roughnessVariation: number
  edgeWear: number
  weathering: {
    amount: number
    scale: number
    efflorescence: number
    verticalStreaks: number
    baseDampness: number
  }
}

export function normalizeProceduralBrick(
  value: ProceduralBrickMaterial,
  baseColor: [number, number, number],
): NormalizedProceduralBrickMaterial {
  const width = range(value.brickSize?.[0], 0.04, 2, 0.24)
  const height = range(value.brickSize?.[1], 0.02, 1, 0.065)
  const maxMortar = Math.max(0.002, Math.min(0.03, Math.min(width, height) * 0.49))
  const weathering = value.weathering || {}
  return {
    type: 'brick',
    seed: integer(value.seed, 0, 2_147_483_647, 1),
    brickSize: [width, height],
    mortarWidth: range(value.mortarWidth, 0.002, maxMortar, Math.min(0.01, maxMortar)),
    mortarDepth: range(value.mortarDepth, 0, 0.02, 0.006),
    bond: value.bond === 'stack' ? 'stack' : 'running',
    secondaryColor: color(value.secondaryColor, deriveSecondaryColor(baseColor)),
    colorVariation: unit(value.colorVariation, 0.12),
    roughnessVariation: unit(value.roughnessVariation, 0.12),
    edgeWear: unit(value.edgeWear, 0.05),
    weathering: {
      amount: unit(weathering.amount, 0),
      scale: range(weathering.scale, 0.1, 100, 1.8),
      efflorescence: unit(weathering.efflorescence, 0),
      verticalStreaks: unit(weathering.verticalStreaks, 0),
      baseDampness: unit(weathering.baseDampness, 0),
    },
  }
}

function unit(value: unknown, fallback: number): number {
  return range(value, 0, 1, fallback)
}

function range(value: unknown, min: number, max: number, fallback: number): number {
  return typeof value === 'number' && Number.isFinite(value)
    ? Math.min(max, Math.max(min, value))
    : fallback
}

function integer(value: unknown, min: number, max: number, fallback: number): number {
  return typeof value === 'number' && Number.isFinite(value) && Number.isInteger(value)
    ? Math.min(max, Math.max(min, value))
    : fallback
}

function color(
  value: unknown,
  fallback: [number, number, number],
): [number, number, number] {
  return Array.isArray(value) && value.length === 3 && value.every(channel => (
    typeof channel === 'number' && Number.isFinite(channel) && channel >= 0 && channel <= 1
  ))
    ? [value[0], value[1], value[2]]
    : [...fallback]
}

function deriveSecondaryColor(baseColor: [number, number, number]): [number, number, number] {
  return [
    Math.min(1, baseColor[0] * 1.18 + 0.025),
    Math.min(1, baseColor[1] * 1.12 + 0.012),
    Math.min(1, baseColor[2] * 0.96 + 0.008),
  ]
}
