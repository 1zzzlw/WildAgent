import wildSchema from '../../../../wild-lang/schema.json';

type JsonSchema = Record<string, any>;

export function validateBlueprintSchema(value: unknown): string[] {
  return validate(value, wildSchema as JsonSchema, '$');
}

function validate(value: unknown, inputSchema: JsonSchema, path: string): string[] {
  const schema = inputSchema.$ref ? resolveReference(inputSchema.$ref) : inputSchema;
  const errors: string[] = [];

  if (schema.oneOf) {
    const candidates = (schema.oneOf as JsonSchema[]).map(candidate => validate(value, candidate, path));
    const matchCount = candidates.filter(candidateErrors => candidateErrors.length === 0).length;
    if (matchCount !== 1) {
      const reasons = [...candidates]
        .sort((a, b) => a.length - b.length)
        .map(candidateErrors => candidateErrors[0])
        .filter(Boolean)
        .slice(0, 2)
        .join('；');
      errors.push(`${path} 必须且只能匹配一种结构${reasons ? `（${reasons}）` : ''}`);
    }
  }

  if (schema.const !== undefined && value !== schema.const) {
    errors.push(`${path} 必须为 ${JSON.stringify(schema.const)}`);
  }
  if (schema.enum && !(schema.enum as unknown[]).includes(value)) {
    errors.push(`${path} 必须是 ${schema.enum.map((item: unknown) => JSON.stringify(item)).join(' / ')}`);
  }

  if (schema.type && !matchesType(value, schema.type)) {
    errors.push(`${path} 必须是 ${schema.type}`);
    return errors;
  }

  if (typeof value === 'number') {
    if (!Number.isFinite(value)) errors.push(`${path} 必须是有限数值`);
    if (schema.minimum !== undefined && value < schema.minimum) {
      errors.push(`${path} 不能小于 ${schema.minimum}`);
    }
    if (schema.maximum !== undefined && value > schema.maximum) {
      errors.push(`${path} 不能大于 ${schema.maximum}`);
    }
    if (schema.exclusiveMinimum !== undefined && value <= schema.exclusiveMinimum) {
      errors.push(`${path} 必须大于 ${schema.exclusiveMinimum}`);
    }
  }

  if (typeof value === 'string') {
    if (schema.minLength !== undefined && value.length < schema.minLength) {
      errors.push(`${path} 长度不能小于 ${schema.minLength}`);
    }
    if (schema.pattern && !new RegExp(schema.pattern).test(value)) {
      errors.push(`${path} 不符合格式 ${schema.pattern}`);
    }
  }

  if (Array.isArray(value)) {
    if (schema.minItems !== undefined && value.length < schema.minItems) {
      errors.push(`${path} 至少需要 ${schema.minItems} 项`);
    }
    if (schema.maxItems !== undefined && value.length > schema.maxItems) {
      errors.push(`${path} 最多允许 ${schema.maxItems} 项`);
    }
    if (schema.items) {
      value.forEach((item, index) => {
        errors.push(...validate(item, schema.items, `${path}[${index}]`));
      });
    }
  }

  if (isObject(value)) {
    for (const required of schema.required || []) {
      if (!(required in value)) errors.push(`${path}.${required} 为必填字段`);
    }

    for (const [key, child] of Object.entries(value)) {
      const childSchema = schema.properties?.[key];
      if (childSchema) {
        errors.push(...validate(child, childSchema, `${path}.${key}`));
      } else if (schema.additionalProperties === false) {
        errors.push(`${path}.${key} 是未知字段`);
      } else if (isObject(schema.additionalProperties)) {
        errors.push(...validate(child, schema.additionalProperties, `${path}.${key}`));
      }
    }
  }

  return errors;
}

function resolveReference(reference: string): JsonSchema {
  if (!reference.startsWith('#/')) {
    throw new Error(`Unsupported schema reference: ${reference}`);
  }
  const segments = reference
    .slice(2)
    .split('/')
    .map(segment => segment.replace(/~1/g, '/').replace(/~0/g, '~'));
  let value: any = wildSchema;
  for (const segment of segments) value = value?.[segment];
  if (!value) throw new Error(`Schema reference not found: ${reference}`);
  return value as JsonSchema;
}

function matchesType(value: unknown, type: string): boolean {
  switch (type) {
    case 'array': return Array.isArray(value);
    case 'object': return isObject(value);
    case 'integer': return Number.isInteger(value);
    case 'number': return typeof value === 'number';
    case 'string': return typeof value === 'string';
    case 'boolean': return typeof value === 'boolean';
    case 'null': return value === null;
    default: return true;
  }
}

function isObject(value: unknown): value is Record<string, any> {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}
