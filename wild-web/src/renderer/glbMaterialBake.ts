import * as THREE from 'three'

export interface GlbMaterialBakeItem {
  mesh: THREE.Mesh<THREE.BufferGeometry, THREE.MeshStandardMaterial>
  source: THREE.MeshStandardMaterial
  worldMatrix: THREE.Matrix4
  tint?: THREE.Color
}

export function canBakeGlbMaterial(material: THREE.Material): material is THREE.MeshStandardMaterial {
  return material instanceof THREE.MeshStandardMaterial && !!(
    material.userData.wildDefaultSurface || material.userData.wildProcedural
    || material.userData.wildEnvironmentSurface || material.userData.wildWaterSurface
  )
}

interface AtlasTriangle {
  offset: number
  geometryUv: THREE.BufferAttribute
  vertex: number
  base: number
  width: number
  height: number
  thirdX: number
}

const PADDING = 3

/** 复用原材质的 Shader，在独立 UV 图集中采样颜色、ORM 和切线法线。 */
export function bakeGlbMaterials(items: GlbMaterialBakeItem[], renderer: THREE.WebGLRenderer) {
  const textures = new Set<THREE.Texture>()
  const geometries = new Set<THREE.BufferGeometry>()
  const materials = new Set<THREE.Material>()
  const dispose = () => {
    textures.forEach(texture => texture.dispose())
    geometries.forEach(geometry => geometry.dispose())
    materials.forEach(material => material.dispose())
  }
  const groups = new Map<THREE.MeshStandardMaterial, GlbMaterialBakeItem[]>()
  for (const item of items) {
    const group = groups.get(item.source) || []
    group.push(item)
    groups.set(item.source, group)
  }
  const failures: string[] = []
  let count = 0
  for (const [source, group] of groups) {
    const previous = group.map(item => ({ mesh: item.mesh, geometry: item.mesh.geometry, material: item.mesh.material }))
    try {
      bakeGroup(source, group)
      count++
    } catch (error) {
      // 烘焙会改写快照的 UV；失败时连同材质一起还原，继续交付基础 PBR。
      for (const item of previous) {
        item.mesh.geometry = item.geometry
        item.mesh.material = item.material
      }
      failures.push(`${source.name || source.type}：${error instanceof Error ? error.message : '烘焙失败'}`)
    }
  }
  return { count, failures, dispose }

  function bakeGroup(source: THREE.MeshStandardMaterial, group: GlbMaterialBakeItem[]) {
    const count = group.reduce((sum, item) => sum + (item.mesh.geometry.index?.count
      ?? item.mesh.geometry.getAttribute('position').count), 0)
    const positions = new Float32Array(count * 3)
    const normals = new Float32Array(count * 3)
    const colors = new Float32Array(count * 3).fill(1)
    const sourceUvs = new Float32Array(count * 2)
    const atlasUvs = new Float32Array(count * 2)
    const triangles: AtlasTriangle[] = []
    const point = new THREE.Vector3()
    const normal = new THREE.Vector3()
    const points = [new THREE.Vector3(), new THREE.Vector3(), new THREE.Vector3()]
    const edge = new THREE.Vector3()
    const side = new THREE.Vector3()
    let offset = 0
    for (const item of group) {
      const geometry = item.mesh.geometry.index ? item.mesh.geometry.toNonIndexed() : item.mesh.geometry.clone()
      geometries.add(geometry)
      item.mesh.geometry = geometry
      if (!geometry.getAttribute('normal')) geometry.computeVertexNormals()
      const position = geometry.getAttribute('position')
      const vertexNormal = geometry.getAttribute('normal')
      const uv = geometry.getAttribute('uv')
      const color = geometry.getAttribute('color')
      const normalMatrix = new THREE.Matrix3().getNormalMatrix(item.worldMatrix)
      const geometryUv = new THREE.BufferAttribute(new Float32Array(position.count * 2), 2)
      for (let i = 0; i < position.count; i++) {
        point.fromBufferAttribute(position, i).applyMatrix4(item.worldMatrix).toArray(positions, (offset + i) * 3)
        normal.fromBufferAttribute(vertexNormal, i).applyNormalMatrix(normalMatrix).toArray(normals, (offset + i) * 3)
        if (uv) {
          sourceUvs[(offset + i) * 2] = uv.getX(i)
          sourceUvs[(offset + i) * 2 + 1] = uv.getY(i)
        }
        if (color && source.vertexColors) {
          colors.set([color.getX(i), color.getY(i), color.getZ(i)], (offset + i) * 3)
        }
        if (item.tint) {
          colors[(offset + i) * 3]! *= item.tint.r
          colors[(offset + i) * 3 + 1]! *= item.tint.g
          colors[(offset + i) * 3 + 2]! *= item.tint.b
        }
      }
      for (let i = 0; i + 2 < position.count; i += 3) {
        points.forEach((p, corner) => p.fromArray(positions, (offset + i + corner) * 3))
        const lengths = points.map((p, corner) => p.distanceToSquared(points[(corner + 1) % 3]!))
        const base = lengths.indexOf(Math.max(...lengths))
        edge.subVectors(points[(base + 1) % 3]!, points[base]!)
        const width = Math.max(edge.length(), 1e-6)
        side.subVectors(points[(base + 2) % 3]!, points[base]!)
        const thirdX = side.dot(edge) / width
        const height = Math.sqrt(Math.max(0, side.lengthSq() - thirdX * thirdX))
        triangles.push({ offset: offset + i, geometryUv, vertex: i, base, width, height, thirdX })
      }
      geometry.setAttribute('uv', geometryUv)
      geometry.deleteAttribute('uv1')
      geometry.deleteAttribute('uv2')
      geometry.deleteAttribute('color') // 顶点色已经乘入烘焙颜色。
      geometry.deleteAttribute('tangent') // 新图集使用其自身的切线基。
      offset += position.count
    }

    const maxSize = Math.min(2048, renderer.capabilities.maxTextureSize)
    let size = Math.min(128, maxSize)
    const sorted = [...triangles].sort((a, b) => b.height - a.height)
    function pack(density: number, write = false): boolean {
      let x = 0, y = 0, rowHeight = 0
      for (const triangle of sorted) {
        const width = Math.max(1, Math.ceil(triangle.width * density)) + PADDING * 2
        const height = Math.max(1, Math.ceil(triangle.height * density)) + PADDING * 2
        if (width > size || height > size) return false
        if (x + width > size) { x = 0; y += rowHeight; rowHeight = 0 }
        if (y + height > size) return false
        if (write) {
          const coordinates = [[0, 0], [triangle.width, 0], [triangle.thirdX, triangle.height]]
          coordinates.forEach(([u, v], corner) => {
            const index = (triangle.base + corner) % 3
            const s = (x + PADDING + u! * density) / size
            const t = (y + PADDING + v! * density) / size
            atlasUvs.set([s, t], (triangle.offset + index) * 2)
            triangle.geometryUv.setXY(triangle.vertex + index, s, t)
          })
        }
        x += width
        rowHeight = Math.max(rowHeight, height)
      }
      return true
    }
    while (size < maxSize && !pack(128)) size = Math.min(size * 2, maxSize)
    if (!pack(0)) throw new Error('材质表面过于复杂，超过 GLB 贴图烘焙容量')
    let low = 0, high = 128
    for (let i = 0; i < 18; i++) {
      const middle = (low + high) / 2
      if (pack(middle)) low = middle
      else high = middle
    }
    pack(low, true)
    const geometry = new THREE.BufferGeometry()
    geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3))
    geometry.setAttribute('normal', new THREE.BufferAttribute(normals, 3))
    geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3))
    geometry.setAttribute('uv', new THREE.BufferAttribute(sourceUvs, 2))
    geometry.setAttribute('wildBakeUv', new THREE.BufferAttribute(atlasUvs, 2))
    // 现有 PBR 通道可能选择 uv1/uv2；烘焙时保留它们原先共用 UV 的语义。
    geometry.setAttribute('uv1', geometry.getAttribute('uv'))
    geometry.setAttribute('uv2', geometry.getAttribute('uv'))
    const channel = { value: 0 }
    const cleanSource = Object.create(source) as THREE.MeshStandardMaterial
    cleanSource.userData = {}
    const material = source instanceof THREE.MeshPhysicalMaterial
      ? new THREE.MeshPhysicalMaterial().copy(cleanSource as THREE.MeshPhysicalMaterial)
      : new THREE.MeshStandardMaterial().copy(cleanSource)
    material.side = THREE.DoubleSide
    material.vertexColors = source.vertexColors || group.some(item => !!item.tint)
    material.transparent = false
    material.blending = THREE.NoBlending
    material.depthTest = false
    material.depthWrite = false
    material.alphaTest = 0
    material.clippingPlanes = []
    material.toneMapped = false
    material.onBeforeCompile = (shader, gl) => {
      source.onBeforeCompile(shader, gl)
      shader.uniforms.wildBakeChannel = channel
      shader.vertexShader = shader.vertexShader
        .replace('#include <common>', '#include <common>\nattribute vec2 wildBakeUv; varying vec2 vWildBakeUv;')
        .replace('#include <project_vertex>', '#include <project_vertex>\nvWildBakeUv = wildBakeUv; gl_Position = vec4(wildBakeUv * 2.0 - 1.0, 0.0, 1.0);')
      shader.fragmentShader = shader.fragmentShader
        .replace('#include <common>', '#include <common>\nuniform int wildBakeChannel; varying vec2 vWildBakeUv;')
        .replace('#include <emissivemap_fragment>', `#include <emissivemap_fragment>
if (wildBakeChannel == 0) {
  gl_FragColor = vec4(sRGBTransferOETF(vec4(diffuseColor.rgb, 1.0)).rgb, diffuseColor.a / max(opacity, 0.00001));
} else if (wildBakeChannel == 1) {
  float ao = 1.0;
  #ifdef USE_AOMAP
    ao = (texture2D(aoMap, vAoMapUv).r - 1.0) * aoMapIntensity + 1.0;
  #endif
  gl_FragColor = vec4(ao, roughnessFactor, metalnessFactor, 1.0);
} else {
  vec3 q0 = dFdx(-vViewPosition), q1 = dFdy(-vViewPosition);
  vec2 st0 = dFdx(vWildBakeUv), st1 = dFdy(vWildBakeUv);
  vec3 N = nonPerturbedNormal;
  vec3 T = cross(q1, N) * st0.x + cross(N, q0) * st1.x;
  vec3 B = cross(q1, N) * st0.y + cross(N, q0) * st1.y;
  float scale = inversesqrt(max(max(dot(T,T), dot(B,B)), 1e-20));
  T *= scale; B *= scale;
  float determinant = dot(T, cross(B, N));
  vec3 tangentNormal = abs(determinant) > 1e-8
    ? normalize(vec3(dot(cross(B,N), normal), dot(cross(N,T), normal), dot(cross(T,B), normal)) / determinant)
    : vec3(0.0, 0.0, 1.0);
  gl_FragColor = vec4(tangentNormal * 0.5 + 0.5, 1.0);
}
return;`)
    }
    material.customProgramCacheKey = () => `wild-glb-bake-v1:${source.customProgramCacheKey()}`
    const scene = new THREE.Scene()
    const mesh = new THREE.Mesh(geometry, material)
    mesh.frustumCulled = false
    scene.add(mesh)
    const camera = new THREE.OrthographicCamera(-1, 1, 1, -1, .1, 10)
    const target = new THREE.WebGLRenderTarget(size, size, { depthBuffer: false, stencilBuffer: false })
    const previous = {
      target: renderer.getRenderTarget(), cubeFace: renderer.getActiveCubeFace(),
      mipmapLevel: renderer.getActiveMipmapLevel(),
      color: renderer.getClearColor(new THREE.Color()), alpha: renderer.getClearAlpha(),
      clipping: renderer.localClippingEnabled, planes: renderer.clippingPlanes,
      shadows: renderer.shadowMap.enabled, autoClear: renderer.autoClear,
    }
    const pixels = [new Uint8Array(size * size * 4), new Uint8Array(size * size * 4), new Uint8Array(size * size * 4)]
    try {
      renderer.localClippingEnabled = false
      renderer.clippingPlanes = []
      renderer.shadowMap.enabled = false
      renderer.autoClear = true
      renderer.setClearColor(0, 0)
      // RenderTarget 自带物理像素 viewport；setViewport 会再乘视口 DPR，导致图集裁切错位。
      renderer.setRenderTarget(target)
      for (let i = 0; i < pixels.length; i++) {
        channel.value = i
        material.needsUpdate = true
        renderer.render(scene, camera)
        renderer.readRenderTargetPixels(target, 0, 0, size, size, pixels[i]!)
      }
    } finally {
      renderer.setRenderTarget(previous.target, previous.cubeFace, previous.mipmapLevel)
      renderer.setClearColor(previous.color, previous.alpha)
      renderer.localClippingEnabled = previous.clipping
      renderer.clippingPlanes = previous.planes
      renderer.shadowMap.enabled = previous.shadows
      renderer.autoClear = previous.autoClear
      target.dispose()
      material.dispose()
      geometry.dispose()
    }
    dilateAtlas(pixels, size)
    const maps = pixels.map((data, index) => {
      const canvas = document.createElement('canvas')
      canvas.width = canvas.height = size
      canvas.getContext('2d')!.putImageData(new ImageData(new Uint8ClampedArray(data), size, size), 0, 0)
      const texture = new THREE.CanvasTexture(canvas)
      texture.name = `${source.name || 'surface'}-${['color', 'orm', 'normal'][index]}`
      texture.flipY = false
      texture.colorSpace = index === 0 ? THREE.SRGBColorSpace : THREE.NoColorSpace
      textures.add(texture)
      return texture
    })
    const baked = group[0]!.mesh.material.clone()
    materials.add(baked)
    baked.color.set(0xffffff)
    baked.map = maps[0]!
    baked.alphaMap = null
    baked.vertexColors = false
    baked.roughness = 1
    baked.metalness = 1
    baked.roughnessMap = baked.metalnessMap = baked.aoMap = maps[1]!
    baked.aoMapIntensity = 1
    baked.normalMap = maps[2]!
    baked.normalScale.set(1, 1)
    baked.normalMapType = THREE.TangentSpaceNormalMap
    baked.bumpMap = null
    for (const item of group) item.mesh.material = baked
  }
}

/** 用最近的有效像素填满图集空白，避免低层级 mipmap 混入黑色和无效法线。 */
function dilateAtlas(maps: Uint8Array[], size: number) {
  const filled = new Uint8Array(size * size)
  const queue = new Uint32Array(size * size)
  let end = 0
  for (let i = 0; i < filled.length; i++) {
    if (maps[2]![i * 4 + 3]) { filled[i] = 1; queue[end++] = i }
  }
  if (!end) throw new Error('材质贴图烘焙没有产生有效像素')
  for (let start = 0; start < end; start++) {
    const pixel = queue[start]!
    for (const next of [pixel % size ? pixel - 1 : -1, pixel % size < size - 1 ? pixel + 1 : -1, pixel - size, pixel + size]) {
      if (next < 0 || next >= filled.length || filled[next]) continue
      filled[next] = 1
      for (const map of maps) map.copyWithin(next * 4, pixel * 4, pixel * 4 + 4)
      queue[end++] = next
    }
  }
}
