# WILD 知识库索引

> 本目录下除 `BLUEPRINT-SPEC-MINIMAL.md` 外，所有 Markdown 都会被 `collect_markdown_paths()` 自动扫描并进入 RAG 分片。
> Markdown 链接不会被自动追踪；需要参与召回的内容必须实际放在本目录或子目录下。

## 目录职责

| 目录 / 文件 | 存放内容 | 建议粒度 |
|---|---|---|
| `BLUEPRINT-SPEC-MINIMAL.md` | 基础蓝图铁律，直接注入 System Prompt | 小而稳定，不放风格知识 |
| `BLUEPRINT-SPEC-FULL.md` | 完整 .wild 表达规范 | 完整规范，参与 RAG |
| `building_types/catalog/` | 轻量建筑类型默认语义参考 | 用户只说“别墅/木屋/凉亭/塔楼”时的默认入口 |
| `building_types/` | 按建筑用途分类的构件配方 | 一个文件对应一个建筑主题或小类集合 |
| `components/` | 按构件族分类的参数、变体、组装规则 | 一个文件对应墙/门/窗/屋顶等构件族 |
| `recipes/` | 跨构件组装模板和速查矩阵 | 说明一个建筑如何搭配和组装多个构件 |
| `patterns/` | 用户确认后的项目案例、偏好和可复用模式 | 一个条目一个 Markdown |

## 新增文档模板

```md
# 主题名称

> 来源：手工维护 / 用户确认 / 规范整理。
> 用途：说明这个文档回答哪类生成问题。
> RAG 关键词：关键词一、关键词二、WILD type、常见中文别名。

## 适用范围

## 构件清单

## 参数建议

## 组装规则

## 最少可行版本
```
