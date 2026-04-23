"""
拒绝分类定义
"""

from enum import Enum


class RefusalCategory(Enum):
    """拒绝分类枚举"""

    # 硬红线：直接拒绝，态度强硬
    NON_NEGOTIABLE = "non_negotiable"

    # 软边界：先调整态度，可能软化
    SOFT_BOUNDARY = "soft_boundary"

    # 关系破坏者：严肃拒绝，可能影响关系
    DEAL_BREAKER = "deal_breaker"

    # 不拒绝，继续正常流程
    ALLOWED = "allowed"
