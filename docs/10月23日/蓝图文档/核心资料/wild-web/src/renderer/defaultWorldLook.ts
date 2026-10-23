export type TimeOfDay = 'day' | 'sunset' | 'night'
export type ViewMode = 'editor' | 'presentation'
export type QualityLevel = 'low' | 'medium' | 'high'
export type CameraPresetId = 'corner' | 'human' | 'bird' | 'front'
export type EnvironmentPresetId = 'minimal' | 'meadow' | 'alpine' | 'desert' | 'autumn'

export interface TimePreset {
  label: string
  icon: string
  background: number
  exposure: number
  skyVisible: boolean
  turbidity: number
  rayleigh: number
  mieCoefficient: number
  mieDirectionalG: number
  sunPhi: number
  sunTheta: number
  directionalColor: number
  directionalIntensity: number
  hemisphereSkyColor: number
  hemisphereGroundColor: number
  hemisphereIntensity: number
  groundColor: number
  fogColor: number
}

export interface QualityPreset {
  label: string
  pixelRatio: number
  shadowMapSize: number
  ssao: boolean
  bloom: boolean
}

export interface CameraPreset {
  label: string
  direction: [number, number, number]
}

export interface EnvironmentPreset {
  label: string
  icon: string
  groundColor: number
  fogColor: number
  sunAzimuthOffset: number
  directLightScale: number
  ambientLightScale: number
  exposureScale: number
  shadowOpacity: number
}

export const TIME_ORDER: TimeOfDay[] = ['day', 'sunset', 'night']
/**
 * ── 时段预设的标定口径（2026-09-21 重标）────────────────────────
 *
 * 这里的曝光与光强是**同一把尺子**上的两个数字，必须一起看：
 * `renderer.toneMappingExposure` 决定"天空这张图有多亮"，光强决定"建筑有多亮"，
 * 而两者的**比值**决定"直射光 : 环境光"，也就是体面能不能看清。
 *
 * 为什么现在要重标：S0 把 IBL（`scene.environment`）接进引擎后，
 * 建筑同时拿到"直射光 + 半球光 + 环境光"三份照明，而这三个数是在**没有 IBL** 的
 * 年代调的 —— 结果白天 37% 的像素被打到 240 以上（云、白墙、屋面全部并成同一个白），
 * 天空更是整片纯白。
 *
 * 怎么标：不看"好不好看"，看三个可计算的量（出图实测，见
 * `.workbuddy/diag/sweep_exposure_calibration.mjs`）：
 *   ① 过曝比（亮度 ≥240 的像素占比）≤ 2% —— 像素一进饱和区，其上的材质与几何细节就没了；
 *   ② 天空区必须仍然是"蓝的"（B−R ≥ 18）—— 白天空的 B−R 趋近 0，这是"打白"的客观标志；
 *   ③ 在满足 ①② 的前提下最大化细节能量（相邻像素亮度梯度均值）= 让细节真的看得见。
 *
 * ⚠️ 曝光之所以能从 1.08 掉到 0.30 而画面不暗，是因为 three 的 `Sky` 着色器输出的
 * **不是显示亮度而是任意尺度的辐射量**（three 官方 Sky 示例配的就是 exposure 0.5）。
 * 曝光小了 3.2 倍 → 天空与 IBL 一起落到合理区间；光强同时提上去 → 直射光相对环境光
 * 变强约 4 倍，这才是"白墙不再一片死白、窗框与檐口重新出现"的真正原因。
 */
