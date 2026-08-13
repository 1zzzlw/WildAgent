import type {
  MaterialDef,
  MaterialParams,
  MeshData,
  PBRTextureSetAsset,
} from '../types';

/** 烘焙效果层到基础材质参数 */
function bakeEffects(
  base: MaterialDef,
  assets: Record<string, PBRTextureSetAsset>,
): MaterialParams {
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
    textures: base.textureSet
      ? assets[base.textureSet]?.maps || base.textures
      : base.textures,
    normalScale: base.normalScale,
    uvScale: base.uvScale,
    materialClass: base.materialClass,
    side: base.side,
    transmission: base.transmission,
    ior: base.ior,
    thickness: base.thickness,
    attenuationColor: base.attenuationColor,
    attenuationDistance: base.attenuationDistance,
    clearcoat: base.clearcoat,
    clearcoatRoughness: base.clearcoatRoughness,
    sheen: base.sheen,
    sheenColor: base.sheenColor,
    emissiveIntensity: base.emissiveIntensity,
    procedural: base.procedural
      ? JSON.parse(JSON.stringify(base.procedural))
      : undefined,
  };
}

export function applyMaterials(
  materials: Record<string, MaterialDef>,
  assets: Record<string, PBRTextureSetAsset>,
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
    return bakeEffects(mat, assets);
  });
}

function normalizeMaterial(value: MaterialDef | undefined): MaterialDef {
  const fallback = defaultMaterial();
  if (!value || typeof value !== 'object') return fallback;
  const baseColor = normalizeColor(value.baseColor, fallback.baseColor);

  return {
    ...fallback,
    ...value,
    baseColor,
    roughness: normalizeUnit(value.roughness, fallback.roughness),
    metallic: normalizeUnit(value.metallic, fallback.metallic),
    albedo: normalizeUnit(value.albedo, fallback.albedo),
    emissive: value.emissive
      ? normalizeColor(value.emissive, [0, 0, 0])
      : undefined,
    opacity: normalizeUnit(value.opacity, 1),
    transmission: normalizeUnit(value.transmission, 0),
    clearcoat: normalizeUnit(value.clearcoat, 0),
    clearcoatRoughness: normalizeUnit(value.clearcoatRoughness, 0),
    sheen: normalizeUnit(value.sheen, 0),
    ior: normalizeRange(value.ior, 1, 2.333, 1.5),
    thickness: normalizeNonNegative(value.thickness, 0),
    attenuationDistance: normalizePositive(value.attenuationDistance),
    attenuationColor: value.attenuationColor
      ? normalizeColor(value.attenuationColor, [1, 1, 1])
      : undefined,
    sheenColor: value.sheenColor
      ? normalizeColor(value.sheenColor, [1, 1, 1])
      : undefined,
    emissiveIntensity: normalizeNonNegative(value.emissiveIntensity, 1),
    effects: Array.isArray(value.effects) ? value.effects : [],
    procedural: normalizeProcedural(value.procedural, baseColor),
  };
}

function normalizeProcedural(
  value: MaterialDef['procedural'],
  baseColor: [number, number, number],
): MaterialDef['procedural'] {
  if (!value || value.type !== 'brick') return undefined;
  const brickWidth = normalizeRange(value.brickSize?.[0], 0.04, 2, 0.24);
  const brickHeight = normalizeRange(value.brickSize?.[1], 0.02, 1, 0.065);
  const maxMortarWidth = Math.max(0.002, Math.min(0.03, Math.min(brickWidth, brickHeight) * 0.49));
  const weathering = value.weathering || {};
  return {
    type: 'brick',
    seed: normalizeInteger(value.seed, 0, 2_147_483_647, 1),
    brickSize: [brickWidth, brickHeight],
    mortarWidth: normalizeRange(value.mortarWidth, 0.002, maxMortarWidth, Math.min(0.01, maxMortarWidth)),
    mortarDepth: normalizeRange(value.mortarDepth, 0, 0.02, 0.006),
    bond: value.bond === 'stack' ? 'stack' : 'running',
    secondaryColor: value.secondaryColor
      ? normalizeColor(value.secondaryColor, deriveSecondaryColor(baseColor))
      : deriveSecondaryColor(baseColor),
    colorVariation: normalizeUnit(value.colorVariation, 0.12),
    roughnessVariation: normalizeUnit(value.roughnessVariation, 0.12),
    edgeWear: normalizeUnit(value.edgeWear, 0.05),
    weathering: {
      amount: normalizeUnit(weathering.amount, 0),
      scale: normalizeRange(weathering.scale, 0.1, 100, 1.8),
      efflorescence: normalizeUnit(weathering.efflorescence, 0),
      verticalStreaks: normalizeUnit(weathering.verticalStreaks, 0),
      baseDampness: normalizeUnit(weathering.baseDampness, 0),
    },
  };
}

function deriveSecondaryColor(baseColor: [number, number, number]): [number, number, number] {
  return [
    Math.min(1, baseColor[0] * 1.18 + 0.025),
    Math.min(1, baseColor[1] * 1.12 + 0.012),
    Math.min(1, baseColor[2] * 0.96 + 0.008),
  ];
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

function normalizeRange(value: unknown, min: number, max: number, fallback: number): number {
  return typeof value === 'number' && Number.isFinite(value)
    ? Math.min(max, Math.max(min, value))
    : fallback;
}

function normalizeInteger(value: unknown, min: number, max: number, fallback: number): number {
  return typeof value === 'number' && Number.isFinite(value) && Number.isInteger(value)
    ? Math.min(max, Math.max(min, value))
    : fallback;
}

function normalizeNonNegative(value: unknown, fallback: number): number {
  return typeof value === 'number' && Number.isFinite(value) && value >= 0
    ? value
    : fallback;
}

function normalizePositive(value: unknown): number | undefined {
  return typeof value === 'number' && Number.isFinite(value) && value > 0
    ? value
    : undefined;
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
