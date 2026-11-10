import { getComponentCapabilities, getRecipeCapabilities } from 'wild-core/compiler'
import type { ComponentSpec } from 'wild-core/types'

/**
 * 构件面板的条目装配。
 *
 * 为什么单独成模块：这段逻辑决定「引擎里注册了什么，面板上就能看到什么」。
 * 它一旦退化（某类构件静默消失），编译、渲染、校验全都正常，只有用户点不到 ——
 * 是最难靠肉眼发现的一类失败，所以必须能被测试直接调用。
 */

export interface ComponentEntry {
  type: string
  label: string
  icon: string
  description: string
  fixtureType?: 'bulb' | 'table_lamp'
}

/**
 * 尚未迁移成配方的手写构件才需要在这里登记显示名。
 *
 * **这个表只允许变短**：每迁移一个构件到 `recipes/*.json`，就删掉这里一条。
 * 12 种全部迁移完之后本表应被删除，面板完全由 `getRecipeCapabilities()` 驱动。
 */
export const LEGACY_COMPONENT_DISPLAY: readonly ComponentEntry[] = [
  { type: 'door', label: '门', icon: '▯', description: '选择墙面放置门' },
  { type: 'window', label: '窗', icon: '▦', description: '选择墙面放置窗' },
  { type: 'railing', label: '栏杆', icon: '╪', description: '创建一段路径栏杆' },
  { type: 'canopy', label: '雨棚', icon: '⌐', description: '创建依附墙体的雨棚' },
  { type: 'balcony', label: '阳台', icon: '▱', description: '创建带栏杆的悬挑阳台' },
  { type: 'ramp', label: '坡道', icon: '╱', description: '创建带可选栏杆的直线坡道' },
  { type: 'bay_window', label: '凸窗', icon: '▤', description: '创建向墙外投影的凸窗' },
  { type: 'cornice', label: '檐口', icon: '⌒', description: '选择屋顶放置分层檐口线脚' },
  { type: 'light', fixtureType: 'bulb', label: '灯泡', icon: '💡', description: '创建可拖动、可右键调光的裸灯泡' },
  { type: 'light', fixtureType: 'table_lamp', label: '台灯', icon: '♟', description: '创建带灯座、灯杆和灯罩的发光台灯' },
  { type: 'elevator', label: '电梯', icon: '↕', description: '创建轿厢、层门与楼层按钮；放入井道并为上层楼板留洞' },
]

/** 引擎里**注册了什么**就列什么 —— 面板不允许漏构件。 */
export function buildComponentEntries(): ComponentEntry[] {
  const recipes = new Map(getRecipeCapabilities().map(entry => [entry.type, entry]))
  const entries: ComponentEntry[] = []
  for (const capability of getComponentCapabilities()) {
    const recipe = recipes.get(capability.type)
    if (recipe) {
      entries.push({
        type: capability.type,
        label: recipe.label,
        icon: recipe.icon,
        description: recipe.description,
      })
      continue
    }
    const legacy = LEGACY_COMPONENT_DISPLAY.filter(item => item.type === capability.type)
    if (legacy.length > 0) {
      entries.push(...legacy)
      continue
    }
    // 兜底：注册了但没有显示名，仍然列出来。静默消失比显示英文 type 更糟。
    entries.push({ type: capability.type, label: capability.type, icon: '◇', description: capability.description })
  }
  return entries
}

/** 面板点击后交给放置流程的类型。配方构件的 type 是运行期字符串。 */
export function entryComponentType(entry: ComponentEntry): ComponentSpec['type'] {
  return entry.type as ComponentSpec['type']
}
