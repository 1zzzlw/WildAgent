---
name: wild-knowledge-ingest
description: Classify, merge, update, and deduplicate WildAgent knowledge-base documents for WILD generation. Use when the user provides or points to a document about a specific building, furniture/object, architectural component, construction rule, style recipe, design pattern, or any Markdown/text knowledge that should be integrated into E:\AgentProject\WildAgent\wild-server\storage\knowledge_base with automatic RAG scanning.
---

# Wild Knowledge Ingest

## Goal

Turn a supplied knowledge document into clean, searchable WildAgent knowledge-base Markdown. Preserve the source document, classify its content, merge it into the right `knowledge_base` topic files, and remove or consolidate duplicates.

## Default Paths

- Source documents may live anywhere in the workspace; do not move or rewrite them unless the user asks.
- Knowledge base root: `wild-server/storage/knowledge_base/`.
- RAG scans every `.md` under the knowledge base except `BLUEPRINT-SPEC-MINIMAL.md`.
- Keep lightweight building-name defaults in `building_types/catalog/`. Put detailed rules into classified subdirectories.

## Required Workflow

1. Read the source document and inspect its headings, tables, keywords, examples, and images.
2. Read `references/classification-taxonomy.md` before choosing target directories.
3. Run the audit script when local execution is available:

```bash
python skills/wild-knowledge-ingest/scripts/audit_knowledge_ingest.py --source <source.md> --kb-root wild-server/storage/knowledge_base
```

4. Classify each meaningful content block into one of these buckets:

- `building_types/catalog/`: lightweight default entries for fuzzy building-name requests, such as "别墅", "木屋", "凉亭", "塔楼".
- `building_types/residential|public|industrial|agricultural/`: deeper building-use recipes and variants.
- `components/`: reusable WILD components, furniture, facade parts, openings, roofs, materials, fixtures, or object families.
- `recipes/`: cross-component assembly sequences, templates, matrices, or style matching tables.
- `patterns/`: user-approved examples, project preferences, reusable cases, or knowledge that is not universal.

5. Read the likely target files before editing. If no good file exists, create one using `references/document-templates.md`.
6. Merge rather than append blindly:

- Preserve useful existing content.
- Remove exact duplicate sections.
- Merge near-duplicate lists and tables into one canonical section.
- Keep conflicting facts under `待确认` instead of silently choosing one.
- Add source/provenance lines when content came from a supplied document.

7. Update local index files when adding new files or folders:

- `knowledge_base/README.md`
- relevant subdirectory `README.md`
- `building_types/catalog/README.md` when adding or renaming lightweight building-type entries.

8. Validate before finishing:

- Confirm every new or changed Markdown file has one clear `#` title.
- Confirm code fences are balanced.
- Confirm no empty files were created.
- Confirm image links are valid, or convert broken copied image links into textual provenance notes.
- Confirm the automatic scan would include the new file and exclude only `BLUEPRINT-SPEC-MINIMAL.md`.

## Classification Rules

Use one file per stable topic, not one giant document and not one tiny file per subpart.

- A short default reference for "别墅", "木屋", "凉亭", "塔楼", or another fuzzy building name belongs in `building_types/catalog/`.
- A deeper document about "现代别墅", "医院", "温室", or "机场航站楼" belongs in the matching building-use directory under `building_types/`.
- A document about "门", "窗", "屋檐", "家具", "斗拱", "栏杆", "幕墙", "材料" belongs in `components/`.
- A document about "低层建筑组装模板", "高层核心筒流程", "门窗风格速配", or a matrix belongs in `recipes/`; this directory explains how a building combines components into an assembly strategy.
- A document about a user-confirmed case, custom prompt preference, or project-specific style belongs in `patterns/`.

If a source document spans multiple buckets, split it. Keep each output file independently useful for RAG retrieval with a title, purpose, keywords, and focused sections.

## Deduplication Rules

Normalize before comparing:

- Ignore heading numbers such as `1.1`, `X.2.3`, and Chinese numerals used as section prefixes.
- Treat common bilingual labels as equivalent when context matches, such as `窗/window`, `门/door`, `屋顶/roof`, `家具/furniture`.
- Compare headings, table headers, WILD `type` names, and distinctive quantities or parameter names.

When duplicates are found:

- Exact duplicate paragraph or table row: keep one copy.
- Same topic with richer new details: merge details into the existing canonical section.
- Same topic with contradictory dimensions or counts: keep both under `待确认`, with provenance.
- Same content in light reference and deep file: keep short summary in light reference and canonical details in the deep file.

## WILD Capability Boundary

Knowledge documents may describe what should be generated, but they must not invent legal `.wild` fields as if the engine already supports them.

- If the idea can be expressed with existing WILD types, document the mapping.
- If it needs a new type or field, mark it as `候选能力` and mention that `BLUEPRINT-SPEC-FULL.md`, validators, and `wild-core` need follow-up changes.
- Do not put unsupported fields into default generation recipes.

## Output Summary

When done, report:

- Source document processed.
- Files created or updated.
- Where each major content group was classified.
- Duplicates merged or skipped.
- Any unresolved conflicts or candidate capabilities.
- Validation performed and anything that could not be run.
