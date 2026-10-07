"""货币战争 BOSS 信息识别。

前置：navigate.py 已进入词条首领一览界面。
输出：段位层级、三位面、敌人难度、词条 → output/boss_info.json
引擎：RapidOCR（全屏识别）+ ddddocr（数字）

本模块只被 navigate.py 调用，不独立运行。
"""

from __future__ import annotations

import re
import time
from pathlib import Path

import cv2
import numpy as np

from common import (
    setup_logging, snapshot_error, screenshot, tap, swipe,
    get_rank_level, save_output,
)

# ── 配置 ────────────────────────────────────────────────────────────

CACHE_SCREENSHOT = Path("tmp/boss_info_screenshot.png")

# 段位与词条数量映射
RANK_AFFIX_COUNT = {
    "A0": 0, "A1": 0,
    "A2": 1, "A3": 1,
    "A4": 2, "A5": 2,
    "A6": 3, "A7": 3,
    "A8": 4,
}

# y 坐标范围（从 RapidOCR 全屏结果中筛选）
DIMENSION_Y_RANGE = (490, 530)    # 三位面
DIFFICULTY_Y_RANGE = (640, 680)   # 敌人难度 + 词条
AFFIX_X_START = 200               # 词条 x 起点（排除敌人难度）

# 滑动参数
AFFIX_SWIPE_X1 = 745
AFFIX_SWIPE_X2 = 240
AFFIX_SWIPE_Y = 655


log = setup_logging("boss_info")


# ── 词库匹配 ───────────────────────────────────────────────────────

_AFFIX_DICT_PATH = Path(__file__).resolve().parent / "assets" / "affix_dict.json"
_FACTION_DICT_PATH = Path(__file__).resolve().parent / "assets" / "boss_factions.json"
_affix_dict_cache: dict | None = None
_faction_dict_cache: list[str] | None = None


def _load_affix_dict() -> dict:
    """懒加载词条词库。"""
    global _affix_dict_cache
    if _affix_dict_cache is None:
        import json
        with open(_AFFIX_DICT_PATH, "r", encoding="utf-8") as f:
            _affix_dict_cache = json.load(f)
    return _affix_dict_cache


