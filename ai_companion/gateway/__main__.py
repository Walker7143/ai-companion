"""
Gateway 模块入口 - 支持 python -m ai_companion.gateway 直接执行
"""

import asyncio
import logging
import sys
from pathlib import Path

# 添加项目根目录和 vendor 目录到 path
_project_root = Path(__file__).parent.parent.parent.parent
_vendor_dir = _project_root / "ai_companion" / "_vendor"
sys.path.insert(0, str(_project_root))
sys.path.insert(0, str(_vendor_dir))

from ai_companion.gateway.cmd import run_gateway

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )
    asyncio.run(run_gateway())
