"""`app/utils/json_extractor.py` 的提取契约（2026-10-08 事故后补）。

为什么这个文件此前一条测试都没有却值得补：它是 **11 个调用点共用的**解析入口
（设计块草稿、材质方案、物件方案、plan 策略、replan、格式恢复、RAG 质量、
构件生成…），却用手写的贪婪正则实现，且对"模型多吐一段"零容忍 —— 拿到正确
对象也会报"输出不是合法 JSON 对象"。
"""

from app.utils.json_extractor import extract_json_array, extract_json_object


# ── 事故原文：对象后面多了 `volumes:` 一行 ──


#: 与 `2026-10-08 14:32:52` 那条 ERROR 日志逐字一致（含被日志截断的尾部）。
INCIDENT_TEXT = (
    '{"shape": "l_shape", "width": 20.0, "depth": 15.0, "floors": 2,'
    ' "modeled_floors": 2, "representation_mode": "full", "floor_height": 3.0,'
    ' "symmetry": false, "tiers": null}\nvolumes: [{"id": "main_volume'
)


def test_incident_text_yields_the_object_instead_of_none():
    """事故原文必须能提取出那个对象。

    旧实现：`re.findall(r"\\{[\\s\\S]*\\}")` 贪婪 ⇒ 跨度 = "第一个 `{` 到最后一个
    `}`" ⇒ 横跨"正确对象 + volumes 一行" ⇒ `Extra data: line 2 column 1` ⇒ 返回
    None ⇒ `design_workflow` 判"输出不是合法 JSON 对象"并白烧一轮重出。
    """

    parsed = extract_json_object(INCIDENT_TEXT)

    assert isinstance(parsed, dict), "正确对象就在最前面，不该提取失败"
    assert parsed["shape"] == "l_shape"
    assert parsed["width"] == 20.0
    assert parsed["tiers"] is None  # 显式 null 要保留，不能被当成缺失


def test_first_object_wins_even_when_a_later_one_is_longer():
    """取**第一个**可用对象，不是最长的那段。

    旧 `max(matches, key=len)` 的意图是"多个候选里取最大的那个载荷"，但贪婪正则
    根本产不出多个候选（只有一个横跨两段的跨度）—— 于是"取最长"只在**横跨垃圾**
    这个错误方向上起作用。这里钉住方向：答案在最前面就先返回它，
    哪怕后面那段更长（模型把 `volumes` 也吐了出来，正是本次事故的形态）。
    """

    text = (
        '{"shape": "l_shape", "width": 20.0}\n'
        'volumes: [{"id": "main_volume", "x": 0.0, "z": 0.0, "width": 20.0,'
        ' "depth": 15.0, "start_floor": 1, "end_floor": 2}]'
    )

    assert extract_json_object(text) == {"shape": "l_shape", "width": 20.0}


def test_object_followed_by_prose_is_still_extracted():
    text = '{"concept": "双层中式别墅"}\n\n以上就是本轮的体量设计说明。'

    assert extract_json_object(text) == {"concept": "双层中式别墅"}


def test_truncated_follow_up_does_not_poison_the_answer():
    """后面那段**本身不合法**（被截断）时也要拿到前面那个完整对象。"""

    text = '{"shape": "rectangle"}\n{"facades": {"front": {"bays": 2'

    assert extract_json_object(text) == {"shape": "rectangle"}


# ── 围栏与正文的相对位置 ──


def test_fenced_object_with_surrounding_prose():
    text = (
        "我来给出本轮的体量：\n\n"
        '```json\n{"shape": "u_shape", "width": 24.0}\n```\n\n'
        "其中 width 是总面宽。"
    )

    assert extract_json_object(text) == {"shape": "u_shape", "width": 24.0}


def test_prose_object_does_not_beat_the_fenced_answer():
    """正文里顺带提到的对象不能被当成答案（先扫围栏、再扫全文）。"""

    text = (
        '先说结论：例如 {"note": "草稿"} 这种形式是不完整的。\n\n'
        '```json\n{"shape": "l_shape", "width": 20.0}\n```'
    )

    assert extract_json_object(text) == {"shape": "l_shape", "width": 20.0}


def test_answer_in_a_later_fence_is_found():
    """第一个围栏只是分析（没有 JSON），答案在第二个围栏 —— 不能一无所获。"""

    text = (
        "```text\n先算面宽：20m，进深 15m。\n```\n\n"
        '```json\n{"width": 20.0, "depth": 15.0}\n```'
    )

    assert extract_json_object(text) == {"width": 20.0, "depth": 15.0}


# ── 边界 ──


def test_empty_object_is_skipped_in_favour_of_the_real_payload():
    """`{}` 不是有效载荷（调用方一律判空），跳过它继续往后扫。

    注意 `{"draft": {}}` **不**算空对象 —— 它有键，是模型真表态的内容，
    照常返回。
    """

    assert extract_json_object('{}\n{"shape": "rectangle"}') == {"shape": "rectangle"}
    assert extract_json_object('{"draft": {}}') == {"draft": {}}


def test_only_an_empty_object_returns_none():
    assert extract_json_object("{}") is None


def test_nested_object_is_returned_whole():
    text = '{"massing": {"shape": "l_shape", "floors": 2}, "roof": {"type": "flat"}}'

    parsed = extract_json_object(text)
    assert parsed is not None
    assert parsed["massing"]["shape"] == "l_shape"
    assert parsed["roof"] == {"type": "flat"}


def test_brace_inside_a_string_does_not_confuse_the_scanner():
    text = '{"note": "用 { 表示开始", "shape": "rectangle"}'

    parsed = extract_json_object(text)
    assert parsed is not None
    assert parsed["shape"] == "rectangle"


def test_invalid_text_returns_none_without_raising():
    assert extract_json_object("这里没有任何 JSON，只有说明文字。") is None
    assert extract_json_object('{"shape": "l_shape"') is None


# ── 数组路径同样受同一类 bug 影响 ──


def test_array_with_trailing_prose_is_extracted():
    text = '[{"id": "door_01"}, {"id": "window_01"}]\n以上是两个构件。'

    assert extract_json_array(text) == [{"id": "door_01"}, {"id": "window_01"}]


def test_array_with_nested_arrays_is_not_split():
    text = '[[1, 2], [3, 4]] 后续还有说明 [备注]'

    assert extract_json_array(text) == [[1, 2], [3, 4]]


def test_empty_array_is_a_legitimate_answer_and_stays_empty():
    """`[]` 是"本次没有片段"，不能被跳过、也不能变成别的数组。

    与对象路径的取舍不同（对象跳过 `{}`）：空数组对构件生成是**有意义的**答案，
    旧实现在这种情况下返回的也正是 `[]`，不改它的语义。
    """

    assert extract_json_array("[]\n本次没有可生成的片段。") == []
    assert extract_json_array("[]\n[{\"id\": \"x\"}]") == []


def test_fenced_array_with_leading_prose():
    text = '```json\n[{"id": "railing_01"}]\n```\n共一条。'

    assert extract_json_array(text) == [{"id": "railing_01"}]


def test_invalid_array_returns_empty_list():
    assert extract_json_array("没有数组") == []
