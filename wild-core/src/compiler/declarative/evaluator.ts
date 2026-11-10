/**
 * 配方表达式求值器。
 *
 * 为什么不用 `eval` / `new Function`：配方是**数据**，可能来自导入的构件库文件。
 * `registry.ts` 的注释已经把「蓝图不能携带或执行 JavaScript」定成硬约束，这里
 * 必须一致 —— 只解释一棵白名单语法树，任何越界写法在解析期就失败。
 *
 * 支持的语法（够用即可，多一条就多一份被滥用的可能）：
 *   字面量     12  0.5  'text'  true  false
 *   路径       id  pos.x  host.from      （只读作用域，可写点号链）
 *   算术       + - * / %                 （数组按分量逐元素运算）
 *   比较       == != < <= > >=
 *   逻辑       && || !
 *   三元       cond ? a : b
 *   空值兜底   a ?? b
 *   数组       [a, b, c]
 *   函数       min max abs round floor ceil sqrt hypot clamp if default
 *              cos sin tan deg
 *
 * 不支持的：赋值、成员调用、字符串拼接、正则、循环。需要循环就用配方的 repeat。
 */

export type ExpressionScope = Record<string, unknown>;

type TokenKind = 'number' | 'string' | 'ident' | 'punct' | 'eof';

interface Token {
  kind: TokenKind;
  value: string;
  /** 源码偏移，只用于报错定位。 */
  at: number;
}

const PUNCTUATORS = [
  '??', '&&', '||', '==', '!=', '<=', '>=',
  '+', '-', '*', '/', '%', '(', ')', '[', ']', ',', '?', ':', '<', '>', '!',
];

const FUNCTIONS: Record<string, (...args: unknown[]) => unknown> = {
  min: (...args) => Math.min(...toNumbers(args)),
  max: (...args) => Math.max(...toNumbers(args)),
  abs: value => Math.abs(toNumber(value)),
  round: value => Math.round(toNumber(value)),
  floor: value => Math.floor(toNumber(value)),
  ceil: value => Math.ceil(toNumber(value)),
  sqrt: value => Math.sqrt(toNumber(value)),
  hypot: (...args) => Math.hypot(...toNumbers(args)),
  clamp: (value, low, high) => Math.min(Math.max(toNumber(value), toNumber(low)), toNumber(high)),
  cos: value => Math.cos(toNumber(value)),
  sin: value => Math.sin(toNumber(value)),
  tan: value => Math.tan(toNumber(value)),
  deg: value => (toNumber(value) * Math.PI) / 180,
  if: (condition, whenTrue, whenFalse) => (isTruthy(condition) ? whenTrue : whenFalse),
  default: (value, fallback) => (value === undefined || value === null ? fallback : value),
};

function toNumber(value: unknown): number {
  if (typeof value === 'number') return value;
  if (typeof value === 'boolean') return value ? 1 : 0;
  throw new Error(`期望数值，得到 ${describe(value)}`);
}

function toNumbers(args: unknown[]): number[] {
  return args.map(toNumber);
}

function isTruthy(value: unknown): boolean {
  if (Array.isArray(value)) return value.length > 0;
  return Boolean(value);
}

function describe(value: unknown): string {
  if (value === null) return 'null';
  if (Array.isArray(value)) return `数组(${value.length})`;
  return typeof value;
}

export class RecipeExpressionError extends Error {
  constructor(message: string, expression: string) {
    super(`${message} —— 表达式: ${expression}`);
    this.name = 'RecipeExpressionError';
  }
}

function tokenize(source: string): Token[] {
  const tokens: Token[] = [];
  let index = 0;
  while (index < source.length) {
    const char = source[index];
    if (/\s/.test(char)) { index += 1; continue; }
    if (/[0-9]/.test(char) || (char === '.' && /[0-9]/.test(source[index + 1] || ''))) {
      let end = index;
      while (end < source.length && /[0-9.]/.test(source[end])) end += 1;
      const text = source.slice(index, end);
      if ((text.match(/\./g) || []).length > 1) {
        throw new RecipeExpressionError(`非法数字 ${text}`, source);
      }
      tokens.push({ kind: 'number', value: text, at: index });
      index = end;
      continue;
    }
    if (/[A-Za-z_$]/.test(char)) {
      let end = index;
      while (end < source.length && /[A-Za-z0-9_$.]/.test(source[end])) end += 1;
      tokens.push({ kind: 'ident', value: source.slice(index, end), at: index });
      index = end;
      continue;
    }
    if (char === '"' || char === "'") {
      const quote = char;
      let end = index + 1;
      let text = '';
      while (end < source.length && source[end] !== quote) { text += source[end]; end += 1; }
      if (end >= source.length) throw new RecipeExpressionError('字符串未闭合', source);
      tokens.push({ kind: 'string', value: text, at: index });
      index = end + 1;
      continue;
    }
    const punct = PUNCTUATORS.find(item => source.startsWith(item, index));
    if (!punct) throw new RecipeExpressionError(`无法识别的字符 ${JSON.stringify(char)}`, source);
    tokens.push({ kind: 'punct', value: punct, at: index });
    index += punct.length;
  }
  tokens.push({ kind: 'eof', value: '', at: source.length });
  return tokens;
}

