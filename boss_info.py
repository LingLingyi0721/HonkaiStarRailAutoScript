"""崩坏：星穹铁道 货币战争 BOSS 信息脚本。

前置条件：已通过 battle.py 进入词条首领一览界面（"下一步"）。

输出信息（同时写入日志和 output/boss_info/ JSON 文件）：
1. 当前段位（段位）+（层级） — 如 "当前段位：A8（50）"
2. 三位面文字 — 如 "第一位面：xxx"
3. 敌人难度+数值 — 如 "敌人难度：5"
4. 词条文字 — 1~4段，第4段需滑动补全
"""

from __future__ import annotations

import re
import sys
import time
from pathlib import Path

import cv2
import numpy as np

from common import (
    setup_logging, snapshot_error, ensure_device, screenshot, tap, swipe,
    get_rank_level, save_output,
)

# ── 配置 ────────────────────────────────────────────────────────────

CACHE_SCREENSHOT = Path("tmp/boss_info_screenshot.png")

# 三位面文字区域（y500-525）
DIMENSION1_AREA = (50, 500, 245, 525)    # 第一位面
DIMENSION2_AREA = (300, 500, 500, 525)   # 第二位面
DIMENSION3_AREA = (550, 500, 755, 525)   # 第三位面

# 敌人难度区域（文字+数值）
ENEMY_DIFFICULTY_AREA = (70, 640, 210, 670)

# 词条文字区域（1~4段，第4段可能需要滑动补全）
AFFIX_AREA = (220, 640, 765, 670)


log = setup_logging("boss_info")


# ── 信息提取 ───────────────────────────────────────────────────────

def get_dimensions(image: np.ndarray) -> dict:
    """识别三位面文字，返回 {dimension1, dimension2, dimension3}。"""
    from perception.matcher import ocr

    results = {}
    areas = [
        ("dimension1", DIMENSION1_AREA),
        ("dimension2", DIMENSION2_AREA),
        ("dimension3", DIMENSION3_AREA),
    ]

    for name, area in areas:
        text = ocr(image, area=area, lang="chi_sim+eng",
                   preprocess=None, scale=1.0, psm=6)
        text = text.strip()
        results[name] = text
        log.info(f"{name}: {text if text else '(空)'}")

    return results


def get_enemy_difficulty(image: np.ndarray) -> str | None:
    """识别敌人难度+数值，返回数值部分。

    区域 x70-210, y640-670 包含"敌人难度"文字和数值。
    先尝试整体识别，提取数值；如果文字干扰大，用数字白名单只认数字。
    """
    from perception.matcher import ocr

    # 先整体识别（文字+数值）
    full_text = ocr(image, area=ENEMY_DIFFICULTY_AREA, lang="chi_sim+eng",
                    preprocess=None, scale=1.0, psm=6)
    log.info(f"敌人难度区域原始识别: {repr(full_text)}")

    # 从识别结果中提取数字
    numbers = re.findall(r'\d+', full_text)
    if numbers:
        difficulty = numbers[-1]  # 取最后一个数字（难度数值通常在文字后面）
        log.info(f"敌人难度: {difficulty}")
        return difficulty

    # 如果整体识别没提取到数字，用数字白名单再试
    digits_text = ocr(image, area=ENEMY_DIFFICULTY_AREA, lang="eng",
                      whitelist="0123456789",
                      preprocess=None, scale=2.0, psm=6)
    digits_text = digits_text.strip()
    if digits_text and digits_text.isdigit():
        log.info(f"敌人难度(数字白名单): {digits_text}")
        return digits_text

    log.warning("敌人难度识别失败")
    return None


