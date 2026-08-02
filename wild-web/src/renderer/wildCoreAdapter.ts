/**
 * wild-core 渲染引擎适配层
 * 
 * 封装 wild-core 的调用，提供统一的接口给前端使用：
 * - parseBlueprint(): 解析 .wild JSON 字符串
 * - reconstructEntity(): 重建场景几何
 * 
 * wild-core 位置：src/wild-core/src/primitive/
 * 
 * 使用方式：
 * ```ts
 * const blueprint = parseWildBlueprint(jsonText)
 * const entity = await reconstructWildEntity(blueprint)
 * ```
 */

import type { Blueprint } from '../types/blueprint'
import type { ReconstructedEntity } from '../types/scene'
import {
  compileBlueprintComponents,
  getComponentCapabilities,
} from '../wild-compiler'

// 导入 wild-core 的函数
// 注意：wild-core 使用的是 wild-lang/types.ts 的类型定义
import {
  parseBlueprint as coreParseBlueprint,
  reconstructEntity as coreReconstructEntity,
  getEngineCapabilities,
} from '../wild-core/src/primitive/index'

/**
 * 解析 .wild JSON 字符串为 Blueprint
 * 
 * @param jsonText - .wild 文件的 JSON 字符串
 * @returns Blueprint 对象
 * @throws 如果 JSON 格式错误或版本不支持
 */
export function parseWildBlueprint(jsonText: string): Blueprint {
  try {
    // wild-core 的 parseBlueprint 会校验 JSON 格式和版本
    const coreBlueprint = coreParseBlueprint(jsonText)

    // 类型转换：wild-core 使用的类型和我们的前端类型略有差异
    // 但结构是兼容的，可以直接使用
    return coreBlueprint as unknown as Blueprint
  } catch (error) {
    console.error('解析 Blueprint 失败:', error)
    throw error
  }
}

/**
 * 重建场景几何
 * 
 * 将 Blueprint 转换为可渲染的几何数据：
 * - meshes: 网格数据（顶点、索引、法线、颜色）
 * - materialParams: 材质参数
 * - boundingBox: 场景边界盒
 * 
 * @param blueprint - 已解析的 Blueprint
 * @returns Promise<ReconstructedEntity> 重建后的实体数据
 */
export async function reconstructWildEntity(blueprint: Blueprint): Promise<ReconstructedEntity> {
  try {
    // 高级组合构件先展开为 Core 已支持的基础元素；源 Blueprint 保持不变。
    const compilation = compileBlueprintComponents(blueprint as any)
    const coreEntity = await coreReconstructEntity(compilation.blueprint)
    coreEntity.diagnostics = [
      ...compilation.diagnostics,
      ...coreEntity.diagnostics,
    ]
    const errors = coreEntity.diagnostics.filter(item => item.level === 'error')
    if (errors.length > 0) {
      console.warn('WILD 重建完成，但存在构件错误:', errors)
    }

    return {
      ...coreEntity,
      componentMapping: compilation.mapping,
    } as unknown as ReconstructedEntity
  } catch (error) {
    console.error('重建场景失败:', error)
    throw error
  }
}

/**
 * 快速加载：解析 + 重建一步完成
 * 
 * @param jsonText - .wild 文件的 JSON 字符串
 * @returns Promise<{ blueprint, entity }> 蓝图和重建结果
 */
export async function loadWildScene(jsonText: string): Promise<{
  blueprint: Blueprint
  entity: ReconstructedEntity
}> {
  const blueprint = parseWildBlueprint(jsonText)
  const entity = await reconstructWildEntity(blueprint)

  return { blueprint, entity }
}

/**
 * 获取 wild-core 引擎信息
 */
export function getWildCoreInfo() {
  const componentCapabilities = getComponentCapabilities()
  return {
    version: '1.1.0',
    supportedVersion: '1.1',
    geometryTypes: getEngineCapabilities().map(item => item.type),
    capabilities: getEngineCapabilities(),
    componentTypes: componentCapabilities.map(item => item.type),
    componentCapabilities,
  }
}
