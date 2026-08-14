/**
 * Blueprint 校验器
 * 
 * 校验 Blueprint 的合法性，包括：
 * - meta 字段完整性（version, type）
 * - 构件 id 唯一性
 * - 构件 type 存在性
 * - 材质引用有效性（构件引用的材质必须存在）
 * - 父元素存在性（opening.parentWall 必须存在）
 * 
 * 返回 ValidationIssue 列表：
 * - level: 'error' | 'warning'
 * - message: 问题描述
 * - elementId / path: 问题位置
 * 
 * 校验时机：
 * - applyPatch 之前
 * - 用户手动触发校验
 * - Agent 生成 Patch 之前
 */

import type { Blueprint } from '../types/blueprint'
import type { ValidationIssue } from '../types/scenePatch'
import { compileBlueprintComponents } from '../wild-compiler'

export function validateBlueprint(blueprint: Blueprint): ValidationIssue[] {
  const issues: ValidationIssue[] = []

  // 校验 meta
  if (!blueprint.meta?.version) {
    issues.push({ level: 'error', message: 'Blueprint 缺少 meta.version', path: 'meta.version' })
  }
  if (!blueprint.meta?.type) {
    issues.push({ level: 'error', message: 'Blueprint 缺少 meta.type', path: 'meta.type' })
  }

  // 校验 geometry
  if (!blueprint.geometry) {
    issues.push({ level: 'error', message: 'Blueprint 缺少 geometry', path: 'geometry' })
    return issues
  }

  // 检查元素 id 唯一性
  const elementIds = new Set<string>()
  for (const element of blueprint.geometry.elements || []) {
    if (!element.id) {
      issues.push({ level: 'error', message: '构件缺少 id', path: `geometry.elements` })
      continue
    }

    if (elementIds.has(element.id)) {
      issues.push({
        level: 'error',
        message: `构件 id 重复: ${element.id}`,
        elementId: element.id
      })
    }
    elementIds.add(element.id)

    // 校验构件类型
    if (!element.type) {
      issues.push({
        level: 'error',
        message: `构件 ${element.id} 缺少 type`,
        elementId: element.id
      })
    }
  }

  // 校验材质引用
  const materialNames = new Set(Object.keys(blueprint.materials || {}))
  const assetNames = new Set(Object.keys(blueprint.assets || {}))
  for (const [assetId, rawAsset] of Object.entries(blueprint.assets || {})) {
    const asset = rawAsset as any
    const path = `assets.${assetId}`
    if (!/^pbr_[0-9a-f]{24}$/.test(assetId) || asset?.assetId !== assetId) {
      issues.push({ level: 'error', message: `PBR 资产 ${assetId} 标识无效`, path })
    }
    if (asset?.kind !== 'pbr_texture_set' || !/^sha256:[0-9a-f]{64}$/.test(asset?.contentHash || '')) {
      issues.push({ level: 'error', message: `PBR 资产 ${assetId} 清单无效`, path })
    }
    if (typeof asset?.license !== 'string' || !asset.license.trim()) {
      issues.push({ level: 'error', message: `PBR 资产 ${assetId} 缺少授权信息`, path: `${path}.license` })
    }
    if (!asset?.maps?.baseColor) {
      issues.push({ level: 'error', message: `PBR 资产 ${assetId} 缺少 baseColor`, path: `${path}.maps.baseColor` })
    }
    const supportedChannels = new Set([
      'baseColor', 'normal', 'roughness', 'metalness', 'ambientOcclusion',
    ])
    for (const [channel, image] of Object.entries(asset?.maps || {})) {
      const ref = image as any
      if (!supportedChannels.has(channel)) {
        issues.push({ level: 'error', message: `PBR 资产 ${assetId} 包含未知通道: ${channel}`, path: `${path}.maps.${channel}` })
        continue
      }
      const validUri = typeof ref?.uri === 'string'
        && (/^https?:\/\/\S+$/.test(ref.uri)
          || /^wildpkg:\/\/[a-zA-Z0-9._:/%-]+$/.test(ref.uri)
          || (/^\//.test(ref.uri) && !/^\/\//.test(ref.uri)))
      if (
        ref?.encoding !== 'url'
        || !validUri
        || !/^image\/(png|jpeg|webp|ktx2)$/.test(ref?.mimeType || '')
        || !/^[0-9a-f]{64}$/.test(ref?.sha256 || '')
      ) {
        issues.push({
          level: 'error',
          message: `PBR 资产 ${assetId} 的 ${channel} URL 引用无效`,
          path: `${path}.maps.${channel}`
        })
      }
      const expectedColorSpace = channel === 'baseColor' ? 'srgb' : 'linear'
      if (ref?.colorSpace !== expectedColorSpace) {
        issues.push({
          level: 'error',
          message: `PBR 资产 ${assetId} 的 ${channel} colorSpace 必须是 ${expectedColorSpace}`,
          path: `${path}.maps.${channel}.colorSpace`
        })
      }
    }
  }
  for (const [name, material] of Object.entries(blueprint.materials || {})) {
    const baseColor = (material as any)?.baseColor
    const validBaseColor = Array.isArray(baseColor)
      && baseColor.length === 3
      && baseColor.every(
        value => typeof value === 'number'
          && Number.isFinite(value)
          && value >= 0
          && value <= 1
      )
    if (!validBaseColor) {
      issues.push({
        level: 'error',
        message: `材质 ${name} 的 baseColor 必须是 3 个 0–1 数值`,
        path: `materials.${name}.baseColor`
      })
    }
    const textureSet = (material as any)?.textureSet
    if (textureSet && !assetNames.has(textureSet)) {
      issues.push({
        level: 'error',
        message: `材质 ${name} 引用了不存在的 PBR 资产: ${textureSet}`,
        path: `materials.${name}.textureSet`
      })
    }
  }

  for (const element of blueprint.geometry.elements || []) {
    const mat = (element as any).material
    if (mat && typeof mat === 'string' && !materialNames.has(mat)) {
      issues.push({
        level: 'warning',
        message: `构件 ${element.id} 引用了不存在的材质: ${mat}`,
        elementId: element.id
      })
    }
  }

  // 组合构件与基础元素共享 ID 命名空间；编译器会进一步校验尺寸和空间关系。
  const componentIds = new Set<string>()
  for (const component of blueprint.geometry.components || []) {
    if (!component.id) {
      issues.push({
        level: 'error',
        message: '组合构件缺少 id',
        path: 'geometry.components'
      })
      continue
    }
    if (componentIds.has(component.id) || elementIds.has(component.id)) {
      issues.push({
        level: 'error',
        message: `构件 id 重复: ${component.id}`,
        elementId: component.id
      })
    }
    componentIds.add(component.id)
  }

  const compilation = compileBlueprintComponents(blueprint as any)
  for (const diagnostic of compilation.diagnostics) {
    // 保留原始级别：error 级编译诊断应阻止 Patch 提交，warning 级仅提示。
    issues.push({
      level: diagnostic.level,
      message: diagnostic.message,
      elementId: diagnostic.elementId,
      path: `geometry.components.${diagnostic.elementId}`
    })
  }

  // 校验 opening.parentWall
  for (const element of blueprint.geometry.elements || []) {
    if (element.type === 'opening') {
      const parentWall = (element as any).parentWall
      if (parentWall && !elementIds.has(parentWall)) {
        issues.push({
          level: 'error',
          message: `opening ${element.id} 的 parentWall 不存在: ${parentWall}`,
          elementId: element.id
        })
      }
    }
  }

  for (const component of blueprint.geometry.components || []) {
    const materialFields = [
      'material',
      'frameMaterial',
      'leafMaterial',
      'glassMaterial',
      'supportMaterial',
      'railingMaterial',
      'capMaterial',
    ] as const
    for (const field of materialFields) {
      const material = (component as unknown as Record<string, unknown>)[field]
      if (typeof material === 'string' && !materialNames.has(material)) {
        issues.push({
          level: 'warning',
          message: `组合构件 ${component.id} 引用了不存在的材质: ${material}`,
          elementId: component.id
        })
      }
    }
  }

  return issues
}
