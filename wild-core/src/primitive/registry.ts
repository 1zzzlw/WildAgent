import type { EngineCapability, MeshData } from './types';
import {
  buildBeam,
  buildBody,
  buildColumn,
  buildDenseBrick,
  buildFloor,
  buildFurniture,
  buildOpening,
  buildPrimitive,
  buildRoof,
  buildStair,
  buildWall,
} from './geometry';

export interface ElementBuilderRegistration {
  type: string;
  status: EngineCapability['status'];
  description: string;
  build: (element: any) => MeshData[];
}

const builders = new Map<string, ElementBuilderRegistration>();

/**
 * 注册构件 builder。
 *
 * 当前仅允许应用启动时静态注册。蓝图不能携带或执行 JavaScript，避免
 * 把数据格式变成任意代码执行入口。
 */
export function registerElementBuilder(registration: ElementBuilderRegistration): void {
  if (!registration.type) throw new Error('Builder registration requires a type');
  if (builders.has(registration.type)) {
    throw new Error(`Element builder already registered: ${registration.type}`);
  }
  builders.set(registration.type, registration);
}

export function getElementBuilder(type: string): ElementBuilderRegistration | undefined {
  return builders.get(type);
}

export function getEngineCapabilities(): EngineCapability[] {
  return [...builders.values()]
    .map(({ type, status, description }) => ({ type, status, description }))
    .sort((a, b) => a.type.localeCompare(b.type));
}

function registerBuiltins(): void {
  const builtins: ElementBuilderRegistration[] = [
    { type: 'wall', status: 'stable', description: '直线/圆弧墙体与矩形洞口', build: buildWall },
    { type: 'floor', status: 'stable', description: '矩形或圆形楼板', build: buildFloor },
    { type: 'column', status: 'partial', description: '参数化柱体；柱式细部持续补齐', build: buildColumn },
    { type: 'beam', status: 'partial', description: '矩形、圆形与工字梁', build: buildBeam },
    { type: 'roof', status: 'partial', description: '基础屋顶、中式曲面与重檐屋顶', build: buildRoof },
    { type: 'opening', status: 'partial', description: '墙体洞口及门窗覆盖几何', build: buildOpening },
    { type: 'stair', status: 'stable', description: '直跑参数化楼梯', build: buildStair },
    { type: 'furniture', status: 'partial', description: '基础参数化家具', build: buildFurniture },
    { type: 'dense_brick', status: 'experimental', description: '体素细节；等值面提取仍为实验能力', build: buildDenseBrick },
    { type: 'body', status: 'partial', description: '简化参数化人物', build: buildBody },
    { type: 'primitive', status: 'stable', description: 'WILD v1.1 通用 box/sphere/cylinder/profile_sweep', build: buildPrimitive },
  ];

  for (const registration of builtins) registerElementBuilder(registration);
}

registerBuiltins();
