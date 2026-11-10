import type { ComponentRecipe } from '../types'
import fan from './fan.json'
import chimney from './chimney.json'
import louverPanel from './louver_panel.json'

/**
 * 数据化构件的清单。
 *
 * 新增一个构件 = 放一份同名 `.json` 进本目录 + 在这里加一行 import。
 * 这一行是**数据清单**，不是引擎代码：`componentRegistry`、`types.ts`、
 * schema 两副本、属性面板、构件面板都不用动。
 *
 * 为什么不用 `import.meta.glob` 自动扫描：`wild-core` 要能被 tsc 独立
 * typecheck，glob 只存在于 vite 里。显式清单换来的是两侧都能编译。
 */
export const RECIPES: readonly ComponentRecipe[] = [
  fan as ComponentRecipe,
  chimney as ComponentRecipe,
  louverPanel as ComponentRecipe,
]
