/**
 * 构件 ID 生成工具
 * 
 * 提供生成唯一构件 ID 的工具函数：
 * 
 * - generateElementId(): 生成格式化的构件 ID（如 wall_01, col_02）
 *   - 自动递增序号
 *   - 检查 ID 唯一性
 *   - 补零对齐（01, 02, ...）
 * 
 * - generateUniqueId(): 生成带时间戳和随机数的唯一 ID
 *   - 格式：prefix_timestamp_random
 *   - 保证全局唯一
 * 
 * 用于：
 * - 构件库添加构件时生成 ID
 * - Agent 生成新构件时生成 ID
 * - 确保 Blueprint 中所有 ID 唯一
 */

export function generateElementId(type: string, existingIds: Set<string>): string {
  let counter = 1
  let id = `${type}_${counter.toString().padStart(2, '0')}`
  
  while (existingIds.has(id)) {
    counter++
    id = `${type}_${counter.toString().padStart(2, '0')}`
  }
  
  return id
}

export function generateUniqueId(prefix: string): string {
  return `${prefix}_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`
}
