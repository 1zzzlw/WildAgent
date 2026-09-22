import type { ComponentSpec } from '../wild-core/types'
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

export interface ComponentCompilerRegistration {
  type: ComponentSpec['type']
  description: string
  compile: ComponentCompiler
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
}> {
  return [...compilers.values()]
    .map(({ type, description }) => ({ type, description }))
    .sort((left, right) => left.type.localeCompare(right.type))
}

function registerBuiltins(): void {
  registerComponentCompiler({
    type: 'door',
    description: '将静态门编译为墙体 opening 与门框 primitive',
    compile: (component, context) => compileDoor(component as Extract<ComponentSpec, { type: 'door' }>, context),
  })
  registerComponentCompiler({
    type: 'window',
    description: '将静态窗编译为墙体 opening、窗框与窗棂 primitive',
    compile: (component, context) => compileWindow(component as Extract<ComponentSpec, { type: 'window' }>, context),
  })
  registerComponentCompiler({
    type: 'railing',
    description: '将路径栏杆编译为立柱 primitive 与横向 beam',
    compile: (component, context) => compileRailing(component as Extract<ComponentSpec, { type: 'railing' }>, context),
  })
  registerComponentCompiler({
    type: 'canopy',
    description: '将墙体雨棚编译为板和可选支柱',
    compile: (component, context) => compileCanopy(component as Extract<ComponentSpec, { type: 'canopy' }>, context),
  })
  registerComponentCompiler({
    type: 'balcony',
    description: '将墙体阳台编译为悬挑板和路径栏杆',
    compile: (component, context) => compileBalcony(component as Extract<ComponentSpec, { type: 'balcony' }>, context),
  })
  registerComponentCompiler({
    type: 'ramp',
    description: '将直线坡道编译为矩形梁体和可选栏杆',
    compile: (component, context) => compileRamp(component as Extract<ComponentSpec, { type: 'ramp' }>, context),
  })
  registerComponentCompiler({
    type: 'bay_window',
    description: '将凸窗编译为墙洞、窗框和投影窗体',
    compile: (component, context) => compileBayWindow(component as Extract<ComponentSpec, { type: 'bay_window' }>, context),
  })
  registerComponentCompiler({
    type: 'cornice',
    description: '将檐口编译为沿路径扫掠的通用截面',
    compile: (component, context) => compileCornice(component as Extract<ComponentSpec, { type: 'cornice' }>, context),
  })
  registerComponentCompiler({
    type: 'chimney',
    description: '将烟囱编译为薄壁筒体和顶部压顶',
    compile: (component, context) => compileChimney(component as Extract<ComponentSpec, { type: 'chimney' }>, context),
  })
  registerComponentCompiler({
    type: 'light',
    description: '将交互灯具编译为灯泡、灯座和运行时光源行为',
    compile: (component, context) => compileLight(component as Extract<ComponentSpec, { type: 'light' }>, context),
  })
}

registerBuiltins()