def get_affixes(image: np.ndarray) -> list[str]:
    """识别词条文字，返回词条列表（1~4段）。

    区域 x220-765, y640-670 包含1~4段词条文字，每段前面有一个乱码标记。
    如果存在第4段，先确认前三段内容，然后从此区域往左滑动一次，再识别补全第4段。
    """
    from perception.matcher import ocr

    # 第一次识别
    text = ocr(image, area=AFFIX_AREA, lang="chi_sim+eng",
               preprocess=None, scale=1.0, psm=6)
    log.info(f"词条区域原始识别: {repr(text)}")

    # 分割词条：乱码字符作为分隔标志，后面接文字内容
    # 用非中文、非数字、非字母的连续字符作为分隔
    parts = re.split(r'[^\u4e00-\u9fff\w]+', text)
    # 只保留2字及以上的片段（单字多为乱码误识别）
    parts = [p.strip() for p in parts if len(p.strip()) >= 2]

    if not parts:
        log.warning("词条识别失败：未识别到任何可信内容")
        return []

    log.info(f"词条分割结果: {parts} (共{len(parts)}段)")

    # 如果有4段或以上，需要滑动补全第4段
    if len(parts) >= 4:
        log.info("检测到4段词条，执行滑动补全第4段")
        confirmed = parts[:3]
        log.info(f"前三段已确认: {confirmed}")

        # 从词条区域往左滑动（让第4段完整显示）
        x1, y1, x2, y2 = AFFIX_AREA
        mid_y = (y1 + y2) // 2
        swipe(log, x2 - 20, mid_y, x1 + 20, mid_y, duration_ms=500)
        time.sleep(2.0)  # 滑动后等2秒让画面稳定再截图

        # 滑动后重新截图并识别
        new_image = screenshot(log, CACHE_SCREENSHOT)
        if new_image is not None:
            new_text = ocr(new_image, area=AFFIX_AREA, lang="chi_sim+eng",
                           preprocess=None, scale=1.0, psm=6)
            log.info(f"滑动后词条区域识别: {repr(new_text)}")
            new_parts = re.split(r'[^\u4e00-\u9fff\w]+', new_text)
            new_parts = [p.strip() for p in new_parts if len(p.strip()) >= 2]
            log.info(f"滑动后词条分割结果: {new_parts}")

            if new_parts:
                fourth = new_parts[0] if len(new_parts) == 1 else new_parts[-1]
                confirmed.append(fourth)
                log.info(f"第4段补全: {fourth}")
            else:
                confirmed.append(parts[3])
                log.warning("滑动后识别失败，使用原始第4段结果")
        else:
            confirmed.append(parts[3])
            log.warning("滑动后截图失败，使用原始第4段结果")

        return confirmed

    return parts


# ── 主流程 ─────────────────────────────────────────────────────────

def run() -> int:
    log.info("=" * 50)
    log.info("崩坏：星穹铁道 BOSS 信息识别")
    log.info("=" * 50)

    try:
        ensure_device(log)
    except Exception as e:
        log.error(f"设备连接失败: {e}")
        return 1

    image = screenshot(log, CACHE_SCREENSHOT)
    if image is None:
        log.error("截图失败，无法继续")
        return 1

    # ── 1. 段位和层级 ──
    log.info("-" * 30)
    log.info("步骤1: 段位和层级")
    log.info("-" * 30)

    rank_info = get_rank_level(image, log)

    # ── 2. 三位面文字 ──
    log.info("-" * 30)
    log.info("步骤2: 三位面")
    log.info("-" * 30)

    dim_info = get_dimensions(image)

    # ── 3. 敌人难度 ──
    log.info("-" * 30)
    log.info("步骤3: 敌人难度")
    log.info("-" * 30)

    difficulty = get_enemy_difficulty(image)

    # ── 4. 词条文字 ──
    log.info("-" * 30)
    log.info("步骤4: 词条")
    log.info("-" * 30)

    affixes = get_affixes(image)

    # ── 汇总输出 ──
    log.info("=" * 50)
    log.info("BOSS 信息汇总")
    log.info("=" * 50)

    if rank_info:
        log.info(f"当前段位：{rank_info['rank']}（{rank_info['level']}）")
    else:
        log.warning("当前段位：识别失败")

    for label, key in [("第一位面", "dimension1"), ("第二位面", "dimension2"), ("第三位面", "dimension3")]:
        text = dim_info.get(key, "")
        log.info(f"{label}：{text if text else '(空)'}")

    if difficulty:
        log.info(f"敌人难度：{difficulty}")
    else:
        log.warning("敌人难度：识别失败")

    for i, affix in enumerate(affixes, 1):
        log.info(f"词条{i}：{affix}")

    # ── 结构化 JSON 输出到 output/boss_info/ ──
    output_data = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "rank": rank_info["rank"] if rank_info else None,
        "level": rank_info["level"] if rank_info else None,
        "rank_level": rank_info["combined"] if rank_info else None,
        "dimension1": dim_info.get("dimension1", ""),
        "dimension2": dim_info.get("dimension2", ""),
        "dimension3": dim_info.get("dimension3", ""),
        "enemy_difficulty": difficulty,
        "affixes": affixes,
        "affix_count": len(affixes),
    }
    save_output(log, "boss_info", output_data)

    return 0


if __name__ == "__main__":
    sys.exit(run())