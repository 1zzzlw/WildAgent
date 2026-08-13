export const PROCEDURAL_NOISE_GLSL = /* glsl */ `
float wildHash21(vec2 point) {
  vec3 p3 = fract(vec3(point.xyx) * 0.1031);
  p3 += dot(p3, p3.yzx + 33.33);
  return fract((p3.x + p3.y) * p3.z);
}

float wildValueNoise(vec2 point) {
  vec2 cell = floor(point);
  vec2 local = fract(point);
  local = local * local * (3.0 - 2.0 * local);
  return mix(
    mix(wildHash21(cell), wildHash21(cell + vec2(1.0, 0.0)), local.x),
    mix(wildHash21(cell + vec2(0.0, 1.0)), wildHash21(cell + vec2(1.0)), local.x),
    local.y
  );
}

float wildFbm(vec2 point) {
  float value = 0.0;
  float amplitude = 0.5;
  for (int octave = 0; octave < 3; octave++) {
    value += amplitude * wildValueNoise(point);
    point = point * 2.03 + vec2(17.13, 9.71);
    amplitude *= 0.5;
  }
  return value;
}
`
