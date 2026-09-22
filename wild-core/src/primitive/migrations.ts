export interface BlueprintMigrationResult<T = any> {
  blueprint: T
  fromVersion: string
  toVersion: string
  applied: string[]
}

/**
 * 显式执行 WILD 版本迁移。当前只把已被归一化器兼容处理的 1.0 文档
 * 提升为 1.1，避免旧版本继续在保存链路中无期限传播。
 */
export function migrateBlueprintToLatest<T = any>(value: T): BlueprintMigrationResult<T> {
  const source = value as any
  const fromVersion = String(source?.meta?.version || '')
  if (fromVersion !== '1.0') {
    return { blueprint: value, fromVersion, toVersion: fromVersion, applied: [] }
  }
  const blueprint = {
    ...source,
    meta: { ...source.meta, version: '1.1' },
  }
  return {
    blueprint,
    fromVersion,
    toVersion: '1.1',
    applied: ['meta.version: 1.0 -> 1.1'],
  }
}
