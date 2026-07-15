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
      case 'play_sound':   break;
      case 'show_text':    break;
      case 'teleport':     break;
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