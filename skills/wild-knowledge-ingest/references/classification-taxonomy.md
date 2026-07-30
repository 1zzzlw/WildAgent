# Classification Taxonomy

Use this reference after reading a source document and before editing `wild-server/storage/knowledge_base`.

## Directory Routing

| Target | Use For | Typical Files |
|---|---|---|
| `building_types/catalog/` | Lightweight defaults for fuzzy building-name requests such as villa, cabin, pavilion, courtyard, tower | `villas.md`, `cabins.md`, `pavilions.md` |
| `building_types/residential/` | Villas, houses, apartments, dormitories, hotels, courtyard homes | `villas.md`, `housing-dormitories-hotels.md` |
| `building_types/public/` | Schools, offices, museums, theaters, malls, stadiums, hospitals, stations, civic buildings | split by stable public-building group |
| `building_types/industrial/` | Factories, warehouses, industrial upstairs, workshops | `factories-and-warehouses.md` |
| `building_types/agricultural/` | Greenhouses, livestock buildings, granaries, agricultural stations | `agricultural-buildings.md` |
| `components/` | Reusable elements: walls, doors, windows, roofs, eaves, columns, beams, stairs, railings, furniture, fixtures, facade parts, materials | one component family per file |
| `recipes/` | Assembly order, type matrices, style matching, default generation templates, cross-component rules that explain how buildings combine components | one strategy or matrix per file |
| `patterns/` | User-approved cases, project preferences, reusable examples, non-universal knowledge from later interactions | one case or pattern per file |

## Component File Suggestions

Create these files only when needed:

| Topic | Suggested File |
|---|---|
| Furniture, fixtures, interior props | `components/furniture-and-fixtures.md` |
| Stairs, ramps, railings, guardrails | `components/stairs-ramps-railings.md` |
| Columns, beams, trusses, slabs | `components/structural-components.md` |
| Materials, surfaces, color palettes | `components/materials-and-surfaces.md` |
| Facade ornaments, cornices, eaves, canopies | `components/facade-and-eaves.md` or extend `components/roofs-and-eaves.md` |
| Outdoor ground, courtyards, terrain, landscape | `components/site-and-landscape.md` |

## Split vs Merge Decision

Split the source when it contains independent retrieval intents. Example: a document with "中式门", "漏窗", and "四合院" should update `components/doors.md`, `components/windows.md`, and `building_types/residential/villas.md` or a courtyard file.

Use `building_types/catalog/` only for short default entries. If the content has detailed dimensions, full component tables, construction logic, or multiple variants, route it to a deeper `building_types/<use>/` file instead.

Merge into an existing file when the target topic already exists and the new content only adds variants, parameters, or examples.

Create a new file when the source has a stable topic that would make the existing file too broad, such as a full "医院建筑" guide or a full "家具构件体系" guide.

## Keyword Hygiene

Each new or heavily edited file should include a short `RAG 关键词` line near the top. Include:

- Chinese names and common aliases.
- WILD `type` names when known.
- Style names, building names, and component names.
- Parameter names that users are likely to ask about.
