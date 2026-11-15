"""设计与生成输入共用的基础取值类型。"""
from typing import Literal

IntentName = Literal["generate", "edit", "chat"]
TargetKind = Literal["architecture", "object"]
DetailLevel = Literal["minimal", "simple", "standard", "detailed"]
