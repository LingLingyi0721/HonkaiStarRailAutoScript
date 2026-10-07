"""导航至货币战争词条首领一览界面。

前置：launch.py 已启动游戏。
流程：登录 → 主界面 → 指南 → 旷宇纷争 → 货币战争 → 标准博弈 → 词条首领
兜底：启动段（登录/主界面）持续识别至超时 120 秒；
导航段（指南起）每 3 秒识别一次共 5 次，未命中则点击并比对左上角 40x40 区域判断界面是否切换。
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import cv2

from common import (
    setup_logging, ensure_device, screenshot, tap,
    get_rank_level, rank_to_global,
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

# 指南界面（图片模板匹配）
GUIDE_AREA = (1210, 530, 1240, 560)
WAR_ENTRY = (372, 115)


# 前往参与按钮（图片模板匹配）
ENTER_AREA = (1000, 605, 1085, 630)
ENTER_TAP = (1042, 617)

# 货币战争主界面（图片模板匹配）
WAR_MAIN_AREA = (965, 633, 1105, 663)
START_TAP = (1115, 645)

# 模式选择界面（图片模板匹配）
MODE_AREA = (980, 628, 1110, 650)
MODE_ENTER_TAP = (1115, 645)

# 标准博弈界面（图片模板匹配）
RANK_AREA = (1048, 632, 1130, 655)
START_BATTLE_TAP = (1087, 642)

# 词条首领一览界面（图片模板匹配）
NEXT_STEP_AREA = (970, 648, 1035, 668)
NEXT_STEP_TAP = (1002, 658)

# 第一位面过渡界面（图形匹配 + OCR"点击空白处继续"）
DIM1_TRANSITION_AREA = (168, 558, 204, 594)
DIM1_CONTINUE_KEYWORDS = [
    {"keyword": "空白处", "area": (550, 630, 740, 680)},
    {"keyword": "继续", "area": (550, 630, 740, 680)},
    {"keyword": "点击", "area": (550, 630, 740, 680)},
    {"keyword": "点击空白处继续", "area": (550, 630, 740, 680)},
]
DIM1_CONTINUE_TAP = (645, 655)

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
    log.info("navigate start")

    try:
        ensure_device(log)
    except Exception as e:
        log.error(f"device connect failed: {e}")
        return 1

    start_time = time.time()

    # ── 1. 等待登录界面（持续识别，超时120秒）→ 点击屏幕中央 ──
    log.info("stage 1: wait login")
    if not proceed_to_next(
        log, LOGIN_KEYWORDS, None, "login",
        cache_path=CACHE_SCREENSHOT, timeout=120,
    ):
        return 1
    tap(log, *SCREEN_CENTER)
    time.sleep(2.0)

    # ── 2. 等待游戏主界面（持续识别，超时120秒）→ 点击指南入口 ──
    log.info("stage 2: wait main")
    if not proceed_to_next(
        log, GAME_KEYWORDS, None, "main",
        cache_path=CACHE_SCREENSHOT, timeout=120,
    ):
        return 1
    tap(log, *GUIDE_ENTRY)
    time.sleep(2.0)

    # ── 3. 等待指南界面 → 点击旷宇纷争入口 ──
    log.info("stage 3: wait guide")
    if not proceed_to_next(
        log, None, GUIDE_ENTRY, "guide",
        cache_path=CACHE_SCREENSHOT,
        template=("ui", GUIDE_AREA),
    ):
        return 1
    tap(log, *WAR_ENTRY)
    time.sleep(2.0)

    # ── 4. 等待前往参与按钮 → 点击前往参与 ──
    log.info("stage 4: wait enter")
    if not proceed_to_next(
        log, None, None, "enter",
        cache_path=CACHE_SCREENSHOT,
        template=("ui", ENTER_AREA),
    ):
        return 1
    tap(log, *ENTER_TAP)
    time.sleep(2.0)

    # ── 5. 等待货币战争主界面 → 点击开始按钮 ──
    log.info("stage 5: wait war_main")
    if not proceed_to_next(
        log, None, ENTER_TAP, "war_main",
        cache_path=CACHE_SCREENSHOT,
        template=("ui", WAR_MAIN_AREA),
    ):
        return 1
    tap(log, *START_TAP)
    time.sleep(2.0)

    # ── 6. 等待模式选择界面 → 点击进入标准博弈 ──
    log.info("stage 6: wait mode")
    if not proceed_to_next(
        log, None, START_TAP, "mode",
        cache_path=CACHE_SCREENSHOT,
        template=("ui", MODE_AREA),
    ):
        return 1
    tap(log, *MODE_ENTER_TAP)
    time.sleep(2.0)

    # ── 7. 等待标准博弈界面 → 记录难度 → 点击开始对局 ──
    log.info("stage 7: wait rank")
    if not proceed_to_next(
        log, None, MODE_ENTER_TAP, "rank",
        cache_path=CACHE_SCREENSHOT,
        template=("ui", RANK_AREA),
    ):
        return 1

    # 记录难度信息
    log.info("stage 7b: read rank level")
    global CURRENT_RANK_LEVEL
    image = screenshot(log, CACHE_SCREENSHOT)
    rank_info = None
    if image is not None:
        rank_info = get_rank_level(image, log)
        if rank_info:
            CURRENT_RANK_LEVEL = rank_info["combined"]
            log.info(f"rank: {CURRENT_RANK_LEVEL}")
        else:
            log.warning("rank ocr failed, continue")

    # 段位层级切换
    if target_rank_level and rank_info and rank_info["rank"] and rank_info["level"]:
        log.info(f"stage 7c: adjust {target_rank_level}")
        target_rank, target_level_str = target_rank_level.split("-", 1)
        target_level = int(target_level_str)
        current_global = rank_to_global(rank_info["rank"], int(rank_info["level"]))
        target_global = rank_to_global(target_rank, target_level)
        if current_global != target_global:
            log.info(f"adjust: {CURRENT_RANK_LEVEL} -> {target_rank_level}")
            from adjust import adjust_level
            ok = adjust_level(target_rank, target_level)
            if not ok:
                log.error(f"adjust failed: {target_rank_level}")
                snapshot_error(log, "adjust_failed",
                               f"adjust failed: {target_rank_level}",
                               {"current": CURRENT_RANK_LEVEL, "target": target_rank_level}, image)
                return 1
            image2 = screenshot(log)
            if image2 is not None:
                rank_info2 = get_rank_level(image2, log)
                if rank_info2 and rank_info2["combined"]:
                    CURRENT_RANK_LEVEL = rank_info2["combined"]
                    log.info(f"adjusted: {CURRENT_RANK_LEVEL}")
        else:
            log.info(f"no adjust needed: {target_rank_level}")

    # 点击开始对局
    log.info("stage 7d: tap start battle")
    tap(log, *START_BATTLE_TAP)
    time.sleep(2.0)

    # ── 8. 调用 boss_info 识别 BOSS 信息 ──
    log.info("stage 8: boss_info")
    from boss_info import run as boss_info_run
    boss_info_run()

    # ── 9. 检测"下一步"控件 → 点击"下一步" ──
    log.info("stage 9: wait next_step")
    if not proceed_to_next(
        log, None, NEXT_STEP_TAP, "next_step",
        cache_path=CACHE_SCREENSHOT,
        template=("ui", NEXT_STEP_AREA),
    ):
        return 1
    tap(log, *NEXT_STEP_TAP)
    time.sleep(2.0)

    # ── 10. 第一位面过渡：图形匹配确认界面 → OCR检测"点击空白处继续" → 点击 ──
    log.info("stage 10: wait dim1 transition")
    if not proceed_to_next(
        log, None, None, "dim1_transition",
        cache_path=CACHE_SCREENSHOT,
        template=("ui", DIM1_TRANSITION_AREA),
    ):
        return 1
    log.info("stage 10b: wait continue text")
    if not proceed_to_next(
        log, DIM1_CONTINUE_KEYWORDS, None, "dim1_continue",
        cache_path=CACHE_SCREENSHOT,
    ):
        return 1
    tap(log, *DIM1_CONTINUE_TAP)
    time.sleep(2.0)

    log.info(f"done: {time.time() - start_time:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(run())