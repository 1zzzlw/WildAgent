import type { OpeningParams } from '../types';

export function buildOpeningContour(
  style: OpeningParams['style'],
  hw: number,
  hh: number,
  width: number,
  height: number,
): Array<[number, number]> {
  if (style === 'circular') {
    const radius = Math.min(width, height) / 2;
    return Array.from({ length: 32 }, (_, index) => {
      const angle = index / 32 * Math.PI * 2;
      return [Math.cos(angle) * radius, Math.sin(angle) * radius] as [number, number];
    });
  }
  if (style === 'arched') {
    const radius = Math.min(hw, height * 0.45);
    const springY = hh - radius;
    const contour: Array<[number, number]> = [[-hw, -hh], [hw, -hh], [hw, springY]];
    if (radius < hw - 1e-9) contour.push([radius, springY]);
    for (let index = 0; index <= 18; index++) {
      const angle = Math.PI * index / 18;
      const point: [number, number] = [
        Math.cos(angle) * radius,
        springY + Math.sin(angle) * radius,
      ];
      const previous = contour[contour.length - 1];
      if (Math.hypot(previous[0] - point[0], previous[1] - point[1]) > 1e-9) {
        contour.push(point);
      }
    }
    if (radius < hw - 1e-9) contour.push([-hw, springY]);
    return contour;
  }
  if (style === 'gothic') {
    const springY = hh - Math.min(height * 0.38, hw);
    return [[-hw, -hh], [hw, -hh], [hw, springY], [0, hh], [-hw, springY]];
  }
  return [[-hw, -hh], [hw, -hh], [hw, hh], [-hw, hh]];
}
