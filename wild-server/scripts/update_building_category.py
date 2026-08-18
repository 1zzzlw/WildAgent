"""批量为知识库文档添加 building_category 元数据"""
import re
from pathlib import Path


def add_building_category_to_frontmatter(file_path: Path) -> bool:
    """为文档添加 building_category 字段"""
    content = file_path.read_text(encoding="utf-8")
    
    # 检查是否已有 frontmatter
    frontmatter_match = re.match(r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|$)", content, re.DOTALL)
    if not frontmatter_match:
        return False
    
    frontmatter_text = frontmatter_match.group(1)
    
    # 检查是否已有 building_category
    if "building_category:" in frontmatter_text:
        return False
    
    # 根据文件路径判断建筑类型
    path_str = str(file_path).replace("\\", "/")
    
    category = None
    if "/residential/" in path_str:
        # 检查是否是底商混合类型
        if "底层商铺" in content or "底商" in content or "商业" in content:
            category = "mixed_use"
        else:
            category = "residential"
    elif "/public/" in path_str:
        # 检查具体子类型
        if "commercial" in file_path.stem or "商业" in file_path.stem or "商场" in file_path.stem or "商铺" in file_path.stem or "shopping" in file_path.stem.lower():
            category = "commercial"
        else:
            category = "public"
    elif "/industrial/" in path_str:
        category = "industrial"
    elif "/agricultural/" in path_str:
        category = "agricultural"
    elif "/catalog/" in path_str:
        # 分类目录文档不添加具体 category
        return False
    
    if not category:
        return False
    
    # 在 frontmatter 中添加 building_category（在 entity_type 之后）
    lines = frontmatter_text.split("\n")
    new_lines = []
    added = False
    
    for line in lines:
        new_lines.append(line)
        if line.startswith("entity_type:") and not added:
            new_lines.append(f"building_category: {category}")
            added = True
    
    if not added:
        # 如果没有 entity_type，添加到最后
        new_lines.append(f"building_category: {category}")
    
    new_frontmatter = "\n".join(new_lines)
    new_content = content.replace(frontmatter_text, new_frontmatter, 1)
    
    # 写回文件
    file_path.write_text(new_content, encoding="utf-8")
    return True


def main():
    """批量处理所有建筑类型文档"""
    knowledge_base = Path("storage/knowledge_base/building_types")
    
    if not knowledge_base.exists():
        print(f"知识库目录不存在: {knowledge_base}")
        return
    
    updated_count = 0
    skipped_count = 0
    
    for md_file in knowledge_base.rglob("*.md"):
        if md_file.name == "README.md":
            skipped_count += 1
            continue
        
        try:
            if add_building_category_to_frontmatter(md_file):
                print(f"✅ 已更新: {md_file.relative_to(knowledge_base)}")
                updated_count += 1
            else:
                print(f"⏭️  跳过: {md_file.relative_to(knowledge_base)}")
                skipped_count += 1
        except Exception as e:
            print(f"❌ 失败: {md_file.relative_to(knowledge_base)} - {e}")
    
    print(f"\n总结: 更新 {updated_count} 个文件, 跳过 {skipped_count} 个文件")


if __name__ == "__main__":
    main()
