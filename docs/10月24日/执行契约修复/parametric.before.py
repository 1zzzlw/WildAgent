"""展开模型声明的参数和重复项；只计算，不执行 Python 或修改设计事实。"""
from copy import deepcopy
import ast
import json
import math
import operator
import re


PARAMETRIC_VERSION = "parametric/1"
MAX_ITEMS = 4096
MAX_VALUES = 200000
_FUNCTIONS = {name: getattr(math, name) for name in
              ("ceil", "floor", "sqrt", "sin", "cos", "tan", "atan2", "hypot", "radians", "degrees")}
_FUNCTIONS.update(abs=abs, min=min, max=max, round=round)
_OPERATORS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
              ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod}
_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_]*\Z")


def expand_parameters(payload: dict, *, facts=None) -> tuple[dict, dict]:
    """显式 parameters 开启计算；结果只含普通 JSON，仍须通过原契约与几何校验。

    =表达式允许数值计算和只读字典/数组引用。数组中的 $repeat 展开 value，
    count 或 items 二选一；var 为循环变量，${变量} 用于稳定 ID。
    """
    if not isinstance(payload, dict):
        raise ValueError("参数化输入必须是对象")
    if "parameters" not in payload:
        return deepcopy(payload), {}
    parameters = payload["parameters"]
    if not isinstance(parameters, dict) or len(parameters) > 128:
        raise ValueError("/parameters：须为至多 128 个参数的对象")
    reserved = {"facts", "pi", *_FUNCTIONS}
    if any(not isinstance(name, str) or not _NAME.fullmatch(name) or name in reserved for name in parameters):
        raise ValueError("/parameters：参数名使用英文字母开头的标识符，不能覆盖 facts/pi/函数")
    values, active = {}, set()
    visited, repeats, expressions = 0, 0, 0

    def charge(count=1):
        nonlocal visited
        visited += count
        if visited > MAX_VALUES:
            raise ValueError(f"展开超过 {MAX_VALUES} 个 JSON 值；缩小当前声明，不能截断产物")

    def number(value):
        if type(value) not in (int, float) or not math.isfinite(value) or abs(value) > 1e12:
            raise ValueError("计算值须为有限数字且绝对值不超过 1e12")
        return value

    def lookup(name, scope):
        if name in scope:
            return scope[name]
        if name == "facts":
            return facts or {}
        if name == "pi":
            return math.pi
        if name not in parameters:
            raise ValueError(f"未声明参数 {name}")
        if name in active:
            raise ValueError(f"/parameters/{name}：参数循环依赖")
        if name not in values:
            active.add(name)
            values[name] = walk(parameters[name], {}, "/parameters/" + name, 0)
            active.remove(name)
        return values[name]

    def evaluate(node, scope):
        charge()
        if isinstance(node, ast.Constant) and type(node.value) in (int, float, str):
            return number(node.value) if type(node.value) is not str else node.value
        if isinstance(node, ast.Name):
            return lookup(node.id, scope)
        if isinstance(node, (ast.Attribute, ast.Subscript)):
            container = evaluate(node.value, scope)
            key = node.attr if isinstance(node, ast.Attribute) else evaluate(node.slice, scope)
            if isinstance(container, dict) and isinstance(key, str) and not key.startswith("_"):
                if key not in container:
                    raise ValueError(f"事实或参数没有字段 {key}")
                return container[key]
            if isinstance(container, list) and type(key) is int and 0 <= key < len(container):
                return container[key]
            raise ValueError("只能读取存在的 JSON 字段或非负数组下标")
        if isinstance(node, ast.BinOp) and type(node.op) in _OPERATORS:
            return number(_OPERATORS[type(node.op)](number(evaluate(node.left, scope)), number(evaluate(node.right, scope))))
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            return number(evaluate(node.operand, scope)) * (-1 if isinstance(node.op, ast.USub) else 1)
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id in _FUNCTIONS and not node.keywords and len(node.args) <= 8):
            return number(_FUNCTIONS[node.func.id](*(number(evaluate(a, scope)) for a in node.args)))
        raise ValueError("表达式仅支持数值运算、数学函数与只读事实引用")

    def literal(value, depth=0):
        # 引用是数据，不把引用中的字符串作为第二段表达式执行。
        charge()
        if depth > 48:
            raise ValueError("JSON 嵌套超过 48 层")
        if isinstance(value, dict):
            return {key: literal(child, depth+1) for key, child in value.items()}
        if isinstance(value, list):
            return [literal(child, depth+1) for child in value]
        if type(value) in (int, float):
            number(value)
        if value is not None and type(value) not in (int, float, str, bool):
            raise ValueError("事实引用必须是 JSON 值")
        return value

    def walk(value, scope, path, depth):
        nonlocal repeats, expressions
        charge()
        if depth > 48:
            raise ValueError(f"{path}：JSON 嵌套超过 48 层")
        try:
            if isinstance(value, str):
                if value.startswith("="):
                    expression = value[1:].strip()
                    if len(expression) > 512:
                        raise ValueError("表达式超过 512 字符")
                    tree = ast.parse(expression, mode="eval")
                    if sum(1 for _ in ast.walk(tree)) > 128:
                        raise ValueError("表达式过于复杂")
                    expressions += 1
                    return literal(evaluate(tree.body, scope))
                def interpolate(match):
                    tree = ast.parse(match[1], mode="eval")
                    scalar = evaluate(tree.body, scope)
                    if type(scalar) not in (str, int, float):
                        raise ValueError("${变量} 只允许字符串或数字")
                    return str(scalar)
                return re.sub(r"\$\{([^{}]{1,256})\}", interpolate, value)
            if isinstance(value, list):
                result = []
                for index, item in enumerate(value):
                    item_path = f"{path}/{index}"
                    if isinstance(item, dict) and "$repeat" in item:
                        repeat = item["$repeat"]
                        if (set(item) != {"$repeat"} or not isinstance(repeat, dict)
                                or set(repeat)-{"count", "items", "var", "value", "values"}
                                or ("value" in repeat) == ("values" in repeat)
                                or ("count" in repeat) == ("items" in repeat)):
                            raise ValueError(f"{item_path}/$repeat：需要 value 或 values，以及 count 或 items")
                        name = repeat.get("var", "i")
                        if (not isinstance(name, str) or not _NAME.fullmatch(name)
                                or name in reserved or name in parameters or name in scope):
                            raise ValueError(f"{item_path}/$repeat/var：不能覆盖已有变量")
                        key = "count" if "count" in repeat else "items"
                        source = walk(repeat[key], scope, item_path+"/$repeat/"+key, depth+1)
                        if key == "count":
                            if type(source) is not int or not 0 <= source <= MAX_ITEMS:
                                raise ValueError(f"重复次数须为 0～{MAX_ITEMS} 的整数")
                            source = range(source)
                        elif not isinstance(source, list):
                            raise ValueError("重复 items 须为数组")
                        repeats += len(source)
                        if repeats > MAX_ITEMS:
                            raise ValueError(f"重复展开总数超过 {MAX_ITEMS}，不能截断产物")
                        template_key = "value" if "value" in repeat else "values"
                        for child in source:
                            expanded = walk(repeat[template_key], {**scope, name: child}, item_path+"/$repeat/"+template_key, depth+1)
                            if template_key == "values":
                                if not isinstance(expanded, list):
                                    raise ValueError("重复 values 必须为数组")
                                result.extend(expanded)
                            else:
                                result.append(expanded)
                    else:
                        result.append(walk(item, scope, item_path, depth+1))
                return result
            if isinstance(value, dict):
                if "$repeat" in value:
                    raise ValueError("$repeat 只能作为数组项")
                return {key: walk(child, scope, f"{path}/{key}", depth+1) for key, child in value.items()}
            return literal(value)
        except (ValueError, TypeError, ArithmeticError, SyntaxError, RecursionError) as exc:
            raise ValueError(f"{path or '/'}：{exc}") from exc

    for name in parameters:
        lookup(name, {})
    result = walk({k: v for k, v in payload.items() if k != "parameters"}, {}, "", 0)
    from hashlib import sha256
    fingerprint = lambda data: sha256(json.dumps(data, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest()
    return result, {"version": PARAMETRIC_VERSION, "input_hash": fingerprint(payload),
                    "facts_hash": fingerprint(facts or {}),
                    "output_hash": fingerprint(result), "expressions": expressions,
                    "repeated_items": repeats, "expanded_values": visited}


PARAMETRIC_PROTOCOL = """
计算与重复展开：在当前对象顶层声明 parameters（不用参数也可写 {}），开启程序计算。
参数值可引用其他参数；字段值用 "=表达式" 引用参数、facts 中的只读事实或进行 + - * / // % 运算。
JSON 数值位置不能裸写算式；即使只涉及常数，也必须写成以 = 开头的字符串或已算好的数字。
表达式的第一个字符必须是 =；负值写 "=-height/2"，不写 "-=height/2"。
支持 min/max/abs/round/ceil/floor/sqrt/sin/cos/tan/atan2/hypot/radians/degrees 和 pi；角度函数用弧度。
字典字段用 .字段 或 ["字段"]，数组用 [非负下标]；只能引用实际提供的数据，不猜测字段。
数组重复项：{"$repeat":{"count":数量,"var":"i","value":单项}}，i 从 0 开始。
或用 items:"=facts.某数组" 替代 count，var 指向每个数组项。每轮输出多项时用 values:[...] 替代 value，结果平铺；可嵌套，变量名不能重用。
ID 用 "构件_${i}"，对象项可用 "构件_${item.id}"；不要手抄一长串重复几何。总重复项上限 4096，程序不会截断。
例如 {"parameters":{"width":4,"n":5},"positions":[{"$repeat":{"count":"=n","var":"i",
"value":{"id":"bar_${i}","x":"=-width/2+i*width/(n-1)"}}}]}。
程序先展开为普通 JSON，再进入原有校验；没有 parameters 的旧 JSON 仍可直接提交。
"""
