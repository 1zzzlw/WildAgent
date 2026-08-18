"""
领域配置加载器

负责加载和管理领域 Schema 配置
"""
import yaml
from pathlib import Path
from typing import Any
from loguru import logger


class DomainConfig:
    """领域配置管理器"""
    
    def __init__(self, config_path: str | Path | None = None):
        """
        Args:
            config_path: 配置文件路径，默认为 config/domain_schema.yaml
        """
        if config_path is None:
            # 默认路径
            config_path = Path(__file__).parent.parent.parent / "config" / "domain_schema.yaml"
        
        self.config_path = Path(config_path)
        self._schema: dict[str, Any] | None = None
        self._load_schema()
    
    def _load_schema(self):
        """加载 YAML 配置"""
        try:
            if not self.config_path.exists():
                logger.warning(
                    f"[领域配置] 配置文件不存在: {self.config_path}，使用默认配置"
                )
                self._schema = self._default_schema()
                return
            
            with open(self.config_path, 'r', encoding='utf-8') as f:
                # 只读取第一个 YAML 文档（忽略示例部分）
                self._schema = yaml.safe_load(f)
            
            logger.info(
                f"[领域配置] 加载成功: {self._schema.get('domain', '未知')}, "
                f"{len(self._schema.get('entity_types', []))} 个实体类型"
            )
            
        except Exception as e:
            logger.error(f"[领域配置] 加载失败: {e}，使用默认配置")
            self._schema = self._default_schema()
    
    def _default_schema(self) -> dict:
        """默认 schema（通用）"""
        return {
            "domain": "generic",
            "entity_types": [],
            "attributes": [],
            "features": [],
            "constraints": {}
        }
    
    def get_schema(self) -> dict:
        """获取完整 schema"""
        return self._schema or {}
    
    def get_domain(self) -> str:
        """获取领域名称"""
        return self.get_schema().get("domain", "generic")
    
    def get_entity_types(self) -> list[dict]:
        """获取实体类型列表"""
        return self.get_schema().get("entity_types", [])
    
    def get_attributes(self) -> list[dict]:
        """获取属性列表"""
        return self.get_schema().get("attributes", [])
    
    def get_features(self) -> list[dict]:
        """获取特性列表"""
        return self.get_schema().get("features", [])
    
    def get_constraints(self) -> dict:
        """获取约束配置"""
        return self.get_schema().get("constraints", {})
    
    def get_entity_constraint(self, entity_type: str) -> dict:
        """
        获取特定实体类型的约束
        
        Args:
            entity_type: 实体类型名称
            
        Returns:
            约束字典
        """
        constraints = self.get_constraints()
        return constraints.get(entity_type, {})
    
    def find_entity_type(self, query: str) -> str | None:
        """
        根据查询字符串查找匹配的实体类型
        
        Args:
            query: 查询字符串（可能是别名）
            
        Returns:
            标准实体类型名称，未找到返回 None
        """
        query_lower = query.lower()
        
        for entity in self.get_entity_types():
            entity_type = entity.get("type", "")
            
            # 精确匹配
            if entity_type.lower() == query_lower:
                return entity_type
            
            # 别名匹配
            aliases = entity.get("aliases", [])
            if any(alias.lower() == query_lower for alias in aliases):
                return entity_type
        
        return None
    
    def get_attribute_aliases(self, attr_name: str) -> dict:
        """
        获取属性的别名映射
        
        Args:
            attr_name: 属性名称
            
        Returns:
            别名映射字典 {value: [aliases]}
        """
        for attr in self.get_attributes():
            if attr.get("name") == attr_name:
                return attr.get("aliases", {})
        
        return {}
    
    def reload(self):
        """重新加载配置"""
        self._load_schema()


# 全局单例
_domain_config: DomainConfig | None = None


def get_domain_config(config_path: str | Path | None = None) -> DomainConfig:
    """
    获取全局领域配置实例
    
    Args:
        config_path: 配置文件路径（可选，首次调用时设置）
        
    Returns:
        DomainConfig 实例
    """
    global _domain_config
    
    if _domain_config is None:
        _domain_config = DomainConfig(config_path)
    
    return _domain_config
