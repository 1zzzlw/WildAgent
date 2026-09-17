import * as THREE from 'three'
import type { RenderMaterialDescriptor, SurfaceFamily } from '../../wild-core/src/materials'
import { PROCEDURAL_NOISE_GLSL } from '../proceduralMaterials/noise.glsl'
import {
  getWorldEnvironmentUniforms,
  getWorldRenderingUniforms,
} from '../worldEnvironmentRuntime'

const SHADER_VERSION = 'default-surface-v2'

interface MutableShader {
  uniforms: Record<string, { value: unknown }>
  vertexShader: string
  fragmentShader: string
}

interface DefaultSurfaceParams {
  family: SurfaceFamily
  familyCode: number
  seed: number
  scale: number
  colorVariation: number
  roughnessVariation: number
  relief: number
  reliefRoughness: number
  courseCells: [number, number]
  grainFrequency: number
  wetnessAbsorption: number
  wetnessDarkening: number
  wetnessRoughnessReduction: number
  wetnessNormalFlattening: number
  rainStreakStrength: number
  snowAdhesion: number
  dustAdhesion: number
}

/**
 * 表面族的着色器编码。mineral 与 masonry 的图案完全不同（灰泥细粒 vs 错缝砖瓦），
 * 因此必须分开编码；masonry 追加为 5，不改动既有 0-4 的含义。
 */
const FAMILY_CODE: Record<SurfaceFamily, number> = {
  neutral: 0,
  mineral: 1,
  wood: 2,
  metal: 3,
  glass: 4,
  masonry: 5,
}

const MASONRY_FAMILY_CODE = FAMILY_CODE.masonry

/**
 * 每个族的凹凸参数。relief 为高度场振幅（米），直接等于表面坡度（米/米）的上限量级，
 * 因此与像素密度无关；courseCells / grainFrequency 都是米制频率（每米周期数）。
 */
const RELIEF_PRESETS: Record<SurfaceFamily, {
  relief: number
  reliefRoughness: number
  courseCells: [number, number]
  grainFrequency: number
}> = {
  masonry: { relief: 0.009, reliefRoughness: 0.3, courseCells: [3.3, 6.6], grainFrequency: 6 },
  mineral: { relief: 0.012, reliefRoughness: 0.22, courseCells: [3.3, 6.6], grainFrequency: 12 },
  wood: { relief: 0.010, reliefRoughness: 0.18, courseCells: [3.3, 6.6], grainFrequency: 16 },
  metal: { relief: 0.004, reliefRoughness: 0.14, courseCells: [3.3, 6.6], grainFrequency: 20 },
  neutral: { relief: 0.010, reliefRoughness: 0.2, courseCells: [3.3, 6.6], grainFrequency: 12 },
  glass: { relief: 0, reliefRoughness: 0, courseCells: [3.3, 6.6], grainFrequency: 12 },
}

/**
 * 默认世界的低成本表面层。它只补充克制的微变化，不替代专用砖 Shader 或 PBR 贴图。
 * 所有表面族共用同一 GPU Program，差异仅通过 uniform 表达。
 */
export function applyDefaultSurfaceMaterial(
  material: THREE.MeshStandardMaterial,
  descriptor: RenderMaterialDescriptor,
  materialSeed: string,
): void {
  if (descriptor.family === 'glass' || descriptor.quality === 'fallback') return
  const params = createDefaultSurfaceParams(descriptor, materialSeed)
  material.userData.wildDefaultSurface = params
  material.userData.wildDefaultSurfaceShaderVersion = SHADER_VERSION
  material.customProgramCacheKey = () => `wild-surface:${SHADER_VERSION}`
  material.onBeforeCompile = shader => installDefaultSurfaceShader(shader as MutableShader, params)
  material.needsUpdate = true
}

