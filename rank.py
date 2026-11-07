"""标准博弈难度选择 → BOSS 阵营与本局词条记录。

阶段范围：等待标准博弈界面 → 读取难度层级 →（可选）调整段位 → 开始对局
         → 识别 BOSS 信息（三位面 / 敌人难度 / 词条）→ 点击下一步。
记录：难度等级、三位面、敌人难度、全局词条、BOSS 阵营
     → output/boss_info.json + data/games.json（由 boss_info 写入）

前置：navigate.py 判定为「进入标准博弈」(mode)。
后续：title.py。
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

from common import (
    setup_logging, ensure_device, screenshot, tap,
    get_rank_level, rank_to_global, proceed_to_next, snapshot_error,
)

# ── 配置 ────────────────────────────────────────────────────────────

CACHE_SCREENSHOT = Path("tmp/rank_screenshot.png")

# 标准博弈界面（图片模板匹配）
RANK_AREA = (1048, 632, 1130, 655)
START_BATTLE_TAP = (1087, 642)

# 词条首领一览界面（图片模板匹配）
NEXT_STEP_AREA = (970, 648, 1035, 668)
NEXT_STEP_TAP = (1002, 658)

# 兜底点击：模式选择界面的「进入标准博弈」按钮
MODE_ENTER_TAP = (1115, 645)

# 当前局难度信息（段位+层级），供 boss_info 与决策层AI使用
CURRENT_RANK_LEVEL: str | None = None

log = setup_logging("rank")


# ── 主流程 ─────────────────────────────────────────────────────────

def run(target_rank_level: str | None = None) -> int:
    """标准博弈难度选择 → BOSS 阵营与本局词条记录。

    Args:
        target_rank_level: 目标段位层级，格式如 "A8-10"。
            None 表示不切换，保持当前位置。
    """
    log.info("rank start")

    try:
        ensure_device(log)
    except Exception as e:
        log.error(f"device connect failed: {e}")
        return 1

    global CURRENT_RANK_LEVEL

    # 新对局开始：作废旧数据
    from data.db import start_new_game
    start_new_game()
    log.info("db: new game started, old active records abandoned")

    # ── 1. 等待标准博弈界面 ──
    log.info("stage 1: wait rank")
    if not proceed_to_next(
        log, None, MODE_ENTER_TAP, "rank",
        cache_path=CACHE_SCREENSHOT,
        template=("navigate", RANK_AREA),
    ):
        return 1

    # ── 2. 读取难度层级 ──
    log.info("stage 2: read rank level")
    image = screenshot(log, CACHE_SCREENSHOT)
    rank_info = None
    if image is not None:
        rank_info = get_rank_level(image, log)
        if rank_info:
            CURRENT_RANK_LEVEL = rank_info["combined"]
            log.info(f"rank: {CURRENT_RANK_LEVEL}")
        else:
            log.warning("rank ocr failed, continue")

    # ── 3. 段位层级切换 ──
    if target_rank_level and rank_info and rank_info["rank"] and rank_info["level"]:
        log.info(f"stage 3: adjust {target_rank_level}")
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

    # ── 4. 点击开始对局 ──
    log.info("stage 4: tap start battle")
    tap(log, *START_BATTLE_TAP)
    time.sleep(2.0)

    # ── 5. 识别 BOSS 信息（位面 / 敌人难度 / 词条）──
    log.info("stage 5: boss_info")
    from boss_info import run as boss_info_run
    boss_info_run()

    # ── 6. 检测「下一步」控件 → 点击 ──
    log.info("stage 6: wait next_step")
    if not proceed_to_next(
        log, None, NEXT_STEP_TAP, "next_step",
        cache_path=CACHE_SCREENSHOT,
        template=("navigate", NEXT_STEP_AREA),
    ):
        return 1
    tap(log, *NEXT_STEP_TAP)
    time.sleep(2.0)

    log.info("rank done")
    return 0


if __name__ == "__main__":
    sys.exit(run())