export const TIME_PRESETS: Record<TimeOfDay, TimePreset> = {
  day: {
    label: '白天', icon: '☀️', background: 0xb9c9d8, exposure: 0.30, skyVisible: true,
    // rayleigh 1.72 → 0.9、turbidity 3.2 → 2.4：实测这两个数直接决定"天是不是蓝的"。
    // 出图实测天空区平均色（同一机位、同一曝光）：
    //   原值 1.72/3.2 → rgb(195,208,213) B−R=19（灰白）
    //   现值 0.90/2.4 → rgb(165,188,202) B−R=36，天顶 rgb(139,168,188)（真天蓝）
    // ⚠️ 反向直觉：**提高** rayleigh（three 官方示例用 3）会让天空更亮更白，
    // 因为瑞利系数在这里是散射总量而不是"蓝色浓度"。别照抄官方示例值。
    turbidity: 2.4, rayleigh: 0.9, mieCoefficient: 0.005, mieDirectionalG: 0.81,
    sunPhi: 48, sunTheta: 135, directionalColor: 0xfff1d6, directionalIntensity: 11.8,
    hemisphereSkyColor: 0xddeeff, hemisphereGroundColor: 0x665544,
    // 半球光只补"IBL 里没有的地面反弹"，所以绝对值不高；它已经不是主要照明。
    hemisphereIntensity: 0.68, groundColor: 0x7c8378, fogColor: 0xb9c9d8,
  },
  sunset: {
    // exposure 0.9 → 1.1：旧值是在"查看器出图脚本强制 exp=1.05"的前提下看着合适的，
    // 一旦让查看器真的走预设（0.9），黄昏就偏暗（均值 113）；实测 1.1 落在 127 左右。
    label: '黄昏', icon: '🌇', background: 0x6f4054, exposure: 1.1, skyVisible: true,
    turbidity: 10, rayleigh: 2.8, mieCoefficient: 0.02, mieDirectionalG: 0.9,
    sunPhi: 84, sunTheta: 245, directionalColor: 0xff8a4c, directionalIntensity: 1.82,
    hemisphereSkyColor: 0xffa27d, hemisphereGroundColor: 0x34283f,
    hemisphereIntensity: 0.38, groundColor: 0x5b4b48, fogColor: 0x6f4054,
  },
  night: {
    // exposure 0.68 → 1.4：旧值同样只在 exp=1.05 的强制覆盖下看着成立；走预设时
    // 13% 的画面被压到 ≤8（细节能量 0.57，整片死黑）。实测 1.4 时均值 ≈29、墙 ≈70。
    label: '夜晚', icon: '🌙', background: 0x050914, exposure: 1.4, skyVisible: false,
    turbidity: 2, rayleigh: 0.2, mieCoefficient: 0.001, mieDirectionalG: 0.7,
    sunPhi: 108, sunTheta: 220, directionalColor: 0x9dbbff, directionalIntensity: 0.32,
    hemisphereSkyColor: 0x182442, hemisphereGroundColor: 0x08070d,
    hemisphereIntensity: 0.2, groundColor: 0x111722, fogColor: 0x050914,
  },
}

export const QUALITY_ORDER: QualityLevel[] = ['low', 'medium', 'high']
export const QUALITY_PRESETS: Record<QualityLevel, QualityPreset> = {
  low: { label: '流畅', pixelRatio: 1, shadowMapSize: 1024, ssao: false, bloom: false },
  // pixelRatio 1.25 + SSAO 半分辨率：默认档清晰度与帧率更平衡。
  medium: { label: '均衡', pixelRatio: 1.25, shadowMapSize: 2048, ssao: true, bloom: false },
  high: { label: '精细', pixelRatio: 2, shadowMapSize: 4096, ssao: true, bloom: true },
}

export const CAMERA_ORDER: CameraPresetId[] = ['corner', 'human', 'bird', 'front']
export const CAMERA_PRESETS: Record<CameraPresetId, CameraPreset> = {
  corner: { label: '街角', direction: [1, 0.72, 1] },  // 从 0.62 提升到 0.72，抬高俯角让屋面更突出
  human: { label: '人视', direction: [1, 0.18, 1] },
  bird: { label: '鸟瞰', direction: [0.8, 1.25, 0.8] },
  front: { label: '正立面', direction: [0, 0.12, 1] },
}

export const ENVIRONMENT_ORDER: EnvironmentPresetId[] = [
  'minimal', 'meadow', 'alpine', 'desert', 'autumn',
]
export const ENVIRONMENT_PRESETS: Record<EnvironmentPresetId, EnvironmentPreset> = {
  minimal: {
    label: '极简', icon: '◻️', groundColor: 0x747b73, fogColor: 0xb9c9d8,
    sunAzimuthOffset: 0, directLightScale: 1, ambientLightScale: 0.9, exposureScale: 1,
    shadowOpacity: 0.40,  // 从 0.22 提升到 0.40，增强阴影落地感
  },
  meadow: {
    label: '草地', icon: '🌿', groundColor: 0x526d42, fogColor: 0xadc2ae,
    sunAzimuthOffset: -18, directLightScale: 1.16, ambientLightScale: 0.72, exposureScale: 0.96,
    shadowOpacity: 0.42,  // 从 0.28 提升到 0.42
  },
  alpine: {
    label: '雪山', icon: '🏔️', groundColor: 0xc9d1d5, fogColor: 0xc6d2da,
    sunAzimuthOffset: 16, directLightScale: 1.22, ambientLightScale: 0.82, exposureScale: 0.92,
    shadowOpacity: 0.44,  // 从 0.3 提升到 0.44
  },
  desert: {
    label: '沙漠', icon: '🏜️', groundColor: 0xb9844f, fogColor: 0xd2ad7f,
    sunAzimuthOffset: 30, directLightScale: 1.3, ambientLightScale: 0.66, exposureScale: 0.92,
    shadowOpacity: 0.46,  // 从 0.34 提升到 0.46
  },
  autumn: {
    label: '秋林', icon: '🍂', groundColor: 0x665c3d, fogColor: 0xb39a78,
    sunAzimuthOffset: -32, directLightScale: 1.18, ambientLightScale: 0.68, exposureScale: 0.92,
    shadowOpacity: 0.44,  // 从 0.32 提升到 0.44
  },
}
