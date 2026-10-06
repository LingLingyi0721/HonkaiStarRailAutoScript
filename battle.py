"""崩坏：星穹铁道 货币战争入口脚本。

前置条件：已通过 navigate.py 进入货币战争主界面。

流程：
1. 确认货币战争主界面（"货币战争"） → 点击开始按钮
2. 兜底：点击后"货币战争"仍在则再次点击，最多5次
3. 确认模式选择界面（"进入标准博弈"） → 点击进入按钮
4. 兜底：点击后"进入标准博弈"仍在则再次点击，最多5次
5. 确认标准博弈界面（"开始对局"） → 记录难度信息（段位+层级） → 点击开始对局按钮
6. 兜底：点击后"开始对局"仍在则再次点击，最多5次
7. 确认词条首领一览界面（"下一步"） → 结束

难度信息（CURRENT_RANK_LEVEL）格式如 "A8-50"，供决策层AI使用。
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import cv2
import numpy as np

from common import setup_logging, snapshot_error, ensure_device, screenshot, tap, check_keywords, get_rank_level

# ── 配置 ────────────────────────────────────────────────────────────

INITIAL_INTERVAL = 1.0
MAX_INTERVAL = 60.0
MAX_WAIT = 120
MAX_RETRY = 5

CACHE_SCREENSHOT = Path("tmp/battle_screenshot.png")

# 货币战争主界面关键词
WAR_MAIN_KEYWORDS = [
    {"keyword": "货币战争", "area": (980, 625, 1085, 670), "preprocess": None, "scale": 1.0, "psm": 6},
]

# 开始按钮点击坐标（x1100-1130, y630-660 的中点）
START_TAP = (1115, 645)

# 模式选择界面关键词
MODE_KEYWORDS = [
    {"keyword": "进入标准博弈", "area": (980, 625, 1110, 650), "preprocess": None, "scale": 1.0, "psm": 6},
]

# 进入标准博弈按钮点击坐标（x1100-1130, y630-660 的中点）
ENTER_TAP = (1115, 645)

# 标准博弈界面关键词（"开始对局"按钮确认进入标准博弈界面）
RANK_KEYWORDS = [
    {"keyword": "开始对局", "area": (1045, 630, 1130, 655), "preprocess": None, "scale": 1.0, "psm": 6},
]

# "开始对局"按钮点击坐标
START_BATTLE_TAP = (1087, 642)

# 词条首领一览界面关键词（"下一步"按钮确认进入）
NEXT_STEP_KEYWORDS = [
    {"keyword": "下一步", "area": (970, 645, 1040, 670), "preprocess": None, "scale": 1.0, "psm": 6},
]

# 当前局难度信息（段位+层级），供决策层AI使用
CURRENT_RANK_LEVEL: str | None = None


log = setup_logging("battle")


# ── 主流程 ─────────────────────────────────────────────────────────

def run() -> int:
    log.info("=" * 50)
    log.info("崩坏：星穹铁道 货币战争主页")
    log.info("=" * 50)

    try:
        ensure_device(log)
    except Exception as e:
        log.error(f"设备连接失败: {e}")
        return 1

    stage = "confirm"
    start_time = time.time()
    screenshot_count = 0
    current_interval = INITIAL_INTERVAL
    retry_count = 0

    while True:
        if time.time() - start_time > MAX_WAIT:
            context = {"stage": stage, "elapsed": f"{time.time() - start_time:.1f}s",
                       "screenshot_count": screenshot_count}
            log.error(f"超时 ({MAX_WAIT}秒)")
            cached = cv2.imread(str(CACHE_SCREENSHOT)) if CACHE_SCREENSHOT.exists() else None
            snapshot_error(log, "timeout", f"等待 {MAX_WAIT}秒超时", context, cached)
            return 1

        image = screenshot(log, CACHE_SCREENSHOT)
        if image is None:
            time.sleep(current_interval)
            continue

        screenshot_count += 1

        if stage == "confirm":
            if check_keywords(log, image, WAR_MAIN_KEYWORDS):
                log.info("货币战争主界面确认")
                current_interval = INITIAL_INTERVAL
                tap(log, *START_TAP)
                time.sleep(2.0)
                retry_count = 0
                stage = "start_verify"
            else:
                log.info("加载中...")
                if current_interval < MAX_INTERVAL:
                    current_interval = min(current_interval + 1.0, MAX_INTERVAL)

        elif stage == "start_verify":
            if check_keywords(log, image, MODE_KEYWORDS):
                log.info("模式选择界面确认")
                current_interval = INITIAL_INTERVAL
                tap(log, *ENTER_TAP)
                time.sleep(2.0)
                retry_count = 0
                stage = "enter_verify"
            elif check_keywords(log, image, WAR_MAIN_KEYWORDS):
                retry_count += 1
                if retry_count >= MAX_RETRY:
                    log.error(f"开始按钮点击重试 {MAX_RETRY} 次仍未进入货币战争")
                    snapshot_error(log, "start_retry_exhausted",
                                   f"点击重试 {MAX_RETRY} 次仍未进入货币战争",
                                   {"stage": stage, "retry_count": retry_count}, image)
                    return 1
                log.info(f"仍在货币战争主界面，再次点击 (重试 {retry_count}/{MAX_RETRY})")
                tap(log, *START_TAP)
                time.sleep(2.0)
            else:
                log.info("加载中...")
                if current_interval < MAX_INTERVAL:
                    current_interval = min(current_interval + 1.0, MAX_INTERVAL)

        elif stage == "enter_verify":
            if check_keywords(log, image, RANK_KEYWORDS):
                log.info("标准博弈界面确认")
                # 记录难度信息（段位+层级），供决策层AI使用
                global CURRENT_RANK_LEVEL
                rank_info = get_rank_level(image, log)
                if rank_info:
                    CURRENT_RANK_LEVEL = rank_info["combined"]
                    log.info(f"当前难度: {CURRENT_RANK_LEVEL}")
                else:
                    log.warning("难度信息识别失败，继续流程")
                # 点击"开始对局"按钮
                current_interval = INITIAL_INTERVAL
                tap(log, *START_BATTLE_TAP)
                time.sleep(2.0)
                retry_count = 0
                stage = "battle_start"
            elif check_keywords(log, image, MODE_KEYWORDS):
                retry_count += 1
                if retry_count >= MAX_RETRY:
                    log.error(f"进入标准博弈点击重试 {MAX_RETRY} 次仍未进入标准博弈界面")
                    snapshot_error(log, "enter_retry_exhausted",
                                   f"点击重试 {MAX_RETRY} 次仍未进入标准博弈界面",
                                   {"stage": stage, "retry_count": retry_count}, image)
                    return 1
                log.info(f"仍在模式选择界面，再次点击 (重试 {retry_count}/{MAX_RETRY})")
                tap(log, *ENTER_TAP)
                time.sleep(2.0)
            else:
                log.info("加载中...")
                if current_interval < MAX_INTERVAL:
                    current_interval = min(current_interval + 1.0, MAX_INTERVAL)

        elif stage == "battle_start":
            if check_keywords(log, image, NEXT_STEP_KEYWORDS):
                log.info("词条首领一览界面确认")
                log.info(f"总耗时: {time.time() - start_time:.1f}秒, 截图次数: {screenshot_count}")
                return 0
            elif check_keywords(log, image, RANK_KEYWORDS):
                retry_count += 1
                if retry_count >= MAX_RETRY:
                    log.error(f"开始对局点击重试 {MAX_RETRY} 次仍未进入词条首领一览")
                    snapshot_error(log, "battle_start_retry_exhausted",
                                   f"点击重试 {MAX_RETRY} 次仍未进入词条首领一览",
                                   {"stage": stage, "retry_count": retry_count}, image)
                    return 1
                log.info(f"仍在标准博弈界面，再次点击开始对局 (重试 {retry_count}/{MAX_RETRY})")
                tap(log, *START_BATTLE_TAP)
                time.sleep(2.0)
            else:
                log.info("加载中...")
                if current_interval < MAX_INTERVAL:
                    current_interval = min(current_interval + 1.0, MAX_INTERVAL)

        time.sleep(current_interval)

    return 0


if __name__ == "__main__":
    sys.exit(run())