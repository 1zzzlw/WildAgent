import * as THREE from 'three'

/** 圆形世界外围柔和消失；保留原材质的天气、受光和阴影 shader。 */
export function softenGroundEdge(material: THREE.Material): void {
  const compile = material.onBeforeCompile.bind(material)
  const key = material.customProgramCacheKey.bind(material)
  const previousKey = key()
  material.transparent = true
  material.depthWrite = false
  material.onBeforeCompile = (shader, renderer) => {
    compile(shader, renderer)
    shader.vertexShader = 'varying vec2 vWorldDiskUv;\n' + shader.vertexShader
    shader.vertexShader = shader.vertexShader.replace('#include <begin_vertex>', '#include <begin_vertex>\nvWorldDiskUv = uv;')
    shader.fragmentShader = 'varying vec2 vWorldDiskUv;\n' + shader.fragmentShader
    // ShadowMaterial 没有 dithering_fragment；在最后一个右花括号前改写透明度。
    const end = shader.fragmentShader.lastIndexOf('}')
    shader.fragmentShader = shader.fragmentShader.slice(0,end)
      + 'gl_FragColor.a *= 1.0 - smoothstep(0.82, 1.0, length(vWorldDiskUv - 0.5) * 2.0);\n'
      + shader.fragmentShader.slice(end)
  }
  material.customProgramCacheKey = () => previousKey + ':world-disk-edge-v1'
  material.needsUpdate = true
}

/** 保留编辑器笛卡尔网格，裁到圆内，并淡出外围线条。 */
export function roundGroundGrid(grid: THREE.GridHelper, radius: number): void {
  const positions = grid.geometry.getAttribute('position')
  for (let i=0; i<positions.count; i+=2) {
    const alongX = positions.getZ(i) === positions.getZ(i+1)
    const distance = alongX ? positions.getZ(i) : positions.getX(i)
    const limit = Math.sqrt(Math.max(0, radius*radius-distance*distance))
    for (const index of [i,i+1]) {
      if (alongX) positions.setX(index, Math.sign(positions.getX(index)) * limit)
      else positions.setZ(index, Math.sign(positions.getZ(index)) * limit)
    }
  }
  // 片元淡出，避免只有端点颜色变淡导致整条网格线一起消失。
  const materials: THREE.Material[] = Array.isArray(grid.material) ? grid.material : [grid.material]
  for (const material of materials) {
    material.transparent = true
    material.depthWrite = false
    material.customProgramCacheKey = () => `world-circular-grid:${radius}`
    material.onBeforeCompile = shader => {
      shader.vertexShader = 'varying vec2 vGridDisk;\n' + shader.vertexShader
      shader.vertexShader = shader.vertexShader.replace('#include <begin_vertex>', `#include <begin_vertex>\nvGridDisk = position.xz / ${radius.toFixed(4)};`)
      shader.fragmentShader = 'varying vec2 vGridDisk;\n' + shader.fragmentShader
      shader.fragmentShader = shader.fragmentShader.replace('#include <dithering_fragment>', 'gl_FragColor.a *= 1.0 - smoothstep(0.72, 1.0, length(vGridDisk));\n#include <dithering_fragment>')
    }
  }
  positions.needsUpdate = true
  grid.geometry.computeBoundingSphere()
}
