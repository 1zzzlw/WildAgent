import * as THREE from 'three'
import { createWallCoordinateFrame, type ComponentCompilationMapping } from 'wild-core/compiler'
import type { WallParams } from 'wild-core/types'
import type { Blueprint } from '../types/blueprint'

export interface BuildingApproach {
  /** 显示世界坐标中的门槛中心及水平向外方向。 */
  position: THREE.Vector3
  outward: THREE.Vector3
}

/** 由已渲染的低层外门推导正面，供展示镜头和人物出生共用；不写回蓝图。 */
export function resolveBuildingApproach(
  blueprint: Blueprint,
  root: THREE.Object3D,
  mapping: ComponentCompilationMapping,
): BuildingApproach | null {
  const walls = new Map((blueprint.geometry.elements.filter(item => item.type === 'wall') as unknown as WallParams[])
    .map(wall => [wall.id, wall]))
  const wallMeshes: THREE.Mesh[] = []
  const rendered = new Set<string>()
  root.updateWorldMatrix(true, true)
  root.traverse(object => {
    if (!(object instanceof THREE.Mesh) || object.userData.isError) return
    const ids: string[] = object.userData.instanceElementIds ?? [object.userData.elementId]
    ids.forEach(id => rendered.add(id))
    if (ids.some(id => walls.has(id))) wallMeshes.push(object)
  })
  const bounds = new THREE.Box3().setFromObject(root)
  if (bounds.isEmpty()) return null
  const center = bounds.getCenter(new THREE.Vector3())
  const normalMatrix = new THREE.Matrix3().getNormalMatrix(root.matrixWorld)
  const raycaster = new THREE.Raycaster()
  raycaster.far = bounds.getSize(new THREE.Vector3()).length() + 1
  const candidates: Array<BuildingApproach & { width: number }> = []
  for (const door of blueprint.geometry.components ?? []) {
    if (door.type !== 'door'
      || !mapping.generatedElementIdsByComponentId[door.id]?.some(id => rendered.has(id))) continue
    const wall = walls.get(door.parentWall)
    if (!wall) continue
    const along = door.from[0] + door.width / 2
    const frame = createWallCoordinateFrame(wall, along)
    const position = new THREE.Vector3(...frame.pointAt(along, door.from[1], door.from[2])).applyMatrix4(root.matrixWorld)
    const outward = new THREE.Vector3(...frame.normalAt(along)).applyNormalMatrix(normalMatrix)
    outward.y = 0
    if (outward.lengthSq() < 1e-8) continue
    outward.normalize()
    if (position.clone().sub(center).dot(outward) < 0) outward.negate()
    // 室内门朝外仍会遇到其他墙体；不要把它当作街道入口。
    const origin = position.clone().add(new THREE.Vector3(0, door.height * 0.5, 0))
    const blocked = (direction: THREE.Vector3) => {
      raycaster.set(origin, direction)
      return raycaster.intersectObjects(wallMeshes, false).some(hit => {
        const id = hit.instanceId === undefined ? hit.object.userData.elementId
          : hit.object.userData.instanceElementIds?.[hit.instanceId]
        return id !== wall.id && walls.has(id)
      })
    }
    if (blocked(outward)) {
      outward.negate()
      if (blocked(outward)) continue
    }
    candidates.push({ position, outward, width: door.width })
  }
  if (!candidates.length) return null
  // 在最低入口附近优先选择较宽的外门，避免楼上阳台门抢占初始机位。
  const lowest = Math.min(...candidates.map(candidate => candidate.position.y))
  return candidates.filter(candidate => candidate.position.y <= lowest + 0.4)
    .sort((a, b) => b.width - a.width)[0] ?? null
}
