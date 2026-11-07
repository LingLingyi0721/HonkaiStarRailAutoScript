"""导航：主界面 → 指南 → 模式选择（判定分支）。

阶段范围：点击指南入口 → 旷宇纷争 → 前往参与 → 货币战争 → 模式选择界面。
结束状态：识别出「进入标准博弈」(mode) 或「继续对局」(mode_continue)，
         写入 CURRENT_MODE，由 main.py 决定后续阶段。
兜底：导航段每 3 秒识别一次共 5 次，未命中则点击并比对左上角 40x40 区域判断界面是否切换。

前置：launch.py 已到达游戏主界面。
后续：mode → rank.py；mode_continue → 继续对局流程（未实现，见 TASK.md）。
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

from common import (
    setup_logging, ensure_device, tap,
    proceed_to_next, check_template_by_name,
)

# ── 配置 ────────────────────────────────────────────────────────────

CACHE_SCREENSHOT = Path("tmp/navigate_screenshot.png")

# 游戏主界面 → 指南入口
GUIDE_ENTRY = (1010, 40)

# 指南界面（图片模板匹配）
GUIDE_AREA = (1210, 530, 1240, 560)
WAR_ENTRY = (372, 115)


# 前往参与按钮（图片模板匹配）
ENTER_AREA = (1000, 605, 1085, 630)
ENTER_TAP = (1042, 617)

# 货币战争主界面（图片模板匹配）
WAR_MAIN_AREA = (965, 633, 1105, 663)
START_TAP = (1115, 645)

# 模式选择界面（图片模板匹配）：进入标准博弈 / 继续对局，两个按钮位置不同
MODE_AREA = (980, 628, 1110, 650)             # mode.png
MODE_CONTINUE_AREA = (1045, 625, 1135, 650)   # mode_continue.png
MODE_ENTER_TAP = (1115, 645)

# 当前对局判定结果："mode"（进入标准博弈）/ "mode_continue"（继续对局）
CURRENT_MODE: str | None = None

log = setup_logging("navigate")


# ── 主流程 ─────────────────────────────────────────────────────────

def run() -> int:
    """导航到模式选择界面并判定分支。

    结束状态写入 CURRENT_MODE：
        "mode"          已点击进入标准博弈
        "mode_continue" 检测到继续对局（不点击，交由编排层处理）
    """
    log.info("navigate start")

    global CURRENT_MODE
    CURRENT_MODE = None

    try:
        ensure_device(log)
    except Exception as e:
        log.error(f"device connect failed: {e}")
        return 1

    start_time = time.time()

    # ── 1. 点击指南入口 → 等待指南界面 ──
    log.info("stage 1: wait guide")
    tap(log, *GUIDE_ENTRY)
    time.sleep(2.0)
    if not proceed_to_next(
        log, None, GUIDE_ENTRY, "guide",
        cache_path=CACHE_SCREENSHOT,
        template=("navigate", GUIDE_AREA),
    ):
        return 1
    tap(log, *WAR_ENTRY)
    time.sleep(2.0)

    # ── 2. 等待前往参与按钮 → 点击前往参与 ──
    log.info("stage 2: wait enter")
    if not proceed_to_next(
        log, None, None, "enter",
        cache_path=CACHE_SCREENSHOT,
        template=("navigate", ENTER_AREA),
    ):
        return 1
    tap(log, *ENTER_TAP)
    time.sleep(2.0)

    # ── 3. 等待货币战争主界面 → 点击开始按钮 ──
    log.info("stage 3: wait war_main")
    if not proceed_to_next(
        log, None, ENTER_TAP, "war_main",
        cache_path=CACHE_SCREENSHOT,
        template=("navigate", WAR_MAIN_AREA),
    ):
        return 1
    tap(log, *START_TAP)
    time.sleep(2.0)

    # ── 4. 等待模式选择界面：先判「进入标准博弈」，不中再判「继续对局」──
    log.info("stage 4: wait mode")
    mode_hits: list[str] = []

    def _probe_mode(image):
        if check_template_by_name(log, image, "mode", "navigate", MODE_AREA):
            mode_hits.append("mode")
            return True
        if check_template_by_name(log, image, "mode_continue", "navigate", MODE_CONTINUE_AREA):
            mode_hits.append("mode_continue")
            return True
        return False

    if not proceed_to_next(
        log, None, START_TAP, "mode",
        cache_path=CACHE_SCREENSHOT,
        probe=_probe_mode,
    ):
        return 1

    # 兜底路径（未识别到模板但点击后界面已切换）视为进入标准博弈
    CURRENT_MODE = mode_hits[0] if mode_hits else "mode"
    log.info(f"stage 4: mode kind = {CURRENT_MODE}")

    if CURRENT_MODE == "mode_continue":
        log.warning("mode_continue detected: resume-game flow not implemented")
        # TODO: 读取对局记录 → 通知 AI 决策层 → 等待对应对局对策（见 TASK.md）
        return 0

    # 进入标准博弈
    tap(log, *MODE_ENTER_TAP)
    time.sleep(2.0)

    log.info(f"navigate done: mode={CURRENT_MODE} ({time.time() - start_time:.1f}s)")
    return 0


if __name__ == "__main__":
    sys.exit(run())