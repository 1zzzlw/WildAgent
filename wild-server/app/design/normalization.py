"""Field evidence for normalization; diagnostics, never a second design input."""
from copy import deepcopy
from typing import Any


def field_changes(before: Any, after: Any, *, path: str = "", rule: str,
                  source: str = "unknown") -> list[dict]:
    changes = []

    def visit(old, new, target, old_exists=True, new_exists=True):
        if (old_exists and new_exists and isinstance(old, (int, float)) and not isinstance(old, bool)
                and isinstance(new, (int, float)) and not isinstance(new, bool) and old == new):
            return
        if old_exists and new_exists and old == new and type(old) is type(new) and not isinstance(old, dict):
            return
        if target in {"/geometry/elements", "/geometry/components"} and isinstance(old, list) and isinstance(new, list):
            old_by_id = {e.get("id"): e for e in old if isinstance(e, dict)}
            new_by_id = {e.get("id"): e for e in new if isinstance(e, dict)}
            if None not in old_by_id and None not in new_by_id and len(old_by_id) == len(old) and len(new_by_id) == len(new):
                for entity_id in sorted(old_by_id.keys() | new_by_id.keys()):
                    visit(old_by_id.get(entity_id), new_by_id.get(entity_id),
                          target+"/"+str(entity_id).replace("~", "~0").replace("/", "~1"),
                          entity_id in old_by_id, entity_id in new_by_id)
                return
        if isinstance(old, dict) and isinstance(new, dict) and old_exists and new_exists:
            for key in sorted(old.keys() | new.keys()):
                token = str(key).replace("~", "~0").replace("/", "~1")
                visit(old.get(key), new.get(key), target+"/"+token, key in old, key in new)
            return
        if not old_exists and isinstance(new, dict) and new:
            for key, value in new.items():
                token = str(key).replace("~", "~0").replace("/", "~1")
                visit(None, value, target+"/"+token, False, True)
            return
        if (isinstance(old, list) and isinstance(new, list) and len(old) == len(new)
                and all(isinstance(a, dict) and isinstance(b, dict) and a.get("id") == b.get("id")
                        for a,b in zip(old,new))):
            for index, (a,b) in enumerate(zip(old,new)):
                visit(a, b, target+f"/{index}")
            return
        # Keep lists atomic: insertion/reordering must not be misreported as field edits.
        protocol = (old_exists and new_exists and isinstance(old, str)
                    and isinstance(new, str) and old.strip().lower() == new)
        category = "default" if not old_exists else "protocol" if protocol else "semantic_change"
        changes.append({"path": target, "before": deepcopy(old), "after": deepcopy(new),
            "before_exists": old_exists, "after_exists": new_exists,
            "rule": rule, "category": category, "input_source": source if old_exists else "missing",
            "output_source": "default" if not old_exists else "program",
            "semantic_change": category == "semantic_change",
            "reason": "缺失字段补值" if not old_exists else "等价文本格式规范化" if protocol else
                      "显式值被改写或丢弃，不能视为等价修复",
            "constraint_ids": []})

    visit(before, after, path)
    return changes


def plan_changes(before, after, *, source="unknown"):
    from .contracts import ArchitectureDecisions
    # Use contract fields; plan-only derivatives are explicitly included below.
    roots = set(ArchitectureDecisions.model_fields) - {"kind", "materials", "envelope", "complexity", "design_rationale"}
    roots.add("curtain_wall")
    old = before if isinstance(before, dict) else {}
    changes = field_changes({k:v for k,v in old.items() if k in roots},
                            {k:v for k,v in after.items() if k in roots},
                            path="/decisions", rule="architecture.normalize", source=source)
    for change in changes:
        root = change["path"].split("/")[2]
        change["rule"] = "architecture.normalize." + root
        if change["semantic_change"]:
            reasons = {
                "massing": "尺寸、楼层或形状的显式值不符合约束，或与请求解析冲突",
                "volumes": "体量字段、数量、ID 或楼层覆盖需要修订；不自动推移重叠体量",
                "roof": "屋顶表达不符合当前单屋顶协议，不能无损保留",
                "facades": "立面 token、开间数量或入口索引被修订",
                "circulation": "交通策略被修订以满足当前楼层或井道关系",
                "detail_packages": "细部清单受当前层数、围护系统或既有选择规则修改",
            }
            change["reason"] = reasons.get(root, change["reason"])
        if (change["path"] == "/decisions/roof" and isinstance(change["before"], list)
                and len(change["before"]) == 1 and isinstance(change["before"][0], dict)
                and all(change["after"].get(k) == v for k,v in change["before"][0].items())):
            change.update(category="protocol", semantic_change=False, reason="单项屋顶数组无损迁移为对象")
        if change["path"].startswith("/decisions/component_quota/") or change["path"] in {
            "/decisions/required_components", "/decisions/massing/representation_mode",
        }:
            # Derived does not mean semantically harmless when replacing an explicit value.
            change["category"] = "derived"
            change["output_source"] = "program"
            change["reason"] = "从立面、屋顶和已采用构件派生；显式值冲突仍需核对"
        change["constraint_ids"] = [c["id"] for c in old.get("design_constraints") or []
            if isinstance(c, dict) and isinstance(c.get("target"), str) and c.get("id")
            and (c["target"] == change["path"] or c["target"].startswith(change["path"]+"/")
                 or change["path"].startswith(c["target"]+"/"))]
    return changes


def decision_summary(plan: dict) -> str:
    massing = plan["massing"]
    return (f"[决策事实] {massing['width']}×{massing['depth']}m；"
            f"{massing['floors']}层，表达{massing['modeled_floors']}层；"
            f"{len(plan['volumes'])}个体量；屋顶 {plan['roof']['type']}")


def approved_compilation_changes(expected: dict, actual: dict) -> list[dict]:
    """Guard existing compiled entities/materials; added execution entities remain allowed.

    This is a conservative mutation guard, not P4's complete requirement fulfillment.
    A topology replacement is not assumed equivalent just because validation passes.
    """
    def retained(old, new):
        if isinstance(old, dict) and isinstance(new, dict):
            return {k: retained(v, new[k]) for k,v in old.items() if k in new}
        if isinstance(old, list) and isinstance(new, list) and len(old) == len(new):
            return [retained(a,b) for a,b in zip(old,new)]
        if (isinstance(old, (float,int)) and not isinstance(old, bool)
                and isinstance(new, (float,int)) and not isinstance(new, bool) and abs(old-new) <= 0.001):
            return old
        return new

    changes = []
    for group in ("elements", "components"):
        old = {e["id"]: e for e in expected.get("geometry", {}).get(group, [])}
        new = {e["id"]: e for e in actual.get("geometry", {}).get(group, [])}
        changes.extend(field_changes(old, retained(old, new), path=f"/geometry/{group}",
                                     rule="approved.compilation", source="approved_design"))
    old = expected.get("materials", {})
    changes.extend(field_changes(old, retained(old, actual.get("materials", {})), path="/materials",
                                 rule="approved.compilation", source="approved_design"))
    return changes
