import type { MaterialDef, MaterialParams, MeshData } from '../types';

/** 烘焙效果层到基础材质参数 */
function bakeEffects(base: MaterialDef): MaterialParams {
  let bc = normalizeColor(base.baseColor, [0.5, 0.5, 0.5]);
  let r = normalizeUnit(base.roughness, 0.8);
  const m = normalizeUnit(base.metallic, 0);
  const emissive = normalizeColor(base.emissive, [0, 0, 0]);

  if (base.effects) {
    for (const fx of base.effects) {
      if (fx.type === 'weathering') {
        // 蒙尘：dustColor 按 dustOpacity 混合进 baseColor
        const d = fx.dustOpacity || 0;
        bc = [
          bc[0] * (1 - d) + fx.dustColor[0] * d,
          bc[1] * (1 - d) + fx.dustColor[1] * d,
          bc[2] * (1 - d) + fx.dustColor[2] * d,
        ];
        // 褪色：向灰度偏移
        const f = fx.colorFade || 0;
        const gray = (bc[0] + bc[1] + bc[2]) / 3;
        bc = [
          bc[0] * (1 - f) + gray * f,
          bc[1] * (1 - f) + gray * f,
          bc[2] * (1 - f) + gray * f,
        ];
        // 裂纹：增加粗糙度
        r = Math.min(1, r + (fx.crackIntensity || 0) * 0.3);
      }

      // moss 的分布依赖世界高度/噪声，只在逐顶点阶段处理，避免重复混色。
      if (fx.type === 'moss') r = Math.min(1, r + (fx.coverage || 0) * 0.2);

      if (fx.type === 'edgeWear') {
        // 边缘磨损：wearColor 提高亮度（全局近似，真实需几何边缘检测）
        const w = fx.intensity || 0;
        bc = [
          bc[0] * (1 - w * 0.3) + fx.wearColor[0] * w * 0.3,
          bc[1] * (1 - w * 0.3) + fx.wearColor[1] * w * 0.3,
          bc[2] * (1 - w * 0.3) + fx.wearColor[2] * w * 0.3,
        ];
      }
    }
  }

  return {
    baseColor: bc,
    roughness: r,
    metallic: m,
    albedo: base.albedo,
    emissive: emissive as [number, number, number],
    opacity: base.opacity ?? 1.0,
    effects: base.effects || [],
    lightingCondition: base.lightingCondition,
    embeddedImage: base.embeddedImage,
    textures: base.textures,
    normalScale: base.normalScale,
    uvScale: base.uvScale,
  };
}

export function applyMaterials(
  materials: Record<string, MaterialDef>,
  meshes: MeshData[]
): MaterialParams[] {
  const normalizedMaterials = new Map<string, MaterialDef>();

  return meshes.map(mesh => {
    let mat = normalizedMaterials.get(mesh.materialRef);
    if (!mat) {
      const source = materials[mesh.materialRef];
      if (source && !isColor(source.baseColor)) {
        console.warn(
          `WILD 材质 "${mesh.materialRef}" 的 baseColor 非法，已使用默认颜色`,
        );
      }
      mat = normalizeMaterial(source);
      normalizedMaterials.set(mesh.materialRef, mat);
    }
    return bakeEffects(mat);
  });
}

function normalizeMaterial(value: MaterialDef | undefined): MaterialDef {
  const fallback = defaultMaterial();
  if (!value || typeof value !== 'object') return fallback;

  return {
    ...fallback,
    ...value,
    baseColor: normalizeColor(value.baseColor, fallback.baseColor),
    roughness: normalizeUnit(value.roughness, fallback.roughness),
    metallic: normalizeUnit(value.metallic, fallback.metallic),
    albedo: normalizeUnit(value.albedo, fallback.albedo),
    emissive: value.emissive
      ? normalizeColor(value.emissive, [0, 0, 0])
      : undefined,
    opacity: normalizeUnit(value.opacity, 1),
    effects: Array.isArray(value.effects) ? value.effects : [],
  };
}

function normalizeColor(
  value: unknown,
  fallback: [number, number, number],
): [number, number, number] {
  return isColor(value) ? [...value] : [...fallback];
}

function isColor(value: unknown): value is [number, number, number] {
  return Array.isArray(value)
    && value.length === 3
    && value.every(
      channel => typeof channel === 'number'
        && Number.isFinite(channel)
        && channel >= 0
        && channel <= 1,
    );
}

function normalizeUnit(value: unknown, fallback: number): number {
  return typeof value === 'number'
    && Number.isFinite(value)
    && value >= 0
    && value <= 1
    ? value
    : fallback;
}

function defaultMaterial(): MaterialDef {
  return {
    baseColor: [0.5, 0.5, 0.5],
    roughness: 0.8,
    metallic: 0.0,
    albedo: 1.0,
    lightingCondition: 'D65_noon'
  };
}
