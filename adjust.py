"""段位层级切换模块。

前置：已进入标准博弈界面。
流程：识别当前段位+层级 → 计算全局差值 → 点击增减按钮 → 验证
"""

from __future__ import annotations

import time

import cv2

from common import (
    setup_logging, ensure_device, screenshot,
    get_rank_level, rank_to_global, global_to_rank,
    RANK_LEVELS, RANK_ORDER, LEVEL_UP_AREA, LEVEL_DOWN_AREA,
    tap,
)
from perception.matcher import area_center


def adjust_level(target_rank: str, target_level: int, max_clicks: int = 60) -> bool:
    """调整段位层级到目标位置。

    Args:
        target_rank: 目标段位（如 "A5"）
        target_level: 目标层级（如 4）
        max_clicks: 最大点击次数，防止无限循环

    Returns:
        True 表示成功调整到目标位置
    """
    log = setup_logging("adjust")

    ensure_device(log)

    # 截图识别当前段位+层级
    img = screenshot(log)
    if img is None:
        return False

    rank_info = get_rank_level(img, log)
    if rank_info is None or rank_info["rank"] is None:
        log.error("无法识别当前段位")
        return False

    current_rank = rank_info["rank"]
    current_level_str = rank_info["level"]

    # 层级可能为None（OCR失败），尝试用ddddocr重新识别
    if current_level_str is None:
        from perception.matcher import ocr_number
        current_level_str = ocr_number(img, area=(180, 295, 285, 380))
        if not current_level_str or not current_level_str.isdigit():
            log.error("无法识别当前层级数字")
            return False

    current_level = int(current_level_str)
    current_global = rank_to_global(current_rank, current_level)
    target_global = rank_to_global(target_rank, target_level)

    log.info("current: %s-%d (global %d)" % (current_rank, current_level, current_global))
    log.info("target: %s-%d (global %d)" % (target_rank, target_level, target_global))

    if current_global == target_global:
        log.info("no adjust needed")
        return True

    diff = target_global - current_global
    up_center = area_center(LEVEL_UP_AREA)
    down_center = area_center(LEVEL_DOWN_AREA)

    if diff > 0:
        direction = "up"
        click_point = up_center
    else:
        direction = "down"
        click_point = down_center
        diff = -diff

    log.info("adjust %s x%d (%s)" % (direction, diff, click_point))

    # 逐次点击
    for i in range(min(diff, max_clicks)):
        tap(log, click_point[0], click_point[1])
        time.sleep(0.3)

    # 验证
    time.sleep(1.0)
    img2 = screenshot(log)
    if img2 is None:
        log.warning("verify screenshot failed, assume ok")
        return True

    rank_info2 = get_rank_level(img2, log)
    if rank_info2 and rank_info2["rank"] and rank_info2["level"]:
        new_rank = rank_info2["rank"]
        new_level = int(rank_info2["level"])
        new_global = rank_to_global(new_rank, new_level)
        log.info("adjusted: %s-%d (global %d)" % (new_rank, new_level, new_global))

        if new_global == target_global:
            log.info("adjust ok")
            return True
        else:
            log.warning("position %s-%d != target %s-%d" %
                        (new_rank, new_level, target_rank, target_level))
            # 尝试二次修正
            remaining = target_global - new_global
            if remaining > 0:
                for _ in range(min(remaining, 10)):
                    tap(log, up_center[0], up_center[1])
                    time.sleep(0.3)
            elif remaining < 0:
                for _ in range(min(-remaining, 10)):
                    tap(log, down_center[0], down_center[1])
                    time.sleep(0.3)

            time.sleep(1.0)
            img3 = screenshot(log)
            if img3 is not None:
                rank_info3 = get_rank_level(img3, log)
                if rank_info3 and rank_info3["rank"] and rank_info3["level"]:
                    final_rank = rank_info3["rank"]
                    final_level = int(rank_info3["level"])
                    final_global = rank_to_global(final_rank, final_level)
                    log.info("final: %s-%d (global %d)" % (final_rank, final_level, final_global))
                    return final_global == target_global

            return False

    log.warning("verify ocr failed, assume ok")
    return True


def run(target_rank: str = "A8", target_level: int = 1) -> int:
    """主入口：调整到目标段位层级。"""
    log = setup_logging("adjust")
    log.info("adjust start")

    ok = adjust_level(target_rank, target_level)
    return 0 if ok else 1


if __name__ == "__main__":
    import sys
    # 用法: python adjust.py A5 4
    if len(sys.argv) >= 3:
        sys.exit(run(sys.argv[1], int(sys.argv[2])))
    else:
        sys.exit(run())