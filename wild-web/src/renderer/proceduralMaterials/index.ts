import type * as THREE from 'three'
import type { ProceduralMaterial } from '../../wild-core/types'
import { applyProceduralBrickMaterial } from './brickMaterial'
import { normalizeProceduralBrick } from './types'

export function applyProceduralMaterial(
  material: THREE.MeshStandardMaterial,
  procedural: ProceduralMaterial | undefined,
  baseColor: [number, number, number],
): void {
  if (!procedural || procedural.type !== 'brick') return
  applyProceduralBrickMaterial(
    material,
    normalizeProceduralBrick(procedural, baseColor),
  )
}

export { normalizeProceduralBrick } from './types'
export { installBrickShader } from './brickMaterial'
