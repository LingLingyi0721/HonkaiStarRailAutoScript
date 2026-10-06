"""崩坏：星穹铁道 货币战争 BOSS 信息脚本。

前置条件：已通过 navigate.py 进入词条首领一览界面（"下一步"）。

输出信息（同时写入日志和 output/boss_info.json）：
1. 当前段位+层级 — 如 "A8-10"
2. 三位面文字 — 如 "第一位面：凛冬经贸联合体"
3. 敌人难度+数值 — 如 "敌人难度：70"
4. 词条文字 — 1~4段，第4段需滑动补全

OCR引擎：RapidOCR（自动检测文本位置+分行，适合中文密集场景）
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

# 段位与词条数量映射（A0-A1:0, A2-A3:1, A4-A5:2, A6-A7:3, A8:4）
RANK_AFFIX_COUNT = {
    "A0": 0, "A1": 0,
    "A2": 1, "A3": 1,
    "A4": 2, "A5": 2,
    "A6": 3, "A7": 3,
    "A8": 4,
}

# 区域 y 坐标范围（用于从 RapidOCR 全屏结果中筛选）
DIMENSION_Y_RANGE = (490, 530)    # 三位面文字
DIFFICULTY_Y_RANGE = (640, 680)   # 敌人难度 + 词条
AFFIX_X_START = 200               # 词条区域 x 起点（排除敌人难度区域）

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
            log.info(f"  {label}匹配: {repr(cleaned)} -> {repr(best_match)} (距离={best_distance})")
        return best_match
    else:
        log.info(f"  {label}未匹配: {repr(cleaned)} (最近={repr(best_match)} 距离={best_distance})")
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

    log.info(f"三位面区域识别到 {len(dim_items)} 项:")
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
            log.warning(f"{key} 识别失败")

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
            log.info(f"敌人难度区域: conf={conf:.2f} text={repr(text)}")
            numbers = re.findall(r'\d+', text)
            if numbers:
                difficulty = numbers[-1]
                log.info(f"敌人难度: {difficulty}")
                return difficulty

    # 如果没找到"敌人难度"文字，尝试在 x<200 区域找纯数字
    for x, y, text, conf in diff_items:
        if x < 200:
            numbers = re.findall(r'\d+', text)
            if numbers:
                difficulty = numbers[-1]
                log.info(f"敌人难度(位置推断): {difficulty} from {repr(text)}")
                return difficulty

    log.warning("敌人难度识别失败")
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

    log.info(f"词条区域识别到 {len(affix_raw)} 项:")
    for x, text, conf in affix_raw:
        log.info(f"  x={x:.0f} conf={conf:.2f} text={repr(text)}")

    # 清洗词条文字
    affixes = []
    for x, text, conf in affix_raw:
        cleaned = match_affix(text)
        if len(cleaned) >= 2:
            affixes.append(cleaned)
            log.info(f"  清洗: {repr(text)} -> {repr(cleaned)}")

    # 如果需要4段词条但只识别到不足4段，或第4段可能被截断（少于3字），左滑补全
    need_slide = False
    if expected_count and expected_count == 4:
        if len(affixes) < 4:
            need_slide = True
        elif len(affixes) == 4 and len(affixes[3]) < 3:
            # 第4段词条少于3字，可能是截断的
            log.info(f"第4段词条 '{affixes[3]}' 可能被截断，左滑补全")
            need_slide = True

    if need_slide:
        log.info("左滑补全第4段词条")
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
                            log.info(f"  左滑补全: {repr(text)} -> {repr(cleaned)}")
                            # 如果第4段被截断，替换它
                            if len(affixes) == 4 and len(affixes[3]) < 3 and len(cleaned) > len(affixes[3]):
                                affixes[3] = cleaned
                                log.info(f"  替换截断词条: {repr(affixes[3])}")
                            else:
                                affixes.append(cleaned)

        # 右滑回来
        swipe(log, AFFIX_SWIPE_X2, AFFIX_SWIPE_Y, AFFIX_SWIPE_X1, AFFIX_SWIPE_Y, duration_ms=500)
        time.sleep(2.0)

    log.info(f"最终词条: {affixes}")
    return affixes


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
            log.info(f"从 navigate 模块获取: {combined}")
    except (ImportError, AttributeError):
        pass

    if rank_info is None:
        log.info("navigate 模块无段位信息，尝试本地识别")
        rank_info = get_rank_level(image, log)

    # ── 2. RapidOCR 全屏识别 ──
    log.info("-" * 30)
    log.info("步骤2: RapidOCR 全屏识别")
    log.info("-" * 30)

    # ── 3. 三位面文字 ──
    log.info("-" * 30)
    log.info("步骤3: 三位面")
    log.info("-" * 30)

    dim_info = get_dimensions(image)

    # ── 4. 敌人难度 ──
    log.info("-" * 30)
    log.info("步骤4: 敌人难度")
    log.info("-" * 30)

    difficulty = get_enemy_difficulty(image)

    # ── 5. 词条文字 ──
    log.info("-" * 30)
    log.info("步骤5: 词条")
    log.info("-" * 30)

    expected_count = RANK_AFFIX_COUNT.get(rank_info["rank"]) if rank_info else None
    affixes = get_affixes(image, expected_count=expected_count)

    # ── 词条数量校验 ──
    if rank_info:
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

    return 0


if __name__ == "__main__":
    sys.exit(run())