def _load_faction_dict() -> list[str]:
    """懒加载BOSS阵营词库。"""
    global _faction_dict_cache
    if _faction_dict_cache is None:
        import json
        with open(_FACTION_DICT_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        _faction_dict_cache = data["boss_factions"]
    return _faction_dict_cache


def _levenshtein(s1: str, s2: str) -> int:
    """计算两个字符串的编辑距离（Levenshtein distance）。"""
    if len(s1) < len(s2):
        return _levenshtein(s2, s1)
    if len(s2) == 0:
        return len(s1)
    prev_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        curr_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = prev_row[j + 1] + 1
            deletions = curr_row[j] + 1
            substitutions = prev_row[j] + (c1 != c2)
            curr_row.append(min(insertions, deletions, substitutions))
        prev_row = curr_row
    return prev_row[-1]


def _match_dict(cleaned: str, candidates: list[str], label: str) -> str:
    """通用词库匹配：编辑距离<=2则替换为标准名称。"""
    if len(cleaned) < 2:
        return cleaned

    best_match = None
    best_distance = 999
    for candidate in candidates:
        dist = _levenshtein(cleaned, candidate)
        if dist < best_distance:
            best_distance = dist
            best_match = candidate

    if best_match and best_distance <= 2:
        if best_match != cleaned:
            log.info(f"  {label} match: {repr(cleaned)} -> {repr(best_match)} (dist={best_distance})")
        return best_match
    else:
        log.info(f"  {label} no match: {repr(cleaned)} (best={repr(best_match)} dist={best_distance})")
        return cleaned


def match_faction(text: str) -> str:
    """用阵营词库匹配修正OCR误识别的BOSS阵营名称。"""
    cleaned = ''.join(c for c in text if '\u4e00' <= c <= '\u9fff')
    return _match_dict(cleaned, _load_faction_dict(), "阵营")


def match_affix(text: str) -> str:
    """用词库匹配修正OCR误识别的词条文字。

    匹配规则：
    - 以"侵蚀·"开头 → 在侵蚀词缀列表中找最接近的匹配
    - 不以"侵蚀·"开头 → 在常规词缀列表中找最接近的匹配
    - 不存在其他形式的前缀和后缀
    - 字数不恒定（有4字、6字等）
    """
    # 先清洗：去掉非中文和非·字符
    cleaned = ''.join(c for c in text if '\u4e00' <= c <= '\u9fff' or c == '·')

    affix_dict = _load_affix_dict()
    erode_prefix = affix_dict["侵蚀前缀"]  # "侵蚀·"

    if cleaned.startswith(erode_prefix):
        return _match_dict(cleaned, affix_dict["侵蚀词缀"], "词库")
    else:
        return _match_dict(cleaned, affix_dict["常规词缀"], "词库")


# ── RapidOCR 识别 ──────────────────────────────────────────────────

def rapidocr_fullscreen(image: np.ndarray) -> list[tuple[list, str, float]]:
    """RapidOCR 全屏识别，返回所有检测结果。"""
    from perception.matcher import ocr_rapid
    return ocr_rapid(image)


def filter_by_y(
    results: list[tuple[list, str, float]],
    y_range: tuple[int, int],
) -> list[tuple[float, float, str, float]]:
    """按 y 坐标范围筛选结果，返回 [(x_avg, y_avg, text, conf), ...]"""
    y1, y2 = y_range
    filtered = []
    for box, text, conf in results:
        ys = [p[1] for p in box]
        y_avg = sum(ys) / len(ys)
        if y1 <= y_avg <= y2:
            xs = [p[0] for p in box]
            x_avg = sum(xs) / len(xs)
            filtered.append((x_avg, y_avg, text, float(conf)))
    return filtered


# ── 信息提取 ───────────────────────────────────────────────────────

def get_dimensions(image: np.ndarray) -> dict:
    """识别三位面文字，返回 {dimension1, dimension2, dimension3}。

    RapidOCR 全屏识别，按 y=490-530 筛选，再按 x 坐标排序对应三位面。
    """
    results = rapidocr_fullscreen(image)
    dim_items = filter_by_y(results, DIMENSION_Y_RANGE)

    # 按 x 坐标排序
    dim_items.sort(key=lambda item: item[0])

    log.info(f"dimensions found: {len(dim_items)}")
    for x, y, text, conf in dim_items:
        log.info(f"  x={x:.0f} y={y:.0f} conf={conf:.2f} text={repr(text)}")

    # 按位置分配 dimension1/2/3，用阵营词库匹配修正
    keys = ["dimension1", "dimension2", "dimension3"]
    results_dict = {}
    for i, key in enumerate(keys):
        if i < len(dim_items):
            raw_text = dim_items[i][2]
            matched = match_faction(raw_text)
            results_dict[key] = matched
        else:
            results_dict[key] = ""
            log.warning(f"{key} not found")

    return results_dict


def get_enemy_difficulty(image: np.ndarray) -> str | None:
    """识别敌人难度数值。

    RapidOCR 全屏识别，筛选 y=640-680 区域中包含"敌人难度"的文字，提取数字。
    """
    results = rapidocr_fullscreen(image)
    diff_items = filter_by_y(results, DIFFICULTY_Y_RANGE)

    # 找包含"敌人难度"或"难度"的文本
    for x, y, text, conf in diff_items:
        if "难度" in text or "敌人" in text:
            log.info(f"difficulty: conf={conf:.2f} text={repr(text)}")
            numbers = re.findall(r'\d+', text)
            if numbers:
                difficulty = numbers[-1]
                log.info(f"difficulty: {difficulty}")
                return difficulty

    # 如果没找到"敌人难度"文字，尝试在 x<200 区域找纯数字
    for x, y, text, conf in diff_items:
        if x < 200:
            numbers = re.findall(r'\d+', text)
            if numbers:
                difficulty = numbers[-1]
                log.info(f"difficulty (pos): {difficulty} from {repr(text)}")
                return difficulty

    log.warning("difficulty not found")
    return None


def get_affixes(image: np.ndarray, expected_count: int | None = None) -> list[str]:
    """识别词条文字，返回词条列表（1~4段）。

    RapidOCR 全屏识别，筛选 y=640-680 区域中 x>200 的文本（排除敌人难度）。
    每段词条前有图标，OCR会识别出噪音前缀，用 match_affix 清洗。

    如果 expected_count=4（A8段位），需要左滑一次识别第4段词条。
    """
    results = rapidocr_fullscreen(image)
    diff_items = filter_by_y(results, DIFFICULTY_Y_RANGE)

    # 筛选词条区域（x > AFFIX_X_START，排除敌人难度和"下一步"按钮）
    affix_raw = []
    for x, y, text, conf in diff_items:
        if x > AFFIX_X_START and x < 900 and "下一步" not in text:
            affix_raw.append((x, text, conf))

    # 按 x 坐标排序
    affix_raw.sort(key=lambda item: item[0])

    log.info(f"affixes found: {len(affix_raw)}")
    for x, text, conf in affix_raw:
        log.info(f"  x={x:.0f} conf={conf:.2f} text={repr(text)}")

    # 清洗词条文字
    affixes = []
    for x, text, conf in affix_raw:
        cleaned = match_affix(text)
        if len(cleaned) >= 2:
            affixes.append(cleaned)
            log.info(f"  match: {repr(text)} -> {repr(cleaned)}")

    # 如果需要4段词条但只识别到不足4段，或第4段可能被截断（少于3字），左滑补全
    need_slide = False
    if expected_count and expected_count == 4:
        if len(affixes) < 4:
            need_slide = True
        elif len(affixes) == 4 and len(affixes[3]) < 3:
            # 第4段词条少于3字，可能是截断的
            log.info(f"affix4 truncated: '{affixes[3]}', slide to complete")
            need_slide = True

    if need_slide:
        log.info("slide left for affix4")
        swipe(log, AFFIX_SWIPE_X1, AFFIX_SWIPE_Y, AFFIX_SWIPE_X2, AFFIX_SWIPE_Y, duration_ms=500)
        time.sleep(2.0)
        img_slide = screenshot(log, CACHE_SCREENSHOT)
        if img_slide is not None:
            slide_results = rapidocr_fullscreen(img_slide)
            slide_items = filter_by_y(slide_results, DIFFICULTY_Y_RANGE)
            for x, y, text, conf in slide_items:
                if x > AFFIX_X_START and x < 900 and "下一步" not in text:
                    cleaned = match_affix(text)
                    if len(cleaned) >= 2:
                        # 如果是新的词条（不在已有列表中），添加
                        if cleaned not in affixes:
                            log.info(f"  slide match: {repr(text)} -> {repr(cleaned)}")
                            # 如果第4段被截断，替换它
                            if len(affixes) == 4 and len(affixes[3]) < 3 and len(cleaned) > len(affixes[3]):
                                affixes[3] = cleaned
                                log.info(f"  replace truncated: {repr(affixes[3])}")
                            else:
                                affixes.append(cleaned)

        # 右滑回来
        swipe(log, AFFIX_SWIPE_X2, AFFIX_SWIPE_Y, AFFIX_SWIPE_X1, AFFIX_SWIPE_Y, duration_ms=500)
        time.sleep(2.0)

    log.info(f"affixes: {affixes}")
    return affixes


# ── 主流程 ─────────────────────────────────────────────────────────

def run() -> int:
    """识别 BOSS 信息。只被 navigate.py 调用。"""
    log.info("boss_info start")

    image = screenshot(log, CACHE_SCREENSHOT)
    if image is None:
        log.error("screenshot failed")
        return 1

    # ── 1. 段位和层级（从 navigate 获取）──
    log.info("step1: rank & level")

    rank_info = None
    try:
        import navigate
        if navigate.CURRENT_RANK_LEVEL:
            combined = navigate.CURRENT_RANK_LEVEL
            if "-" in combined:
                rank_name, level_text = combined.split("-", 1)
            else:
                rank_name, level_text = combined, None
            rank_info = {"rank": rank_name, "level": level_text, "combined": combined}
            log.info(f"rank from navigate: {combined}")
    except (ImportError, AttributeError):
        pass

    if rank_info is None:
        log.warning("rank not available from navigate, skip")

    # ── 2. RapidOCR 全屏识别 ──

    # ── 3. 三位面文字 ──
    log.info("step3: dimensions")

    dim_info = get_dimensions(image)

    # ── 4. 敌人难度 ──
    log.info("step4: difficulty")

    difficulty = get_enemy_difficulty(image)

    # ── 5. 词条文字 ──
    log.info("step5: affixes")

    expected_count = RANK_AFFIX_COUNT.get(rank_info["rank"]) if rank_info else None
    affixes = get_affixes(image, expected_count=expected_count)

    # ── 词条数量校验 ──
    if rank_info:
        actual_count = len(affixes)
        if expected_count is not None and actual_count < expected_count:
            log.error(
                f"affix count mismatch: rank {rank_info['rank']} expected {expected_count}, "
                f"got {actual_count}"
            )
            snapshot_error(
                log, "affix_count_mismatch",
                f"affix count mismatch: rank {rank_info['rank']} expected {expected_count}, got {actual_count}",
                {"rank": rank_info["rank"], "expected": expected_count,
                 "actual": actual_count, "affixes": affixes},
                image,
            )
        else:
            log.info(f"affix count ok: rank {rank_info['rank']} -> {actual_count}/{expected_count}")


    # ── 结构化 JSON 输出 ──
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

    # ── 入库 ──
    from data.db import update_active_game
    game_id = update_active_game(
        rank=rank_info["rank"] if rank_info else None,
        level=rank_info["level"] if rank_info else None,
        dimension1=dim_info.get("dimension1", ""),
        dimension2=dim_info.get("dimension2", ""),
        dimension3=dim_info.get("dimension3", ""),
        difficulty=difficulty,
        affixes=affixes,
    )
    log.info(f"db: game_id={game_id}")

    return 0
