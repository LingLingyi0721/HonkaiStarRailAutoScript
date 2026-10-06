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

# 段位与词条数量映射（A0-A1:0, A2-A3:1, A4-A5:2, A6-A7:3, A8:4）
RANK_AFFIX_COUNT = {
    "A0": 0, "A1": 0,
    "A2": 1, "A3": 1,
    "A4": 2, "A5": 2,
    "A6": 3, "A7": 3,
    "A8": 4,
}


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
    如果存在第4段，执行左滑+右滑循环两次，用投票机制取最可信内容：
    - 左滑：第4段完整显示
    - 右滑回来：前3段再次可见
    - 真词条在多次识别中反复出现（高票），乱码每次不同（低票被淘汰）
    """
    from perception.matcher import ocr
    from collections import Counter

    def ocr_affix(img: np.ndarray) -> list[str]:
        """对词条区域做 OCR 并分割过滤。"""
        text = ocr(img, area=AFFIX_AREA, lang="chi_sim+eng",
                   preprocess=None, scale=1.0, psm=6)
        parts = re.split(r'[^\u4e00-\u9fff\w]+', text)
        # 只保留2字及以上、且包含至少一个中文字符的片段
        # （纯英文/数字片段是乱码误识别，如 WA/CRAG/PB）
        return [p.strip() for p in parts
                if len(p.strip()) >= 2 and re.search(r'[\u4e00-\u9fff]', p)]

    # 原始位置识别
    parts = ocr_affix(image)
    log.info(f"原始识别: {parts} (共{len(parts)}段)")

    # 即使原始识别为空，也执行滑动循环（词条可能全部被乱码遮挡）
    # 执行左滑+右滑循环两次，用投票机制取最可信内容
    x1, y1, x2, y2 = AFFIX_AREA
    mid_y = (y1 + y2) // 2

    all_results = [parts]  # 收集所有轮次的识别结果

    for round_idx in range(2):
        round_num = round_idx + 1

        # 左滑（看第4段）
        swipe(log, x2 - 20, mid_y, x1 + 20, mid_y, duration_ms=500)
        time.sleep(2.0)
        new_image = screenshot(log, CACHE_SCREENSHOT)
        if new_image is not None:
            parts_left = ocr_affix(new_image)
            log.info(f"第{round_num}轮左滑识别: {parts_left}")
            all_results.append(parts_left)

        # 右滑回来（看前3段）
        swipe(log, x1 + 20, mid_y, x2 - 20, mid_y, duration_ms=500)
        time.sleep(2.0)
        new_image = screenshot(log, CACHE_SCREENSHOT)
        if new_image is not None:
            parts_right = ocr_affix(new_image)
            log.info(f"第{round_num}轮右滑识别: {parts_right}")
            all_results.append(parts_right)

    # 投票：把所有轮次中出现的片段统计频次
    # 真词条反复出现（高票），乱码每次不同（低票淘汰）
    all_parts = []
    for r in all_results:
        all_parts.extend(r)

    counter = Counter(all_parts)
    # 按出现次数降序，同票按长度降序（更完整的优先）
    sorted_parts = sorted(counter.items(), key=lambda x: (-x[1], -len(x[0])))

    # 去重：如果一个词条是另一个的子串，仅保留票数更高的
    # 例如 "位面强化"(2票) 是 "第一位面强化"(3票) 的子串 → 保留 "第一位面强化"
    # 例如 "能量逃伟"(3票) 和 "能量逃逸"(1票) 高度重叠 → 保留 "能量逃伟"
    candidates = [p for p, count in sorted_parts[:6]]  # 先取前6个候选
    confirmed = []
    for p in candidates:
        is_dup = False
        for kept in confirmed:
            # 子串关系：一个是另一个的子串
            if p in kept or kept in p:
                is_dup = True
                log.info(f"去重: '{p}' 与 '{kept}' 存在子串关系，保留 '{kept}'")
                break
            # 高度重叠：共同字符占比 >= 60%
            common = sum(1 for c in p if c in kept)
            overlap_ratio = common / max(len(p), len(kept))
            if overlap_ratio >= 0.6:
                is_dup = True
                log.info(f"去重: '{p}' 与 '{kept}' 重叠度{overlap_ratio:.0%}，保留 '{kept}'")
                break
        if not is_dup:
            confirmed.append(p)
        if len(confirmed) >= 4:
            break

    log.info(f"投票统计: {[(p, c) for p, c in sorted_parts[:6]]}")
    log.info(f"最终词条: {confirmed}")

    return confirmed


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
    # 词条首领一览界面不显示段位层级，从 battle 模块传递过来
    # 独立运行时 fallback 到自己识别
    log.info("-" * 30)
    log.info("步骤1: 段位和层级")
    log.info("-" * 30)

    rank_info = None
    try:
        import navigate
        if navigate.CURRENT_RANK_LEVEL:
            # navigate.py 传递的格式如 "A8-50"
            combined = navigate.CURRENT_RANK_LEVEL
            rank_name, level_text = combined.split("-", 1)
            rank_info = {"rank": rank_name, "level": level_text, "combined": combined}
            log.info(f"从 navigate 模块获取: {combined}")
    except (ImportError, AttributeError):
        pass

    if rank_info is None:
        log.info("navigate 模块无段位信息，尝试本地识别")
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

    # ── 词条数量校验 ──
    # 各段位词条数量固定：A0-A1:0, A2-A3:1, A4-A5:2, A6-A7:3, A8:4
    # 如果识别到的词条数少于当前段位应有的数量，抛出错误
    if rank_info:
        expected_count = RANK_AFFIX_COUNT.get(rank_info["rank"])
        actual_count = len(affixes)
        if expected_count is not None and actual_count < expected_count:
            log.error(
                f"词条数量校验失败: 段位{rank_info['rank']}应有{expected_count}个词条，"
                f"实际识别到{actual_count}个"
            )
            snapshot_error(
                log, "affix_count_mismatch",
                f"段位{rank_info['rank']}应有{expected_count}个词条，实际识别到{actual_count}个",
                {"rank": rank_info["rank"], "expected": expected_count,
                 "actual": actual_count, "affixes": affixes},
                image,
            )
            # 仍然继续输出，但标记错误
        else:
            log.info(f"词条数量校验通过: 段位{rank_info['rank']} → {actual_count}/{expected_count}个词条")

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
    expected_count = RANK_AFFIX_COUNT.get(rank_info["rank"]) if rank_info else None
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
        "expected_affix_count": expected_count,
        "affix_count_valid": (expected_count is not None and len(affixes) >= expected_count),
    }
    save_output(log, "boss_info", output_data)

    return 0


if __name__ == "__main__":
    sys.exit(run())