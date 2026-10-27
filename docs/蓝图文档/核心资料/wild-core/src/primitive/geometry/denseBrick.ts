import type { DenseBrickParams, MeshData } from '../types';

export function buildDenseBrick(params: DenseBrickParams): MeshData[] {
  void params;
  throw new Error(
    'dense_brick is experimental: voxel decompression and surface extraction are not implemented',
  );
}
