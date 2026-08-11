import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { PBRTextureSetAsset } from '../types/blueprint'
import type { ScenePatch } from '../types/scenePatch'

export interface PBRUploadRequest {
  name: string
  materialName: string
  license: string
  baseRevision: number
  roughness: number
  metallic: number
  normalScale: number
  uvScale: [number, number]
  materialClass: string
  tags: string[]
  recommendedRoles: string[]
  realWorldSizeMeters: [number, number]
  files: {
    baseColor: File
    normal?: File
    roughness?: File
    metalness?: File
    ambientOcclusion?: File
  }
}

interface PBRUploadResponse {
  asset: PBRTextureSetAsset
  patch: ScenePatch
  trace: Array<{ node: string; status: string; detail?: string }>
}

export const useAssetStore = defineStore('assets', () => {
  const assets = ref<PBRTextureSetAsset[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)

  async function refresh(): Promise<void> {
    try {
      const response = await fetch('/api/assets', { cache: 'no-store' })
      if (!response.ok) throw new Error(`资产列表请求失败 (${response.status})`)
      assets.value = await response.json()
      error.value = null
    } catch (cause) {
      error.value = cause instanceof Error ? cause.message : String(cause)
    }
  }

  async function registerPbr(request: PBRUploadRequest): Promise<PBRUploadResponse | null> {
    loading.value = true
    error.value = null
    try {
      const form = new FormData()
      form.set('name', request.name)
      form.set('material_name', request.materialName)
      form.set('license', request.license)
      form.set('base_revision', String(request.baseRevision))
      form.set('roughness', String(request.roughness))
      form.set('metallic', String(request.metallic))
      form.set('normal_scale', String(request.normalScale))
      form.set('uv_scale_x', String(request.uvScale[0]))
      form.set('uv_scale_y', String(request.uvScale[1]))
      form.set('material_class', request.materialClass)
      form.set('tags', request.tags.join(','))
      form.set('recommended_roles', request.recommendedRoles.join(','))
      form.set('real_world_width', String(request.realWorldSizeMeters[0]))
      form.set('real_world_height', String(request.realWorldSizeMeters[1]))
      form.set('base_color', request.files.baseColor)
      if (request.files.normal) form.set('normal', request.files.normal)
      if (request.files.roughness) form.set('roughness_map', request.files.roughness)
      if (request.files.metalness) form.set('metalness_map', request.files.metalness)
      if (request.files.ambientOcclusion) {
        form.set('ambient_occlusion', request.files.ambientOcclusion)
      }

      const response = await fetch('/api/assets/pbr', { method: 'POST', body: form })
      if (!response.ok) {
        const body = await response.json().catch(() => null)
        throw new Error(body?.detail || `PBR 入库失败 (${response.status})`)
      }
      const result = await response.json() as PBRUploadResponse
      await refresh()
      return result
    } catch (cause) {
      error.value = cause instanceof Error ? cause.message : String(cause)
      return null
    } finally {
      loading.value = false
    }
  }

  return { assets, loading, error, refresh, registerPbr }
})
