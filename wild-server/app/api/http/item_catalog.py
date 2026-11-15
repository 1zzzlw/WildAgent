"""物品目录 API：列出、读取、导入 WILD 物品。

物品就是一份 `.wild` asset 文件（`meta.type = "asset"`）。这里**不定义任何新几何
类型、不新增引擎能力** —— 导入 = 严格校验 + 落盘 + 进目录。这就是"新增物品不必改
渲染引擎"的落点：引擎只认 12 种基础元素，物品是数据。

两个写者分开：

- `storage/item_catalog/manifest.json` + `items/` 由
  `scripts/item_catalog/build.py` 生成（内置物品）；
- `storage/item_catalog/imported/` 由本模块写（用户导入）。

同一个 manifest 被两处写迟早冲突，所以物理分开、读取时合并。
"""

from typing import Annotated
from fastapi import APIRouter, File, UploadFile
import app.application.item_catalog as use_cases

router = APIRouter(prefix="/api/item-catalog", tags=["物品库"])


@router.get("")
async def list_items() -> dict:
    result = await use_cases.list_items()
    return result


@router.get("/{item_id}")
async def get_item(item_id: str) -> dict:
    result = await use_cases.get_item(item_id)
    return result


@router.delete("/{item_id}")
async def delete_item(item_id: str) -> dict:
    result = await use_cases.delete_item(item_id)
    return result


@router.post("/import")
async def import_item(file: Annotated[UploadFile, File()]) -> dict:
    result = use_cases.import_item(file.filename or "", await file.read(use_cases.MAX_IMPORT_BYTES + 1))
    return result

