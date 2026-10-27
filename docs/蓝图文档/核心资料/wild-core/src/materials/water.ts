/** 兼容现有 WILD 水材质约定，不根据构件 ID 猜测水体。 */
export function isWaterMaterial(params: { materialClass?: string; ior?: number }, name: string): boolean {
  return (params.materialClass === 'glass' && Math.abs((params.ior ?? 1.5) - 1.333) < 0.005)
    || /^(water|water_surface|pool_water|pond_water|水|水面|池水|泳池水)$/i.test(name)
}