export function installDefaultSurfaceShader(
  shader: MutableShader,
  params: DefaultSurfaceParams,
): void {
  const environment = getWorldEnvironmentUniforms()
  const rendering = getWorldRenderingUniforms()
  Object.assign(shader.uniforms, {
    wildSurfaceFamily: { value: params.familyCode },
    wildSurfaceSeed: { value: params.seed },
    wildSurfaceScale: { value: params.scale },
    wildSurfaceColorVariation: { value: params.colorVariation },
    wildSurfaceRoughnessVariation: { value: params.roughnessVariation },
    wildSurfaceRelief: { value: params.relief },
    wildSurfaceReliefRoughness: { value: params.reliefRoughness },
    wildSurfaceCourseCells: {
      value: new THREE.Vector2(params.courseCells[0], params.courseCells[1]),
    },
    wildSurfaceGrainFrequency: { value: params.grainFrequency },
    wildWorldWetness: environment.wetness,
    wildWorldRain: environment.rain,
    wildWorldSnow: environment.snow,
    wildWorldDust: environment.dust,
    wildSurfaceEnabled: rendering.surfaceEnabled,
    wildSurfaceQuality: rendering.surfaceQuality,
    wildWeatherEnabled: rendering.weatherEnabled,
    wildWeatherQuality: rendering.weatherQuality,
    wildWetnessAbsorption: { value: params.wetnessAbsorption },
    wildWetnessDarkening: { value: params.wetnessDarkening },
    wildWetnessRoughnessReduction: { value: params.wetnessRoughnessReduction },
    wildWetnessNormalFlattening: { value: params.wetnessNormalFlattening },
    wildRainStreakStrength: { value: params.rainStreakStrength },
    wildSnowAdhesion: { value: params.snowAdhesion },
    wildDustAdhesion: { value: params.dustAdhesion },
  })

  shader.vertexShader = shader.vertexShader
    .replace(
      '#include <common>',
      `#include <common>
varying vec2 vWildDefaultSurfaceUv;
varying vec3 vWildDefaultWorldNormal;
varying vec3 vWildDefaultWorldPosition;`,
    )
    .replace(
      '#include <uv_vertex>',
      '#include <uv_vertex>\nvWildDefaultSurfaceUv = uv;',
    )
    .replace(
      '#include <defaultnormal_vertex>',
      `#include <defaultnormal_vertex>
// defaultnormal_vertex 结束时 transformedNormal 已处于【视图空间】（且已折入 instanceMatrix）。
// 旧实现写的是 mat3(modelMatrix) * transformedNormal —— 视图空间量再乘模型矩阵属于空间混用，
// 相机一旋转、或物体带旋转/实例变换，"世界法线"就是错的。
// inverseTransformDirection 是 viewMatrix 旋转部分的逆转置，正好把它还原回世界空间
// （与下方 map_fragment 里处理 vNormal 的写法保持一致）。
// FLAT_SHADED 下 transformedNormal 未声明，回退到 objectNormal + normalMatrix。
#ifdef FLAT_SHADED
vWildDefaultWorldNormal = inverseTransformDirection(normalMatrix * objectNormal, viewMatrix);
#else
vWildDefaultWorldNormal = inverseTransformDirection(transformedNormal, viewMatrix);
#endif`,
    )
    .replace(
      '#include <worldpos_vertex>',
      `#include <worldpos_vertex>
vec4 wildDefaultWorldPosition = vec4(transformed, 1.0);
#ifdef USE_INSTANCING
  wildDefaultWorldPosition = instanceMatrix * wildDefaultWorldPosition;
#endif
vWildDefaultWorldPosition = (modelMatrix * wildDefaultWorldPosition).xyz;`,
    )

  shader.fragmentShader = shader.fragmentShader
    .replace(
      '#include <common>',
      `#include <common>
varying vec2 vWildDefaultSurfaceUv;
varying vec3 vWildDefaultWorldNormal;
varying vec3 vWildDefaultWorldPosition;
uniform int wildSurfaceFamily;
uniform float wildSurfaceSeed;
uniform float wildSurfaceScale;
uniform float wildSurfaceColorVariation;
uniform float wildSurfaceRoughnessVariation;
uniform float wildWorldWetness;
uniform float wildWorldRain;
uniform float wildWorldSnow;
uniform float wildWorldDust;
uniform float wildSurfaceEnabled;
uniform float wildSurfaceQuality;
uniform float wildWeatherEnabled;
uniform float wildWeatherQuality;
uniform float wildWetnessAbsorption;
uniform float wildWetnessDarkening;
uniform float wildWetnessRoughnessReduction;
uniform float wildWetnessNormalFlattening;
uniform float wildRainStreakStrength;
uniform float wildSnowAdhesion;
uniform float wildDustAdhesion;
uniform float wildSurfaceRelief;
uniform float wildSurfaceReliefRoughness;
uniform vec2 wildSurfaceCourseCells;
uniform float wildSurfaceGrainFrequency;
${PROCEDURAL_NOISE_GLSL}

/**
 * 按世界法线选主投影轴，把世界坐标折成「米制」平面坐标。
 * 这样凹凸尺度与 UV 约定无关：蓝图里既存在按米展开的 UV（屋面/外墙），
 * 也存在归一化 0..1 的 UV（楼板/门窗构件），用世界坐标才能同时正确。
 */
vec2 wildSurfaceMetricUv(vec3 worldPosition, vec3 worldNormal) {
  vec3 weight = abs(worldNormal);
  if (weight.x >= weight.y && weight.x >= weight.z) {
    return vec2(worldPosition.z, worldPosition.y);
  }
  if (weight.y >= weight.z) {
    return vec2(worldPosition.x, worldPosition.z);
  }
  return vec2(worldPosition.x, worldPosition.y);
}

/**
 * 错缝铺装（砖砌 / 瓦垄）：缝下沉、块面高低微差。
 * 返回约 [-1, 1] 的归一化高度，乘 wildSurfaceRelief 后即为米制高度。
 */
float wildSurfaceCourse(vec2 metric, vec2 cells, float seed) {
  vec2 grid = metric * cells;
  float row = floor(grid.y);
  grid.x += mod(row, 2.0) * 0.5;
  vec2 cell = floor(grid);
  vec2 local = fract(grid);
  vec2 edge = min(local, 1.0 - local);
  float face = smoothstep(0.0, 0.05, min(edge.x, edge.y));
  float block = wildHash21(cell + seed * 0.0017);
  // 叠一层沿进深方向的单调微倾，模拟瓦/砖一块压一块的叠压；否则块面完全平坦，
  // 只剩缝线，远看像贴上去的网格。
  return (face - 1.0) * 0.62 + (block - 0.5) * 0.3 * face + (local.y - 0.5) * 0.34 * face;
}

/** 细粒糙面：单倍频价值噪声，用于灰泥/混凝土/木/金属的微观起伏。 */
float wildSurfaceGrain(vec2 metric, float frequency, float seed) {
  return wildValueNoise(metric * frequency + vec2(seed * 0.0137, seed * 0.0071)) - 0.5;
}`,
    )
    .replace(
      '#include <map_fragment>',
      `#include <map_fragment>
float wildDefaultSurfaceAmount = wildSurfaceEnabled * wildSurfaceQuality;
float wildWeatherAmount = wildWeatherEnabled * wildWeatherQuality;
// 表面微变化噪声只在「表面层启用」或「雪/尘天气启用」时才计算；
// 关闭功能时通过 uniform 分支直接跳过，输出与原来完全一致。
float wildDefaultNoise = 0.5;
float wildDefaultDetail = 0.5;
float wildDefaultPattern = 0.0;
float wildSurfaceReliefUnit = 0.0;
if (wildDefaultSurfaceAmount > 0.0 || wildWeatherAmount * (wildWorldSnow + wildWorldDust) > 0.0) {
  vec2 wildDefaultUv = vWildDefaultSurfaceUv * wildSurfaceScale;
  wildDefaultNoise = wildFbm(wildDefaultUv + vec2(wildSurfaceSeed * 0.0017));
  wildDefaultDetail = wildFbm(wildDefaultUv * 3.1 + vec2(wildSurfaceSeed * 0.0041));
  wildDefaultPattern = (wildDefaultNoise - 0.5) * 0.72 + (wildDefaultDetail - 0.5) * 0.28;
  if (wildSurfaceFamily == 2) {
    float wildWoodWave = sin(
      wildDefaultUv.y * 7.0 + wildFbm(vec2(wildDefaultUv.x * 0.18, wildDefaultUv.y * 0.7)) * 5.0
    );
    wildDefaultPattern = wildDefaultPattern * 0.42 + wildWoodWave * 0.08;
  } else if (wildSurfaceFamily == 3) {
    float wildMetalBrush = sin(wildDefaultUv.y * 42.0 + wildDefaultDetail * 2.0) * 0.035;
    wildDefaultPattern = wildDefaultPattern * 0.2 + wildMetalBrush;
  }
#if __VERSION__ >= 300 && !defined( FLAT_SHADED )
  if (wildDefaultSurfaceAmount > 0.0 && wildSurfaceRelief > 0.0) {
    // 用视图空间 vNormal 还原世界法线：此处 normal 尚未由 normal_fragment_begin 声明。
    vec2 wildSurfaceMetric = wildSurfaceMetricUv(
      vWildDefaultWorldPosition,
      inverseTransformDirection(vNormal, viewMatrix)
    );
    // 一个特征小于约 1 像素时淡出，避免高频闪烁。粗/细两级按各自频率分别淡出，
    // 否则细粒会把整体提前淡掉（远处本该保留粗颗粒）。
    float wildSurfacePx = max(fwidth(wildSurfaceMetric.x), fwidth(wildSurfaceMetric.y));
    float wildSurfaceFreq = wildSurfaceFamily == ${MASONRY_FAMILY_CODE}
      ? max(wildSurfaceCourseCells.x, wildSurfaceCourseCells.y)
      : wildSurfaceGrainFrequency;
    float wildSurfaceMainFade = 1.0 - smoothstep(0.5, 1.0, wildSurfacePx * wildSurfaceFreq);
    float wildSurfaceFineFade = 1.0 - smoothstep(
      0.5, 1.0, wildSurfacePx * wildSurfaceFreq * 3.2
    );
    // 细粒糙面：两个倍频。单倍频要么近看呈团块，要么远处留不住。
    float wildSurfaceGrainNoise =
      wildSurfaceGrain(wildSurfaceMetric, wildSurfaceGrainFrequency, wildSurfaceSeed)
        * wildSurfaceMainFade
      + wildSurfaceGrain(
          wildSurfaceMetric, wildSurfaceGrainFrequency * 3.2, wildSurfaceSeed + 91.0
        ) * 0.45 * wildSurfaceFineFade;
    if (wildSurfaceFamily == ${MASONRY_FAMILY_CODE}) {
      // 砖缝/瓦垄为主体，另叠一层细粒与一层已算好的 fbm，避免块面过于"塑料平整"。
      wildSurfaceReliefUnit = wildSurfaceCourse(
        wildSurfaceMetric, wildSurfaceCourseCells, wildSurfaceSeed
      ) * wildSurfaceMainFade
        + wildSurfaceGrainNoise * 0.3
        + (wildDefaultDetail - 0.5) * 0.35;
    } else {
      // 灰泥/混凝土/木/金属：细粒为主 + 复用 wildDefaultDetail（其 fbm 已含 0.15m~4cm 多倍频），
      // 不额外增加 fbm 采样开销。
      wildSurfaceReliefUnit = wildSurfaceGrainNoise + (wildDefaultDetail - 0.5) * 0.8;
    }
  }
#endif
}
if (wildDefaultSurfaceAmount > 0.0) {
  diffuseColor.rgb *= 1.0 + wildDefaultPattern * wildSurfaceColorVariation * wildDefaultSurfaceAmount;
}
float wildMaterialWetness = wildWorldWetness * wildWetnessAbsorption * wildWeatherAmount;
diffuseColor.rgb *= 1.0 - wildMaterialWetness * wildWetnessDarkening;`,
    )
    .replace(
      '#include <color_fragment>',
      `#include <color_fragment>
vec3 wildDefaultNormal = normalize(vWildDefaultWorldNormal);
float wildVerticalMask = 1.0 - abs(wildDefaultNormal.y);
float wildRainMask = 0.0;
if (wildWeatherAmount * wildWorldRain * wildRainStreakStrength > 0.0) {
  float wildRainColumns = wildFbm(vec2(
    vWildDefaultWorldPosition.x * 1.7 + vWildDefaultWorldPosition.z * 0.9,
    vWildDefaultWorldPosition.y * 0.12 + wildSurfaceSeed * 0.002
  ));
  wildRainMask = smoothstep(0.56, 0.84, wildRainColumns)
    * wildVerticalMask * wildWorldRain * wildRainStreakStrength * wildWeatherAmount;
}
diffuseColor.rgb *= 1.0 - wildRainMask * 0.16;
float wildUpward = smoothstep(0.28, 0.82, wildDefaultNormal.y);
float wildSnowMask = wildUpward * wildWorldSnow * wildSnowAdhesion * wildWeatherAmount
  * smoothstep(0.2, 0.72, wildDefaultDetail);
diffuseColor.rgb = mix(diffuseColor.rgb, vec3(0.9, 0.93, 0.95), clamp(wildSnowMask, 0.0, 0.82));
float wildDustMask = wildUpward * wildWorldDust * wildDustAdhesion * wildWeatherAmount
  * smoothstep(0.18, 0.8, 1.0 - wildDefaultNoise);
diffuseColor.rgb = mix(diffuseColor.rgb, vec3(0.52, 0.44, 0.32), clamp(wildDustMask * 0.42, 0.0, 0.38));`,
    )
    .replace(
      '#include <roughnessmap_fragment>',
      `#include <roughnessmap_fragment>
roughnessFactor = clamp(
  roughnessFactor
    + wildDefaultPattern * wildSurfaceRoughnessVariation * wildDefaultSurfaceAmount
    - wildSurfaceReliefUnit * wildSurfaceReliefRoughness * wildDefaultSurfaceAmount
    - wildMaterialWetness * wildWetnessRoughnessReduction,
  0.04,
  1.0
);`,
    )
    .replace(
      '#include <normal_fragment_maps>',
      `vec3 wildDefaultBaseNormal = normal;
#include <normal_fragment_maps>
normal = normalize(mix(
  normal,
  wildDefaultBaseNormal,
  clamp(wildMaterialWetness * wildWetnessNormalFlattening, 0.0, 0.7)
));
#if __VERSION__ >= 300 && !defined( FLAT_SHADED )
if (wildDefaultSurfaceAmount > 0.0 && wildSurfaceReliefUnit != 0.0) {
  // 无参数化凹凸（Mikkelsen listing 3）：只给高度场，不需要切线，斜屋面同样成立。
  // 这里刻意不归一化屏幕空间导数：未归一化时扰动角恰好等于真实坡度（米/米），
  // 与像素密度无关；若像 three 的 bumpmap 那样归一化，强度会随分辨率漂移。
  vec3 wildSurfaceSigmaX = dFdx(-vViewPosition);
  vec3 wildSurfaceSigmaY = dFdy(-vViewPosition);
  float wildSurfaceHeight = wildSurfaceRelief * wildSurfaceReliefUnit * wildDefaultSurfaceAmount;
  vec2 wildSurfaceSlope = vec2(dFdx(wildSurfaceHeight), dFdy(wildSurfaceHeight));
  vec3 wildSurfaceR1 = cross(wildSurfaceSigmaY, normal);
  vec3 wildSurfaceR2 = cross(normal, wildSurfaceSigmaX);
  float wildSurfaceDet = dot(wildSurfaceSigmaX, wildSurfaceR1) * faceDirection;
  vec3 wildSurfaceGrad = sign(wildSurfaceDet) * (
    wildSurfaceSlope.x * wildSurfaceR1 + wildSurfaceSlope.y * wildSurfaceR2
  );
  vec3 wildSurfacePerturbed = abs(wildSurfaceDet) * normal - wildSurfaceGrad;
  float wildSurfaceLength = length(wildSurfacePerturbed);
  normal = wildSurfaceLength > 1e-9 ? wildSurfacePerturbed / wildSurfaceLength : normal;
}
#endif`,
    )
}

