import type { MaterialDef, MaterialParams, MeshData } from '../types';

/** 烘焙效果层到基础材质参数 */
function bakeEffects(base: MaterialDef): MaterialParams {
  let bc = [...base.baseColor] as [number, number, number];
  let r = base.roughness;
  let m = base.metallic;
  const emissive = base.emissive ? [...base.emissive] as [number, number, number] : [0, 0, 0];

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

      if (fx.type === 'moss') {
        // 苔藓：mossColor 按 coverage 混合进 baseColor（均匀近似)
        const c = fx.coverage || 0;
        bc = [
          bc[0] * (1 - c) + fx.mossColor[0] * c,
          bc[1] * (1 - c) + fx.mossColor[1] * c,
          bc[2] * (1 - c) + fx.mossColor[2] * c,
        ];
        r = Math.min(1, r + c * 0.2);
      }

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
  };
}

export function applyMaterials(
  materials: Record<string, MaterialDef>,
  meshes: MeshData[]
): MaterialParams[] {
  return meshes.map(mesh => {
    const mat = materials[mesh.materialRef] || defaultMaterial();
    return bakeEffects(mat);
  });
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