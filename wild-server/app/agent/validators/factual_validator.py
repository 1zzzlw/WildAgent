"""
事实自检模块 (Factual Validator)

P1 方案：验证生成的参数是否符合领域约束（领域无关）

用法:
    validator = FactualValidator(constraint_config)
    is_valid, errors = await validator.validate_entity(entity, parent_entity)
"""
from typing import Any, Callable
from loguru import logger


class FactualValidator:
    """
    事实自检：验证生成的参数是否符合领域约束（领域无关）
    
    约束规则从外部配置文件加载，不硬编码
    """
    
    def __init__(self, constraint_config: dict):
        """
        Args:
            constraint_config: 约束配置（从 domain_schema.yaml 加载）
                {
                    "entity_type_a": {
                        "attribute_1": {"min": 0.5, "max": 10.0},
                        "attribute_2": {"min": 1.0, "max": 5.0}
                    },
                    ...
                }
        """
        self.constraints = constraint_config
    
    async def validate_entity(
        self, 
        entity: dict, 
        parent_entity: dict | None = None,
        custom_validators: list[Callable] | None = None
    ) -> tuple[bool, list[str]]:
        """
        验证实体参数合理性（通用）
        
        Args:
            entity: 要验证的实体
            parent_entity: 父实体（可选，用于父子关系验证）
            custom_validators: 领域特定的自定义验证函数列表
            
        Returns:
            (是否通过, 错误列表)
        """
        errors = []
        entity_type = entity.get("entity_type") or entity.get("type")
        
        if entity_type not in self.constraints:
            return True, []  # 未定义约束的实体跳过
        
        type_constraints = self.constraints[entity_type]
        
        # 1. 数值范围验证（通用）
        range_errors = self._validate_ranges(entity, entity_type, type_constraints)
        errors.extend(range_errors)
        
        # 2. 枚举值验证
        enum_errors = self._validate_enums(entity, entity_type, type_constraints)
        errors.extend(enum_errors)
        
        # 3. 父子关系约束（通用）
        if parent_entity:
            parent_errors = self._validate_parent_child_constraint(
                entity, parent_entity, type_constraints
            )
            errors.extend(parent_errors)
        
        # 4. 自定义领域验证（可扩展）
        if custom_validators:
            for validator_func in custom_validators:
                try:
                    custom_errors = validator_func(entity, parent_entity)
                    if custom_errors:
                        errors.extend(custom_errors)
                except Exception as e:
                    logger.warning(f"自定义验证器执行失败: {e}")
        
        return len(errors) == 0, errors
    
    def _validate_ranges(
        self, 
        entity: dict, 
        entity_type: str,
        constraints: dict
    ) -> list[str]:
        """验证数值范围"""
        errors = []
        
        for attr, constraint in constraints.items():
            if attr.startswith("_"):  # 跳过元数据字段
                continue
            
            if attr not in entity:
                continue
            
            value = entity[attr]
            
            # 检查 min/max 约束
            if "min" in constraint and "max" in constraint:
                min_val, max_val = constraint["min"], constraint["max"]
                
                if not isinstance(value, (int, float)):
                    continue
                
                if not (min_val <= value <= max_val):
                    unit = constraint.get("unit", "")
                    errors.append(
                        f"{entity_type}.{attr}={value}{unit} "
                        f"超出范围 [{min_val}, {max_val}]{unit}"
                    )
        
        return errors
    
    def _validate_enums(
        self,
        entity: dict,
        entity_type: str,
        constraints: dict
    ) -> list[str]:
        """验证枚举值"""
        errors = []
        
        for attr, constraint in constraints.items():
            if attr.startswith("_"):
                continue
            
            if attr not in entity:
                continue
            
            value = entity[attr]
            
            # 检查 enum 约束
            if "enum" in constraint:
                allowed_values = constraint["enum"]
                if value not in allowed_values:
                    errors.append(
                        f"{entity_type}.{attr}='{value}' "
                        f"不在允许值 {allowed_values} 中"
                    )
        
        return errors
    
    def _validate_parent_child_constraint(
        self, 
        entity: dict, 
        parent: dict,
        constraints: dict
    ) -> list[str]:
        """
        验证子实体是否在父实体范围内（通用）
        
        支持配置位置字段和尺寸字段
        """
        errors = []
        
        # 从约束配置获取位置和尺寸字段名
        position_field = constraints.get("_position_field", "position")
        size_fields = constraints.get("_size_fields", ["width", "height", "depth"])
        
        # 检查位置约束
        if position_field in entity and "bounds" in parent:
            position = entity[position_field]
            parent_bounds = parent["bounds"]
            
            # 验证是否超出父实体边界
            if isinstance(position, (list, tuple)) and isinstance(parent_bounds, list):
                for i, pos_val in enumerate(position):
                    if i >= len(parent_bounds):
                        break
                    
                    bound = parent_bounds[i]
                    if isinstance(bound, dict) and "min" in bound and "max" in bound:
                        if pos_val < bound["min"] or pos_val > bound["max"]:
                            errors.append(
                                f"{entity.get('type')} 位置 {position_field}[{i}]={pos_val} "
                                f"超出父实体范围 [{bound['min']}, {bound['max']}]"
                            )
        
        # 检查尺寸约束
        for size_field in size_fields:
            if size_field in entity:
                size_value = entity[size_field]
                parent_size_field = f"max_{size_field}"
                
                if parent_size_field in parent:
                    max_size = parent[parent_size_field]
                    if isinstance(size_value, (int, float)) and isinstance(max_size, (int, float)):
                        if size_value > max_size:
                            errors.append(
                                f"{entity.get('type')}.{size_field}={size_value} "
                                f"超过父实体的 {max_size}"
                            )
        
        return errors
    
    async def auto_correct(
        self, 
        entity: dict, 
        errors: list[str],
        correction_strategy: str = "clamp"
    ) -> dict:
        """
        自动修正不合理的参数（通用）
        
        Args:
            entity: 要修正的实体
            errors: 错误列表
            correction_strategy: 修正策略
                - "clamp": 钳位到范围边界
                - "default": 使用默认值
                - "remove": 移除违规字段
                
        Returns:
            修正后的实体
        """
        entity_type = entity.get("entity_type") or entity.get("type")
        type_constraints = self.constraints.get(entity_type, {})
        
        if correction_strategy == "clamp":
            # 钳位策略：将值限制在合法范围内
            for attr, constraint in type_constraints.items():
                if attr.startswith("_"):
                    continue
                
                if attr in entity and "min" in constraint and "max" in constraint:
                    value = entity[attr]
                    
                    if not isinstance(value, (int, float)):
                        continue
                    
                    min_val, max_val = constraint["min"], constraint["max"]
                    
                    if value < min_val:
                        entity[attr] = min_val
                        logger.info(
                            f"自动修正 {entity_type}.{attr}: {value} → {min_val}"
                        )
                    elif value > max_val:
                        entity[attr] = max_val
                        logger.info(
                            f"自动修正 {entity_type}.{attr}: {value} → {max_val}"
                        )
        
        elif correction_strategy == "default":
            # 默认值策略：使用配置的默认值
            for attr, constraint in type_constraints.items():
                if attr.startswith("_"):
                    continue
                
                if "default" in constraint and attr in entity:
                    # 检查是否有错误与此字段相关
                    if any(attr in err for err in errors):
                        entity[attr] = constraint["default"]
                        logger.info(
                            f"使用默认值 {entity_type}.{attr} → {constraint['default']}"
                        )
        
        elif correction_strategy == "remove":
            # 移除策略：删除违规字段
            for error in errors:
                # 从错误消息中提取字段名
                for attr in type_constraints.keys():
                    if attr.startswith("_"):
                        continue
                    if attr in error and attr in entity:
                        del entity[attr]
                        logger.info(f"移除违规字段 {entity_type}.{attr}")
                        break
        
        return entity
    
    def validate_batch(
        self,
        entities: list[dict],
        parent_entity: dict | None = None
    ) -> tuple[list[dict], list[dict], dict]:
        """
        批量验证实体
        
        Args:
            entities: 实体列表
            parent_entity: 父实体
            
        Returns:
            (通过的实体列表, 失败的实体列表, 统计信息)
        """
        valid_entities = []
        invalid_entities = []
        stats = {
            "total": len(entities),
            "valid": 0,
            "invalid": 0,
            "error_types": {}
        }
        
        for entity in entities:
            # 同步调用（批量验证不使用 async）
            import asyncio
            is_valid, errors = asyncio.run(
                self.validate_entity(entity, parent_entity)
            )
            
            if is_valid:
                valid_entities.append(entity)
                stats["valid"] += 1
            else:
                invalid_entities.append({
                    "entity": entity,
                    "errors": errors
                })
                stats["invalid"] += 1
                
                # 统计错误类型
                for error in errors:
                    # 简单分类
                    if "超出范围" in error:
                        error_type = "range_violation"
                    elif "不在允许值" in error:
                        error_type = "enum_violation"
                    elif "超出父实体" in error:
                        error_type = "parent_constraint_violation"
                    else:
                        error_type = "other"
                    
                    stats["error_types"][error_type] = \
                        stats["error_types"].get(error_type, 0) + 1
        
        return valid_entities, invalid_entities, stats
