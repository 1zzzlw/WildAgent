"""设计字段归属，仅供局部修订定位，不调度独立模型调用。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class DesignBlock:
    name: str
    fields: tuple[str, ...]


DESIGN_BLOCKS = (
    DesignBlock(
        "intent", ("concept", "design_intent", "design_constraints", "design_rationale")
    ),
    DesignBlock("massing", ("massing", "coordinate_system", "levels", "profiles", "volumes")),
    DesignBlock("structure", ("structural_grid", "systems", "slabs", "voids", "floor_layouts", "circulation")),
    DesignBlock("facade", ("walls", "facades", "curtain_wall")),
    DesignBlock("roof", ("roofs", "roof")),
    DesignBlock("components", ("components", "relations", "materials", "detail_packages")),
)


def ordered_blocks():
    return DESIGN_BLOCKS


def block_of_field(field):
    return next((b for b in DESIGN_BLOCKS if field in b.fields), None)


def block_of_design_field(field):
    return block_of_field(
        field.removeprefix("/decisions/")
        .removeprefix("decisions.")
        .split("/")[0]
        .split(".")[0]
    )
