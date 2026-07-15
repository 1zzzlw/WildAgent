/**
 * 通用工具函数
 * 
 * 提供项目中常用的工具函数：
 * 
 * - deepClone(): 深拷贝对象
 *   - 用于 Patch 应用前复制 Blueprint
 *   - 避免直接修改原对象
 * 
 * - generateId(): 生成唯一 ID
 *   - 格式：prefix_timestamp_random
 *   - 用于生成 patch_id、session_id 等
 * 
 * - debounce(): 防抖函数
 *   - 用于输入框、窗口 resize 等高频事件
 *   - 避免频繁触发重建和渲染
 */

export function deepClone<T>(obj: T): T {
  return JSON.parse(JSON.stringify(obj))
}

export function generateId(prefix: string): string {
  return `${prefix}_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`
}

export function debounce<T extends (...args: any[]) => void>(
  fn: T,
  delay: number
): (...args: Parameters<T>) => void {
  let timeoutId: ReturnType<typeof setTimeout> | null = null
  return (...args: Parameters<T>) => {
    if (timeoutId) clearTimeout(timeoutId)
    timeoutId = setTimeout(() => fn(...args), delay)
  }
}
