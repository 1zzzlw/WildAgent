import type {
  ElevatorComponent,
  ElevatorElementBehavior,
  GeometryElement,
  PrimitiveParams,
} from '../../../types'
import type { ComponentCompileContext } from '../types'
import { COMPONENT_MATERIAL } from '../componentMaterials'
import {
  assertNonEmptyString,
  assertPositive,
  assertVec3,
} from './attachedToWall'

/**
 * 将电梯编译为导轨 + 可动轿厢 + 呼梯按钮；井道围合由 wall_core_* 表达。
 *
 * 交互契约（与前端 renderEntity 约定）：
 * - 轿厢网格携带 `kind: 'elevator'`；右键点击轿厢或按钮 → 下一楼层，
 *   已在顶层则回到 0 层（循环）。
 * - `floorCount` 只取井道真实跨越的层数；`floorHeight` 与建筑层高一致，
 *   停靠位置恒为 `floorHeight` 的整数倍，轿厢地板对齐该层地面。
 * - 静态蓝图只保存 `initialFloor`；运行时楼层进度只存在前端 userData，
 *   与门窗开合同一套「不写回蓝图」原则。
 */
export function compileElevator(
  component: ElevatorComponent,
  _context: ComponentCompileContext,
): GeometryElement[] {
  assertNonEmptyString(component.id, 'id')
  assertVec3(component.position, 'position')
  assertPositive(component.dimensions.width, 'dimensions.width')
  assertPositive(component.dimensions.depth, 'dimensions.depth')
  assertPositive(component.dimensions.height, 'dimensions.height')
  assertPositive(component.floorHeight, 'floorHeight')
  if (!Number.isInteger(component.floorCount) || component.floorCount < 1) {
    throw new Error('elevator.floorCount 必须是 ≥1 的整数')
  }
  const initialFloor = component.initialFloor ?? 0
  if (!Number.isInteger(initialFloor) || initialFloor < 0 || initialFloor >= component.floorCount) {
    throw new Error('elevator.initialFloor 必须落在 [0, floorCount) 内')
  }

  const { width, depth, height } = component.dimensions
  const cabHeight = Math.min(height, component.floorHeight - 0.15)
  const behavior: ElevatorElementBehavior = {
    kind: 'elevator',
    floorHeight: component.floorHeight,
    floorCount: component.floorCount,
    initialFloor,
  }

  // 轿厢：位置是「当前停靠层的轿厢地板中心」，几何体中心再抬高 cabHeight/2。
  const cab: PrimitiveParams = {
    type: 'primitive',
    id: `${component.id}__cab`,
    shape: 'box',
    position: [
      component.position[0],
      component.position[1] + cabHeight / 2,
      component.position[2],
    ],
    dimensions: [width, cabHeight, depth],
    rotation: [0, 0, 0],
    _interaction: behavior,
  }
  applyMaterial(cab, component.material)

  // 两根导轨：贴轿厢背部两侧，从底层导轨座到顶层下缘，不随轿厢移动。
  const travel = (component.floorCount - 1) * component.floorHeight
  const railHeight = travel + cabHeight
  const railX = width / 2 + 0.06
  const rails: GeometryElement[] = ([-1, 1] as const).map(side => {
    const rail: PrimitiveParams = {
      type: 'primitive',
      id: `${component.id}__rail_${side < 0 ? 'l' : 'r'}`,
      shape: 'box',
      position: [
        component.position[0] + side * railX,
        component.position[1] - initialFloor * component.floorHeight + railHeight / 2,
        component.position[2] - depth / 2 - 0.05,
      ],
      dimensions: [0.06, railHeight, 0.06],
      rotation: [0, 0, 0],
    }
    applyMaterial(rail, component.frameMaterial ?? COMPONENT_MATERIAL.frame)
    return rail as GeometryElement
  })

  // 呼梯按钮：底层候梯位墙侧（轿厢前方右侧），点击即呼梯。按钮盘小方块+按钮柱。
  const callButton: GeometryElement = (() => {
    const button: PrimitiveParams = {
      type: 'primitive',
      id: `${component.id}__call_button`,
      shape: 'cylinder',
      position: [
        component.position[0] + width / 2 + 0.12,
        component.position[1] + 1.1,
        component.position[2] + depth / 2 + 0.12,
      ],
      radius: 0.05,
      height: 0.03,
      segments: 16,
      rotation: [Math.PI / 2, 0, 0],
      _interaction: behavior,
    }
    applyMaterial(button, COMPONENT_MATERIAL.bulbEmitter)
    return button as GeometryElement
  })()

  return [cab, ...rails, callButton]
}

function applyMaterial(params: PrimitiveParams, material: string | undefined): void {
  if (material) params.material = material
}
