import { csgBoundaryTriangles } from './geometry/csgBoundary';
import modeling from '@jscad/modeling';
import type { GeometryElement, SolidParams, MeshData, EngineDiagnostic } from './types';
import { buildSolid } from './geometry/solid';
import { buildPrimitive } from './geometry/primitive';
import {
  meshTriangles,
  validateTriangles,
  trianglesToMeshes,
  signedVolume,
  pointOnTriangle,
  sub,
  cross,
  dot,
  unit,
  mul,
  add,
  type Tri
} from './geometry/solidMath';
const { booleans, geometries, measurements } = modeling;
/** Blueprint-local dependency evaluator. No source JSON or operand visibility is mutated. */
export function createSolidEvaluator(elements: GeometryElement[]) {
  const by = new Map<string, GeometryElement>(),
    duplicates = new Set<string>();
  for (const e of elements) {
    if (by.has(e.id)) duplicates.add(e.id);
    by.set(e.id, e);
  }
  const cache = new Map<string, MeshData[]>(),
    active = new Set<string>(),
    failures = new Map<string, Error>(),
    hidden = new Set<string>(),
    preserved = new Set<string>(),
    notices: EngineDiagnostic[] = [];
  function evaluate(id: string, depth = 0): MeshData[] {
    if (cache.has(id)) return cache.get(id)!;
    if (failures.has(id)) throw failures.get(id)!;
    if (depth > 64) throw Error('boolean dependency depth exceeds 64');
    if (active.has(id)) throw Error('boolean operand dependency cycle: ' + id);
    if (duplicates.has(id)) throw Error('duplicate solid/operand id: ' + id);
    const e = by.get(id);
    if (!e) throw Error('boolean operand not found: ' + id);
    active.add(id);
    try {
      let meshes: MeshData[];
      if (e.type === 'primitive') meshes = buildPrimitive(e);
      else if (e.type === 'solid' && e.kind !== 'boolean') meshes = buildSolid(e);
      else if (e.type === 'solid') meshes = booleanMesh(e, depth);
      else throw Error('boolean operands must be solid or closed primitive; unsupported ' + e.type);
      cache.set(id, meshes);
      return meshes;
    } catch (error) {
      const err = error instanceof Error ? error : new Error(String(error));
      failures.set(id, err);
      throw err;
    } finally {
      active.delete(id);
    }
  }
  function booleanMesh(s: SolidParams, depth: number): MeshData[] {
    if (s.position || s.rotation || s.scale || (s as any)._instanceTransform)
      throw Error('boolean result does not accept transforms or template instances');
    const refs = s.operands!;
    if (!Array.isArray(refs) || refs.length < 2 || new Set(refs).size !== refs.length)
      throw Error('boolean requires at least two distinct operands');
    if (s.cutMaterial && s.operation !== 'difference')
      throw Error('cutMaterial is only valid for difference');
    const epsilon = s.tolerance ?? 1e-6;
    if (epsilon < 1e-9 || epsilon > 1e-3 || !Number.isFinite(epsilon))
      throw Error('invalid boolean tolerance');
    const sources = refs.map(id => {
      const el = by.get(id);
      if (el && (el as any)._instanceTransform)
        throw Error('boolean operand instances require explicit elements with independent ids');
      return evaluate(id, depth + 1);
    });
    const input = sources.map((ms, i) => {
      try {
        return validateTriangles(meshTriangles(ms), epsilon);
      } catch (error) {
        throw Error('operand ' + refs[i] + ': ' + (error as Error).message);
      }
    });
    if (input.reduce((n, t) => n + t.length, 0) > 12000)
      throw Error('boolean input budget exceeded (12000 triangles)');
    const data = input.map(ts => geometries.geom3.fromPoints(ts as any));
    let result: any;
    if (s.operation === 'intersection')
      result = input.some(t => !t.length)
        ? geometries.geom3.create()
        : data.reduce((a, b) => booleans.intersect(a, b));
    else if (s.operation === 'union') {
      const ds = data.filter((_, i) => input[i].length);
      result = ds.length ? ds.reduce((a, b) => booleans.union(a, b)) : geometries.geom3.create();
    } else if (s.operation === 'difference')
      result = data
        .slice(1)
        .reduce(
          (a, b, i) =>
            input[i + 1].length && geometries.geom3.toPolygons(a).length ? booleans.subtract(a, b) : a,
          data[0]
        );
    else throw Error('unknown boolean operation');
    const polys = geometries.geom3.toPolygons(result);
    const internal = polys.length ? measurements.measureEpsilon(result) : 0;
    const effective = Math.max(epsilon, Number.isFinite(internal) ? internal : epsilon);
    if (effective > 1e-3)
      throw Error('CSG numeric extent too large; split the model or reduce its coordinate scale');
    if (effective > epsilon * 1.01)
      notices.push({
        level: 'info',
        code: 'SOLID_BOOLEAN_PRECISION',
        elementId: s.id,
        elementType: 'solid',
        message: 'CSG boundary welding tolerance ' + effective + ' m'
      });
    const raw = csgBoundaryTriangles(polys as any, effective);
    let ts: Tri[];
    try {
      ts = validateTriangles(raw, effective);
    } catch (error) {
      throw Error('boolean output: ' + (error as Error).message);
    }
    if (!ts.length)
      notices.push({
        level: 'warning',
        code: 'SOLID_BOOLEAN_EMPTY',
        elementId: s.id,
        elementType: 'solid',
        message: 'boolean returned an empty result'
      });
    if (s.operation === 'difference' && Math.abs(signedVolume(ts) - signedVolume(input[0])) < epsilon ** 2)
      notices.push({
        level: 'warning',
        code: 'SOLID_BOOLEAN_NO_EFFECT',
        elementId: s.id,
        elementType: 'solid',
        message: 'difference made no measurable cut'
      });
    const material = s.material ?? sources[0][0]?.materialRef ?? 'default';
    const cut: Tri[] = [],
      body: Tri[] = [];
    const cutters = input.slice(1).flat();
    if (s.cutMaterial) {
      if (ts.length * cutters.length > 4000000) throw Error('cut-material classification budget exceeded');
      for (const t of ts) {
        const n = unit(cross(sub(t[1], t[0]), sub(t[2], t[0]))),
          p = mul(add(add(t[0], t[1]), t[2]), 1 / 3);
        const isCut = cutters.some(
          c =>
            dot(n, unit(cross(sub(c[1], c[0]), sub(c[2], c[0])))) < -0.99 &&
            pointOnTriangle(p, c, effective * 4)
        );
        (isCut ? cut : body).push(t);
      }
    } else body.push(...ts);
    for (const id of refs) (s.keepOperands ? preserved : hidden).add(id);
    return [...trianglesToMeshes(body, material), ...trianglesToMeshes(cut, s.cutMaterial)];
  }
  // Pre-evaluate booleans so operand visibility is resolved independently of list order.
  for (const e of elements)
    if (e.type === 'solid' && e.kind === 'boolean') {
      try {
        evaluate(e.id);
      } catch {
        /* reported per element by reconstructEntity */
      }
    }
  for (const id of preserved) hidden.delete(id);
  return { build: (e: SolidParams) => evaluate(e.id), hidden, notices };
}
