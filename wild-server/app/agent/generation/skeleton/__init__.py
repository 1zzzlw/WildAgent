"""骨架域：骨架生成节点与骨架输出的解析/摘要。

节点入口 ``skeleton_generator`` 见 :mod:`.workflow`（不在此 re-export）。
"""
from __future__ import annotations

from .output import build_skeleton_summary

__all__ = ["build_skeleton_summary"]