type Node =
  | { kind: 'literal'; value: unknown }
  | { kind: 'path'; parts: string[] }
  | { kind: 'array'; items: Node[] }
  | { kind: 'unary'; operator: string; operand: Node }
  | { kind: 'binary'; operator: string; left: Node; right: Node }
  | { kind: 'conditional'; condition: Node; whenTrue: Node; whenFalse: Node }
  | { kind: 'call'; name: string; args: Node[] };

/** 二元运算符按优先级分层，rank 越大结合越紧。同一 rank 内的运算符左结合。 */
const BINARY_RANKS: readonly (readonly string[])[] = [
  ['??'],
  ['||'],
  ['&&'],
  ['==', '!='],
  ['<', '<=', '>', '>='],
  ['+', '-'],
  ['*', '/', '%'],
];

class Parser {
  private cursor = 0;

  private readonly tokens: Token[];

  private readonly source: string;

  constructor(tokens: Token[], source: string) {
    this.tokens = tokens;
    this.source = source;
  }

  private peek(): Token { return this.tokens[this.cursor]; }

  private next(): Token { return this.tokens[this.cursor++]; }

  private accept(value: string): boolean {
    if (this.peek().kind === 'punct' && this.peek().value === value) { this.cursor += 1; return true; }
    return false;
  }

  private expect(value: string): void {
    if (!this.accept(value)) {
      throw new RecipeExpressionError(`期望 ${value}，实际 ${JSON.stringify(this.peek().value)}`, this.source);
    }
  }

  parse(): Node {
    const node = this.parseConditional();
    if (this.peek().kind !== 'eof') {
      throw new RecipeExpressionError(`多余的内容 ${JSON.stringify(this.peek().value)}`, this.source);
    }
    return node;
  }

  private parseConditional(): Node {
    const condition = this.parseBinary(0);
    if (!this.accept('?')) return condition;
    const whenTrue = this.parseConditional();
    this.expect(':');
    const whenFalse = this.parseConditional();
    return { kind: 'conditional', condition, whenTrue, whenFalse };
  }

  private parseBinary(rank: number): Node {
    const operators = BINARY_RANKS[rank];
    if (!operators) return this.parseUnary();
    let left = this.parseBinary(rank + 1);
    for (;;) {
      const token = this.peek();
      if (token.kind !== 'punct' || !operators.includes(token.value)) break;
      this.cursor += 1;
      const right = this.parseBinary(rank + 1);
      left = { kind: 'binary', operator: token.value, left, right };
    }
    return left;
  }

  private parseUnary(): Node {
    const token = this.peek();
    if (token.kind === 'punct' && (token.value === '-' || token.value === '!' || token.value === '+')) {
      this.cursor += 1;
      return { kind: 'unary', operator: token.value, operand: this.parseUnary() };
    }
    return this.parsePrimary();
  }

  private parsePrimary(): Node {
    const token = this.next();
    if (token.kind === 'number') return { kind: 'literal', value: Number(token.value) };
    if (token.kind === 'string') return { kind: 'literal', value: token.value };
    if (token.kind === 'ident') {
      if (token.value === 'true') return { kind: 'literal', value: true };
      if (token.value === 'false') return { kind: 'literal', value: false };
      if (token.value === 'null') return { kind: 'literal', value: null };
      if (this.accept('(')) {
        const args: Node[] = [];
        if (!this.accept(')')) {
          do { args.push(this.parseConditional()); } while (this.accept(','));
          this.expect(')');
        }
        if (!(token.value in FUNCTIONS)) {
          throw new RecipeExpressionError(`未知函数 ${token.value}`, this.source);
        }
        return { kind: 'call', name: token.value, args };
      }
      return { kind: 'path', parts: token.value.split('.') };
    }
    if (token.kind === 'punct' && token.value === '(') {
      const inner = this.parseConditional();
      this.expect(')');
      return inner;
    }
    if (token.kind === 'punct' && token.value === '[') {
      const items: Node[] = [];
      if (!this.accept(']')) {
        do { items.push(this.parseConditional()); } while (this.accept(','));
        this.expect(']');
      }
      return { kind: 'array', items };
    }
    throw new RecipeExpressionError(`意外的记号 ${JSON.stringify(token.value)}`, this.source);
  }
}

