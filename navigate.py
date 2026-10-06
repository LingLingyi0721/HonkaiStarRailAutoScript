"""崩坏：星穹铁道 导航脚本。

前置条件：已通过 launch.py 启动游戏 app。

流程：
1. 等待登录界面 → 点击屏幕中央 → 等待离开登录界面
2. 等待游戏主界面 → 点击指南入口
3. 等待指南界面 → 点击旷宇纷争入口
4. 等待旷宇纷争界面 → 点击前往参与
5. 等待货币战争主界面 → 点击开始按钮
6. 等待模式选择界面 → 点击进入标准博弈
7. 等待标准博弈界面 → 记录难度 → 点击开始对局
8. 等待词条首领一览界面 → 结束

兜底机制：每个阶段截图5次未检测到目标则点击推进位置，
连续3轮失败则抛出错误。
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import cv2

from common import (
    setup_logging, ensure_device, screenshot, tap,
    check_keywords, get_rank_level, rank_to_global,
    proceed_to_next, snapshot_error,
)

# ── 配置 ────────────────────────────────────────────────────────────

CACHE_SCREENSHOT = Path("tmp/navigate_screenshot.png")

# 登录界面
LOGIN_KEYWORDS = [
    {"keyword": "点击进入", "area": (400, 600, 880, 700)},
]
SCREEN_CENTER = (640, 360)

# 游戏主界面
GAME_KEYWORDS = [
    {"keyword": "状态效果", "area": (1150, 100, 1235, 125)},
]
GUIDE_ENTRY = (1010, 40)

# 指南界面
GUIDE_KEYWORDS = [
    {"keyword": "生存索引", "area": (85, 35, 170, 60)},
]
WAR_ENTRY = (372, 115)

# 旷宇纷争界面
WAR_KEYWORDS = [
    {"keyword": "货币战争", "area": (140, 195, 240, 230)},
]
ENTER_KEYWORDS = [
    {"keyword": "前往参与", "area": (1000, 605, 1085, 630)},
]
ENTER_TAP = (1042, 617)

# 货币战争主界面
WAR_MAIN_KEYWORDS = [
    {"keyword": "货币战争", "area": (980, 625, 1085, 670)},
]
START_TAP = (1115, 645)

# 模式选择界面
MODE_KEYWORDS = [
    {"keyword": "进入标准博弈", "area": (980, 625, 1110, 650)},
]
MODE_ENTER_TAP = (1115, 645)

# 标准博弈界面
RANK_KEYWORDS = [
    {"keyword": "开始对局", "area": (1045, 630, 1130, 655)},
]
START_BATTLE_TAP = (1087, 642)

# 词条首领一览界面
NEXT_STEP_KEYWORDS = [
    {"keyword": "下一步", "area": (970, 645, 1040, 670)},
]

# 当前局难度信息（段位+层级），供决策层AI使用
CURRENT_RANK_LEVEL: str | None = None

log = setup_logging("navigate")


# ── 主流程 ─────────────────────────────────────────────────────────

def run(target_rank_level: str | None = None) -> int:
    """导航到词条首领一览界面。

    Args:
        target_rank_level: 目标段位层级，格式如 "A8-10"。
            None 表示不切换，保持当前位置。
    """
    log.info("=" * 50)
    log.info("崩坏：星穹铁道 导航阶段")
    log.info("=" * 50)

    try:
        ensure_device(log)
    except Exception as e:
        log.error(f"设备连接失败: {e}")
        return 1

    start_time = time.time()

    # ── 1. 等待登录界面 → 点击屏幕中央 ──
    if not proceed_to_next(
        log, LOGIN_KEYWORDS, None, "登录界面确认",
        cache_path=CACHE_SCREENSHOT, max_screenshots=15,
    ):
        return 1
    tap(log, *SCREEN_CENTER)
    time.sleep(2.0)

    # ── 2. 等待游戏主界面 → 点击指南入口 ──
    if not proceed_to_next(
        log, GAME_KEYWORDS, None, "游戏界面确认",
        cache_path=CACHE_SCREENSHOT, max_screenshots=15,
    ):
        return 1
    tap(log, *GUIDE_ENTRY)
    time.sleep(2.0)

    # ── 3. 等待指南界面 → 点击旷宇纷争入口 ──
    if not proceed_to_next(
        log, GUIDE_KEYWORDS, GUIDE_ENTRY, "指南界面确认",
        cache_path=CACHE_SCREENSHOT,
    ):
        return 1
    tap(log, *WAR_ENTRY)
    time.sleep(2.0)

    # ── 4. 等待旷宇纷争界面 → 点击前往参与 ──
    if not proceed_to_next(
        log, WAR_KEYWORDS, WAR_ENTRY, "旷宇纷争界面确认",
        cache_path=CACHE_SCREENSHOT,
    ):
        return 1
    if not proceed_to_next(
        log, ENTER_KEYWORDS, None, "前往参与确认",
        cache_path=CACHE_SCREENSHOT,
    ):
        return 1
    tap(log, *ENTER_TAP)
    time.sleep(2.0)

    # ── 5. 等待货币战争主界面 → 点击开始按钮 ──
    if not proceed_to_next(
        log, WAR_MAIN_KEYWORDS, ENTER_TAP, "货币战争主界面确认",
        cache_path=CACHE_SCREENSHOT,
    ):
        return 1
    tap(log, *START_TAP)
    time.sleep(2.0)

    # ── 6. 等待模式选择界面 → 点击进入标准博弈 ──
    if not proceed_to_next(
        log, MODE_KEYWORDS, START_TAP, "模式选择界面确认",
        cache_path=CACHE_SCREENSHOT,
    ):
        return 1
    tap(log, *MODE_ENTER_TAP)
    time.sleep(2.0)

    # ── 7. 等待标准博弈界面 → 记录难度 → 点击开始对局 ──
    if not proceed_to_next(
        log, RANK_KEYWORDS, MODE_ENTER_TAP, "标准博弈界面确认",
        cache_path=CACHE_SCREENSHOT,
    ):
        return 1

    # 记录难度信息
    global CURRENT_RANK_LEVEL
    image = screenshot(log, CACHE_SCREENSHOT)
    if image is not None:
        rank_info = get_rank_level(image, log)
        if rank_info:
            CURRENT_RANK_LEVEL = rank_info["combined"]
            log.info(f"当前难度: {CURRENT_RANK_LEVEL}")
        else:
            log.warning("难度信息识别失败，继续流程")

    # 段位层级切换
    if target_rank_level and rank_info and rank_info["rank"] and rank_info["level"]:
        target_rank, target_level_str = target_rank_level.split("-", 1)
        target_level = int(target_level_str)
        current_global = rank_to_global(rank_info["rank"], int(rank_info["level"]))
        target_global = rank_to_global(target_rank, target_level)
        if current_global != target_global:
            log.info(f"需要切换: {CURRENT_RANK_LEVEL} -> {target_rank_level}")
            from adjust import adjust_level
            ok = adjust_level(target_rank, target_level)
            if not ok:
                log.error(f"段位层级切换失败: {target_rank_level}")
                snapshot_error(log, "adjust_failed",
                               f"切换到 {target_rank_level} 失败",
                               {"current": CURRENT_RANK_LEVEL, "target": target_rank_level}, image)
                return 1
            image2 = screenshot(log)
            if image2 is not None:
                rank_info2 = get_rank_level(image2, log)
                if rank_info2 and rank_info2["combined"]:
                    CURRENT_RANK_LEVEL = rank_info2["combined"]
                    log.info(f"切换后难度: {CURRENT_RANK_LEVEL}")
        else:
            log.info(f"已在目标位置 {target_rank_level}，无需切换")

    # 点击开始对局
    tap(log, *START_BATTLE_TAP)
    time.sleep(2.0)

    # ── 8. 等待词条首领一览界面 → 结束 ──
    if not proceed_to_next(
        log, NEXT_STEP_KEYWORDS, START_BATTLE_TAP, "词条首领一览界面确认",
        cache_path=CACHE_SCREENSHOT,
    ):
        return 1

    log.info(f"总耗时: {time.time() - start_time:.1f}秒")
    return 0


if __name__ == "__main__":
    sys.exit(run())