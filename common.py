"""公共基础设施模块。

提取各脚本中重复的：
- 日志设置
- 错误快照
- 设备操作（连接/截图/点击/滑动）
- 段位+层级识别
- 通用兜底机制
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from pathlib import Path

import cv2
import numpy as np

# ── 常量 ────────────────────────────────────────────────────────────

ERROR_DIR = Path("log/error")
OUTPUT_DIR = Path("output")

RANK_BADGE_AREA = (72, 236, 108, 264)
LEVEL_AREA = (188, 303, 282, 374)
LEVEL_HIGH_THRESHOLD = 10
DEFAULT_HIGH_RANK = "A8"

RANK_LEVELS = {
    "A0": 3, "A1": 3, "A2": 3,
    "A3": 5, "A4": 5,
    "A5": 7, "A6": 7,
    "A7": 9,
    "A8": 50,
}
RANK_ORDER = ["A0", "A1", "A2", "A3", "A4", "A5", "A6", "A7", "A8"]

LEVEL_UP_AREA = (625, 95, 650, 115)
LEVEL_DOWN_AREA = (625, 530, 650, 555)


def rank_to_global(rank: str, level: int) -> int:
    pos = 0
    for r in RANK_ORDER:
        if r == rank:
            return pos + level
        pos += RANK_LEVELS[r]
    return pos + level


def global_to_rank(global_level: int) -> tuple[str, int]:
    pos = 0
    for r in RANK_ORDER:
        if global_level <= pos + RANK_LEVELS[r]:
            return r, global_level - pos
        pos += RANK_LEVELS[r]
    return "A8", global_level - pos


# ── 日志 ────────────────────────────────────────────────────────────

def setup_logging(name: str) -> logging.Logger:
    log_dir = Path("log")
    log_dir.mkdir(exist_ok=True)
    log_file = os.environ.get("HSR_LOG_FILE") or str(log_dir / f"{time.strftime('%Y-%m-%d_%H-%M-%S')}.log")

    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()

    fmt = logging.Formatter("[%(asctime)s] %(levelname)-7s %(message)s", datefmt="%H:%M:%S")

    sh = logging.StreamHandler(sys.stdout)
    sh.setLevel(logging.INFO)
    sh.setFormatter(fmt)
    logger.addHandler(sh)

    fh = logging.FileHandler(log_file, encoding="utf-8", mode="a")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    logger.info(f"log file: {log_file}")
    return logger


# ── 错误快照 ───────────────────────────────────────────────────────

def snapshot_error(log: logging.Logger, tag: str, error: str,
                   context: dict, image: np.ndarray | None) -> None:
    ERROR_DIR.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")

    if image is not None:
        shot_path = ERROR_DIR / f"{ts}_{tag}.png"
        cv2.imwrite(str(shot_path), image)
        log.error(f"snapshot saved: {shot_path}")

    log_path = ERROR_DIR / f"{ts}_{tag}.log"
    lines = [f"时间: {ts}", f"标签: {tag}", f"错误: {error}"]
    for k, v in context.items():
        lines.append(f"{k}: {v}")
    log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    log.error(f"error log saved: {log_path}")


# ── 设备操作 ───────────────────────────────────────────────────────

def ensure_device(log: logging.Logger) -> None:
    from tools.devkit import ensure_connected
    state = ensure_connected()
    log.info(f"device: {state}")


def screenshot(log: logging.Logger, cache_path: Path | None = None) -> np.ndarray | None:
    from tools.devkit import screencap_png
    try:
        png_bytes = screencap_png()
        image = cv2.imdecode(np.frombuffer(png_bytes, np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            log.error("screenshot failed: PNG decode error")
            return None
        if cache_path:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cv2.imwrite(str(cache_path), image)
        log.info("screenshot")
        return image
    except Exception as e:
        log.error(f"screenshot failed: {e}")
        return None


def tap(log: logging.Logger, x: int, y: int) -> None:
    from tools.devkit import tap as _tap
    _tap(x, y)
    log.info(f"tap {x},{y}")


def swipe(log: logging.Logger, x1: int, y1: int, x2: int, y2: int,
          duration_ms: int = 300) -> None:
    from tools.devkit import swipe as _swipe
    _swipe(x1, y1, x2, y2, duration_ms)
    log.info(f"swipe {x1},{y1} -> {x2},{y2}")


# ── OCR 关键词检查 ─────────────────────────────────────────────────

def check_keywords(log: logging.Logger, image: np.ndarray, kw_defs: list[dict]) -> bool:
    from perception.matcher import ocr_rapid_text
    PAD_X, PAD_Y = 30, 10
    for kw_def in kw_defs:
        x1, y1, x2, y2 = kw_def["area"]
        padded = (max(0, x1-PAD_X), max(0, y1-PAD_Y),
                  min(1280, x2+PAD_X), min(720, y2+PAD_Y))
        text = ocr_rapid_text(image, area=padded)
        keyword = kw_def["keyword"]
        log.info(f"check: {keyword}")
        if keyword in text:
            return True
    return False


# ── 通用兜底机制 ───────────────────────────────────────────────────

def proceed_to_next(
    log: logging.Logger,
    next_keywords: list[dict],
    tap_pos: tuple[int, int] | None,
    cache_path: Path | None = None,
    max_screenshots: int = 5,
    max_rounds: int = 3,
    interval: float = 1.0,
) -> bool:
    """等待下一阶段关键词出现，必要时点击推进。

    只检查下一阶段关键词是否出现，不做交叉验证。
    1. 截图，检查 next_keywords
    2. 出现 → 返回 True
    3. max_screenshots 次后未出现 → 点击 tap_pos
    4. 点击后再检查
    5. 连续 max_rounds 轮失败 → 返回 False
    """
    for round_num in range(1, max_rounds + 1):
        for shot_num in range(1, max_screenshots + 1):
            image = screenshot(log, cache_path)
            if image is not None and check_keywords(log, image, next_keywords):
                return True
            log.info("loading...")
            time.sleep(interval)

        if tap_pos is not None:
            log.info(f"fallback tap {tap_pos[0]},{tap_pos[1]} ({round_num}/{max_rounds})")
            tap(log, *tap_pos)
            time.sleep(2.0)
            image = screenshot(log, cache_path)
            if image is not None and check_keywords(log, image, next_keywords):
                return True
        else:
            log.warning(f"no tap_pos, waiting ({round_num}/{max_rounds})")

    log.error(f"proceed failed after {max_rounds} rounds")
    if cache_path and cache_path.exists():
        cached = cv2.imread(str(cache_path))
        snapshot_error(log, "proceed_failed",
                       f"proceed failed after {max_rounds} rounds",
                       {"rounds": max_rounds}, cached)
    return False


# ── 段位+层级识别 ──────────────────────────────────────────────────

def get_rank_level(image: np.ndarray, log: logging.Logger) -> dict | None:
    from perception.matcher import ocr_number
    from perception.templates import template_lib

    level_text = ocr_number(image, area=LEVEL_AREA)
    level_text = level_text.strip()
    level_ok = level_text and level_text.isdigit()
    if not level_ok:
        log.warning("level ocr failed: %s" % repr(level_text))

    rank_name: str | None = None
    if level_ok and int(level_text) > LEVEL_HIGH_THRESHOLD:
        rank_name = DEFAULT_HIGH_RANK
        log.info("rank: %s (level %d > %d, default)" % (rank_name, int(level_text), LEVEL_HIGH_THRESHOLD))
    else:
        template_lib.reload()
        rank_name, rank_sim = template_lib.match(image, "rank", area=RANK_BADGE_AREA)
        if rank_name is None:
            log.warning("rank template match failed (best sim=%.4f)" % rank_sim)
        else:
            log.info("rank: %s (sim=%.4f)" % (rank_name, rank_sim))

    if rank_name is None and not level_ok:
        return None

    if level_ok:
        log.info("level: %s" % level_text)
        combined = "%s-%s" % (rank_name, level_text)
    else:
        combined = rank_name or ""
    return {"rank": rank_name, "level": level_text if level_ok else None, "combined": combined}


# ── 结构化输出 ─────────────────────────────────────────────────────

def save_output(log: logging.Logger, subdir: str, data: dict) -> Path:
    out_path = OUTPUT_DIR / f"{subdir}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info(f"output saved: {out_path}")
    return out_path