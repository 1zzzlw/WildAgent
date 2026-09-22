import type { BodyParams, MeshData, Vec3 } from '../types';
import { buildPrimitive } from './primitive';

export function buildBody(params: BodyParams): MeshData[] {
  const {
    height,
    build,
    headShape,
    armLength,
    legLength,
    cloakLength,
    hoodUp,
    material,
  } = params;
  if (height <= 0) throw new Error('body height must be greater than zero');

  const origin = params.position || [0, 0, 0];
  const materialRef = material || 'default';
  const buildScale = build === 'lean' ? 0.82 : build === 'stout' ? 1.18 : 1;
  const headRadius = height * 0.075;
  const legHeight = height * 0.42 * legLength;
  const torsoHeight = height * 0.35;
  const torsoRadius = height * 0.085 * buildScale;
  const shoulderY = legHeight + torsoHeight * 0.82;
  const armHeight = height * 0.28 * armLength;
  const limbRadius = height * 0.032 * buildScale;
  const meshes: MeshData[] = [];

  const add = (definition: Parameters<typeof buildPrimitive>[0]) => {
    for (const mesh of buildPrimitive(definition)) {
      mesh.transform.position = addVec3(mesh.transform.position, origin);
      meshes.push(mesh);
    }
  };

  add({
    type: 'primitive', id: `${params.id}_torso`, shape: 'cylinder',
    radiusBottom: torsoRadius * 0.82, radiusTop: torsoRadius,
    height: torsoHeight, position: [0, legHeight + torsoHeight / 2, 0],
    material: materialRef,
  });
  add({
    type: 'primitive', id: `${params.id}_head`, shape: 'sphere',
    radius: headRadius, position: [0, legHeight + torsoHeight + headRadius * 1.18, 0],
    scale: headScale(headShape), material: materialRef,
  });

  for (const side of [-1, 1]) {
    add({
      type: 'primitive', id: `${params.id}_leg_${side}`, shape: 'cylinder',
      radius: limbRadius, height: legHeight,
      position: [side * torsoRadius * 0.48, legHeight / 2, 0],
      material: materialRef,
    });
    add({
      type: 'primitive', id: `${params.id}_arm_${side}`, shape: 'cylinder',
      radius: limbRadius * 0.86, height: armHeight,
      position: [side * (torsoRadius + armHeight / 2), shoulderY, 0],
      rotation: [0, 0, Math.PI / 2],
      material: materialRef,
    });
  }

  if (cloakLength > 0.3) {
    add({
      type: 'primitive', id: `${params.id}_cloak`, shape: 'box',
      dimensions: [torsoRadius * 2.25, height * 0.32 * cloakLength, height * 0.025],
      position: [0, legHeight + torsoHeight * 0.48, -torsoRadius * 0.92],
      material: materialRef,
    });
  }
  if (hoodUp) {
    add({
      type: 'primitive', id: `${params.id}_hood`, shape: 'sphere',
      radius: headRadius * 1.22,
      position: [0, legHeight + torsoHeight + headRadius * 1.18, -headRadius * 0.2],
      scale: [1, 1.08, 0.82],
      material: materialRef,
    });
  }

  return meshes;
}

function headScale(shape: BodyParams['headShape']): Vec3 {
  if (shape === 'oval') return [0.9, 1.16, 0.9];
  if (shape === 'angular') return [1, 1, 0.88];
  return [1, 1, 1];
}

function addVec3(a: Vec3, b: Vec3): Vec3 {
  return [a[0] + b[0], a[1] + b[1], a[2] + b[2]];
}