function resolvePath(parts: string[], scope: ExpressionScope): unknown {
  let current: unknown = scope[parts[0]];
  for (let index = 1; index < parts.length; index += 1) {
    if (current === undefined || current === null) return undefined;
    current = (current as Record<string, unknown>)[parts[index]];
  }
  return current;
}

function applyBinary(operator: string, left: unknown, right: unknown): unknown {
  switch (operator) {
    case '??': return left === undefined || left === null ? right : left;
    case '&&': return isTruthy(left) ? right : left;
    case '||': return isTruthy(left) ? left : right;
    case '==': return left === right;
    case '!=': return left !== right;
    case '<': return toNumber(left) < toNumber(right);
    case '<=': return toNumber(left) <= toNumber(right);
    case '>': return toNumber(left) > toNumber(right);
    case '>=': return toNumber(left) >= toNumber(right);
    default: break;
  }
  if (Array.isArray(left) || Array.isArray(right)) {
    const leftList = Array.isArray(left) ? left : [left];
    const rightList = Array.isArray(right) ? right : [right];
    if (leftList.length !== rightList.length) {
      throw new Error(`数组长度不一致 ${leftList.length} / ${rightList.length}`);
    }
    return leftList.map((item, index) => applyArithmetic(operator, item, rightList[index]));
  }
  return applyArithmetic(operator, left, right);
}

function applyArithmetic(operator: string, left: unknown, right: unknown): number {
  const a = toNumber(left);
  const b = toNumber(right);
  switch (operator) {
    case '+': return a + b;
    case '-': return a - b;
    case '*': return a * b;
    case '/': return a / b;
    case '%': return a % b;
    default: throw new Error(`未知运算符 ${operator}`);
  }
}

function evaluateNode(node: Node, scope: ExpressionScope): unknown {
  switch (node.kind) {
    case 'literal': return node.value;
    case 'path': return resolvePath(node.parts, scope);
    case 'array': return node.items.map(item => evaluateNode(item, scope));
    case 'unary': {
      const operand = evaluateNode(node.operand, scope);
      if (node.operator === '!') return !isTruthy(operand);
      const value = toNumber(operand);
      return node.operator === '-' ? -value : value;
    }
    case 'binary':
      return applyBinary(node.operator, evaluateNode(node.left, scope), evaluateNode(node.right, scope));
    case 'conditional':
      return isTruthy(evaluateNode(node.condition, scope))
        ? evaluateNode(node.whenTrue, scope)
        : evaluateNode(node.whenFalse, scope);
    case 'call':
      return FUNCTIONS[node.name](...node.args.map(item => evaluateNode(item, scope)));
    default:
      throw new Error('未覆盖的节点类型');
  }
}

/** 解析缓存：同一配方在一个进程内只解析一次。 */
const cache = new Map<string, Node>();

/** 求值；表达式非法或引用越界都会抛出 `RecipeExpressionError`。 */
export function evaluateExpression(source: string, scope: ExpressionScope): unknown {
  let node = cache.get(source);
  if (!node) {
    try {
      node = new Parser(tokenize(source), source).parse();
    } catch (error) {
      if (error instanceof RecipeExpressionError) throw error;
      throw new RecipeExpressionError(error instanceof Error ? error.message : String(error), source);
    }
    cache.set(source, node);
  }
  try {
    return evaluateNode(node, scope);
  } catch (error) {
    if (error instanceof RecipeExpressionError) throw error;
    throw new RecipeExpressionError(error instanceof Error ? error.message : String(error), source);
  }
}

/** 表达式在**解析期**是否合法（不执行）；用于配方自检与错误提前暴露。 */
export function validateExpression(source: string): void {
  if (!cache.has(source)) {
    cache.set(source, new Parser(tokenize(source), source).parse());
  }
}
