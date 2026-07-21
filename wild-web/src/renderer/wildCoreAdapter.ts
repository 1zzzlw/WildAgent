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

// 导入 wild-core 的函数
// 注意：wild-core 使用的是 wild-lang/types.ts 的类型定义
import {
  parseBlueprint as coreParseBlueprint,
  reconstructEntity as coreReconstructEntity
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
    // 添加调试输出
    import('../utils/debugRender').then(({ logBlueprintInfo, logEntityInfo, logResolverChanges }) => {
      logBlueprintInfo(blueprint);
    });
    
    // 调用 wild-core 的重建函数
    const coreEntity = await coreReconstructEntity(blueprint as any)
    
    // 调试：输出重建后的信息
    import('../utils/debugRender').then(({ logEntityInfo, logResolverChanges }) => {
      logResolverChanges(blueprint);
      logEntityInfo(coreEntity as unknown as ReconstructedEntity);
    });

    return coreEntity as unknown as ReconstructedEntity
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
  return {
    version: '1.0',
    supportedVersion: '1.0',
    geometryTypes: [
      'wall', 'floor', 'column', 'beam', 'roof',
      'opening', 'stair', 'furniture', 'dense_brick', 'body'
    ]
  }
}
