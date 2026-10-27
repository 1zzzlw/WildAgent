import type { ComponentSpec } from '../../types'
import type { ComponentCompiler } from './types'
import { compileDoor } from './components/door'
import { compileRailing } from './components/railing'
import { compileWindow } from './components/window'
import { compileBalcony } from './components/balcony'
import { compileBayWindow } from './components/bayWindow'
import { compileCanopy } from './components/canopy'
import { compileChimney } from './components/chimney'
import { compileCornice } from './components/cornice'
import { compileRamp } from './components/ramp'
import { compileLight } from './components/light'
import { compileElevator } from './components/elevator'

export interface ComponentCompilerRegistration {
  type: ComponentSpec['type']
  description: string
  compile: ComponentCompiler
  editing?: {
    translation: 'wallFrom' | 'fromTo' | 'path' | 'position' | 'lightBody'
    host?: 'parentWall' | 'parentFloor' | 'parentRoof'
    hostRequired?: boolean
    parameters: readonly string[]
  }
  /** Context actually read in addition to the explicit host. */
  contextDependencies?: readonly ('walls' | 'canopiesAndBalconies')[]
}

const compilers = new Map<string, ComponentCompilerRegistration>()

/** 注册高级构件编译器；同名注册会立即失败，避免启动顺序覆盖实现。 */
export function registerComponentCompiler(
  registration: ComponentCompilerRegistration,
): void {
  if (compilers.has(registration.type)) {
    throw new Error(`Component compiler already registered: ${registration.type}`)
  }
  compilers.set(registration.type, registration)
}

export function getComponentCompiler(
  type: string,
): ComponentCompilerRegistration | undefined {
  return compilers.get(type)
}

export function getComponentCapabilities(): Array<{
  type: string
  description: string
  editing?: ComponentCompilerRegistration['editing']
}> {
  return [...compilers.values()]
    .map(({ type, description, editing }) => ({ type, description,
      ...(editing ? { editing: { ...editing, parameters: [...editing.parameters] } } : {}),
    }))
    .sort((left, right) => left.type.localeCompare(right.type))
}

function registerBuiltins(): void {
  registerComponentCompiler({
    type: 'door',
    editing: { translation: 'wallFrom', host: 'parentWall', hostRequired: true, parameters: ['width', 'height', 'frameWidth', 'frameDepth', 'leafDepth'] },
    description: '将门编译为墙洞、门框和默认可平开的门扇；interaction:false 固定',
    compile: (component, context) => compileDoor(component as Extract<ComponentSpec, { type: 'door' }>, context),
  })
  registerComponentCompiler({
    type: 'window',
    editing: { translation: 'wallFrom', host: 'parentWall', hostRequired: true, parameters: ['width', 'height', 'frameWidth', 'frameDepth', 'verticalMullions', 'horizontalMullions'] },
    description: '将窗编译为墙洞、窗框和默认可平开的双扇窗；interaction:false 固定',
    compile: (component, context) => compileWindow(component as Extract<ComponentSpec, { type: 'window' }>, context),
  })
  registerComponentCompiler({
    type: 'railing',
    editing: { translation: 'path', host: 'parentFloor', parameters: ['height', 'postSpacing', 'postRadius', 'railRadius'] },
    description: '将路径栏杆编译为立柱 primitive 与横向 beam',
    compile: (component, context) => compileRailing(component as Extract<ComponentSpec, { type: 'railing' }>, context),
  })
  registerComponentCompiler({
    type: 'canopy',
    editing: { translation: 'wallFrom', host: 'parentWall', hostRequired: true, parameters: ['width', 'depth', 'thickness', 'supportCount'] },
    contextDependencies: ['walls'],
    description: '将墙体雨棚编译为板和可选支柱',
    compile: (component, context) => compileCanopy(component as Extract<ComponentSpec, { type: 'canopy' }>, context),
  })
  registerComponentCompiler({
    type: 'balcony',
    editing: { translation: 'wallFrom', host: 'parentWall', hostRequired: true, parameters: ['width', 'depth', 'slabThickness', 'railingHeight'] },
    contextDependencies: ['walls'],
    description: '将墙体阳台编译为悬挑板和路径栏杆',
    compile: (component, context) => compileBalcony(component as Extract<ComponentSpec, { type: 'balcony' }>, context),
  })
  registerComponentCompiler({
    type: 'ramp',
    editing: { translation: 'fromTo', host: 'parentFloor', parameters: ['width', 'thickness', 'railingHeight'] },
    description: '将直线坡道编译为矩形梁体和可选栏杆',
    compile: (component, context) => compileRamp(component as Extract<ComponentSpec, { type: 'ramp' }>, context),
  })
  registerComponentCompiler({
    type: 'bay_window',
    editing: { translation: 'wallFrom', host: 'parentWall', hostRequired: true, parameters: ['width', 'height', 'frameWidth', 'frameDepth', 'projectionDepth'] },
    description: '将凸窗编译为墙洞、投影窗体和默认可推拉的正面窗扇',
    compile: (component, context) => compileBayWindow(component as Extract<ComponentSpec, { type: 'bay_window' }>, context),
  })
  registerComponentCompiler({
    type: 'cornice',
    editing: { translation: 'path', host: 'parentRoof', parameters: [] },
    contextDependencies: ['walls', 'canopiesAndBalconies'],
    description: '将檐口编译为沿路径扫掠的通用截面',
    compile: (component, context) => compileCornice(component as Extract<ComponentSpec, { type: 'cornice' }>, context),
  })
  registerComponentCompiler({
    type: 'chimney',
    editing: { translation: 'position', host: 'parentRoof', parameters: ['width', 'depth', 'height', 'wallThickness', 'capHeight'] },
    description: '将烟囱编译为薄壁筒体和顶部压顶',
    compile: (component, context) => compileChimney(component as Extract<ComponentSpec, { type: 'chimney' }>, context),
  })
  registerComponentCompiler({
    type: 'light',
    editing: { translation: 'lightBody', parameters: ['height', 'shadeRadius', 'lowIntensity', 'highIntensity', 'distance'] },
    description: '将交互灯具编译为灯泡、灯座和运行时光源行为',
    compile: (component, context) => compileLight(component as Extract<ComponentSpec, { type: 'light' }>, context),
  })
  registerComponentCompiler({
    type: 'elevator',
    editing: { translation: 'position', parameters: ['width', 'depth', 'floorHeight', 'floorCount'] },
    description: '将电梯编译为可动轿厢、导轨与呼梯按钮（点击上下移动）',
    compile: (component, context) => compileElevator(component as Extract<ComponentSpec, { type: 'elevator' }>, context),
  })
}

registerBuiltins()
