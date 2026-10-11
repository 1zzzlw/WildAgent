"""设计字段归属，仅供局部修订定位，不调度独立模型调用。"""
from dataclasses import dataclass


@dataclass(frozen=True)
class DesignBlock:
    name: str
    fields: tuple[str, ...]


DESIGN_BLOCKS = (
    DesignBlock("intent", ("concept", "design_intent", "design_constraints", "design_rationale")),
    DesignBlock("massing", ("massing", "volumes")),
    DesignBlock("structure", ("structural_grid", "circulation")),
    DesignBlock("facade", ("facades", "curtain_wall")),
    DesignBlock("roof", ("roof",)),
    DesignBlock("components", ("components", "materials", "detail_packages")),
)


def ordered_blocks(_level):
    return DESIGN_BLOCKS


def block_of_field(field):
    return next((b for b in DESIGN_BLOCKS if field in b.fields), None)


def block_of_design_field(field):
    return block_of_field(field.removeprefix("/decisions/").removeprefix("decisions.").split("/")[0].split(".")[0])
