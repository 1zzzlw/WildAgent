/**
 * 交互行为脚本解释器（Script Interpreter）
 * ==========================================
 *
 * 【在渲染管线中的角色】
 *
 * 渲染引擎重建场景时，每个 GeometryElement 可以通过 `behaviors.scripts`
 * 携带一份 ScriptData，定义该构件在被用户交互时如何响应。
 *
 * 数据流：
 *   Blueprint JSON → parser → GeometryElement.behaviors.scripts
 *                              ↓
 *                       ReconstructedEntity.scripts (透传)
 *                              ↓
 *                       CanvasViewport (Three.js 视口)
 *                              ↓  用户点击/hover 某个 mesh
 *                       ScriptInterpreter.execute(script, event)
 *                              ↓
 *                       执行对应的 Action (toggle_hinge / play_sound / ...)
 *
 * 【支持的事件类型】
 *   - on_click : 用户点击该构件
 *   - on_enter : 鼠标移入该构件
 *   - on_leave : 鼠标移出该构件
 *
 * 【支持的动作类型】（当前均为待实现的空桩）
 *   - toggle_hinge : 开关门/窗（铰链约束翻转）
 *   - play_sound   : 播放音效
 *   - set_material : 切换材质
 *   - show_text    : 显示浮动文字
 *   - teleport     : 传送玩家/摄像机到指定位置
 *
 * 【当前状态】
 *   所有 Action 的具体实现均为空桩（break），
 *   这是因为 Phase 1 的重点是几何渲染，交互系统尚未接入。
 *   Phase 3（完整编辑工作流）中将实现 3D 拾取 + 选中高亮后，
 *   本解释器的 action 才会逐步填充实际逻辑。
 */
import type { ScriptData, ActionData } from '../types';

export class ScriptInterpreter {
  execute(script: ScriptData, event: { type: string; target: string }) {
    const handler = script[event.type as keyof ScriptData];
    if (!handler) return;
    if (handler.condition && !evaluateCondition(handler.condition, event)) return;
    for (const action of handler.actions) {
      this.executeAction(action);
    }
  }

  private executeAction(action: ActionData) {
    switch (action.type) {
      case 'toggle_hinge': break;
      case 'play_sound': break;
      case 'show_text': break;
      case 'teleport': break;
      default: console.warn(`Unknown action: ${action.type}`);
    }
  }
}

function evaluateCondition(expr: string, event: { type: string; target: string }): boolean {
  if (expr.startsWith("event.target ==")) {
    const target = expr.split("==")[1].trim().replace(/'/g, '');
    return event.target === target;
  }
  return true;
}