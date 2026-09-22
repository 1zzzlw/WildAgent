/**
 * wild-core — WILD 蓝图确定性几何重建引擎
 *
 * 本文件是包的唯一公开入口。完整链路：
 *
 *   .wild 蓝图
 *     -> compileBlueprintComponents()   组合构件（门窗/阳台/檐口…）展开为基础元素
 *     -> parseBlueprint()               结构校验 + 版本归一化
 *     -> reconstructEntity()            确定性重建 MeshData 几何 + 材质参数
 *     -> 交给调用方的渲染适配层（不属于本包职责）
 *
 * 约束：
 * - 不依赖 Vue、Three.js、Agent，也没有任何 npm 运行时依赖。
 * - 唯一外部输入是包内的 schema.json（由 primitive/schema-validator.ts import）。
 * - 需要 WILD 语言的全量类型定义时，从 `wild-core/types` 导入。
 */

// ── 组合构件编译器：geometry.components -> geometry.elements ──────────
export * from './compiler/index'

// ── 原语引擎：elements -> MeshData ────────────────────────────────────
export * from './primitive/index'

// ── 材质契约与材质包解析 ──────────────────────────────────────────────
export * from './materials/index'

// ── 世界（多体量场景）契约 ────────────────────────────────────────────
export * from './world/index'