function createDefaultSurfaceParams(
  descriptor: RenderMaterialDescriptor,
  materialSeed: string,
): DefaultSurfaceParams {
  const family = descriptor.family
  const base = family === 'mineral' || family === 'masonry'
    ? { scale: 2.1, color: 0.11, roughness: 0.13 }
    : family === 'wood'
      ? { scale: 5.2, color: 0.1, roughness: 0.085 }
      : family === 'metal'
        ? { scale: 8.5, color: 0.045, roughness: 0.065 }
        : { scale: 3.5, color: 0.04, roughness: 0.05 }
  const relief = RELIEF_PRESETS[family]
  return {
    family,
    familyCode: FAMILY_CODE[family],
    seed: hashString(materialSeed) % 65521,
    scale: base.scale,
    colorVariation: base.color,
    roughnessVariation: base.roughness,
    relief: relief.relief,
    reliefRoughness: relief.reliefRoughness,
    courseCells: relief.courseCells,
    grainFrequency: relief.grainFrequency,
    wetnessAbsorption: descriptor.environmentResponse.wetness?.absorption ?? 0,
    wetnessDarkening: descriptor.environmentResponse.wetness?.colorDarkening ?? 0,
    wetnessRoughnessReduction: descriptor.environmentResponse.wetness?.roughnessReduction ?? 0,
    wetnessNormalFlattening: descriptor.environmentResponse.wetness?.normalFlattening ?? 0.24,
    rainStreakStrength: descriptor.environmentResponse.rainStreak?.strength ?? 0,
    snowAdhesion: descriptor.environmentResponse.snow?.adhesion ?? 0,
    dustAdhesion: descriptor.environmentResponse.dust?.adhesion ?? 0,
  }
}

function hashString(value: string): number {
  let hash = 2166136261
  for (let index = 0; index < value.length; index++) {
    hash ^= value.charCodeAt(index)
    hash = Math.imul(hash, 16777619)
  }
  return hash >>> 0
}
