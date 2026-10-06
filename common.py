"""公共基础设施：日志、设备操作、OCR关键词检查、段位识别、通用兜底。"""

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

# 兜底：界面切换检测
CORNER_AREA = (0, 0, 40, 40)   # 左上角比对区域
SWITCH_THRESHOLD = 0.8         # 相似度低于此值 = 界面已切换


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


def screenshot(log: logging.Logger, cache_path: Path | None = None,
               quiet: bool = False) -> np.ndarray | None:
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
        if not quiet:
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

def check_keywords(log: logging.Logger, image: np.ndarray,
                   kw_defs: list[dict], obj_id: str) -> bool:
    """在 kw_defs 区域内 OCR，命中任一关键词返回 True。

    日志：check <obj_id>: found / check <obj_id>: not found
    同一区域的多个候选词只 OCR 一次。
    """
    from perception.matcher import ocr_rapid_text
    PAD_X, PAD_Y = 30, 10
    ocr_cache: dict[tuple, str] = {}
    for kw_def in kw_defs:
        x1, y1, x2, y2 = kw_def["area"]
        padded = (max(0, x1-PAD_X), max(0, y1-PAD_Y),
                  min(1280, x2+PAD_X), min(720, y2+PAD_Y))
        if padded not in ocr_cache:
            ocr_cache[padded] = ocr_rapid_text(image, area=padded)
        if kw_def["keyword"] in ocr_cache[padded]:
            log.info(f"check {obj_id}: found")
            return True
    log.info(f"check {obj_id}: not found")
    return False


# ── 通用兜底机制 ───────────────────────────────────────────────────

def _capture_corner(log: logging.Logger) -> np.ndarray | None:
    """截取屏幕左上角 CORNER_AREA 区域，用于界面切换比对。"""
    from tools.devkit import screencap_png
    try:
        png = screencap_png()
        image = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            return None
        x1, y1, x2, y2 = CORNER_AREA
        log.info("capture corner")
        return image[y1:y2, x1:x2]
    except Exception as e:
        log.warning(f"capture corner failed: {e}")
        return None


def region_similar(a: np.ndarray | None, b: np.ndarray | None) -> float:
    """两个同尺寸图像块的相似度 0~1（1=完全相同）。

    用平均像素差而非模板匹配，避免纯色区域 TM_CCOEFF_NORMED 的 NaN。
    无法比对时保守返回 1.0（视为未切换）。
    """
    if a is None or b is None or a.shape != b.shape:
        return 1.0
    diff = np.abs(a.astype(np.float32) - b.astype(np.float32)).mean() / 255.0
    return float(1.0 - diff)


def proceed_to_next(
    log: logging.Logger,
    next_keywords: list[dict],
    tap_pos: tuple[int, int] | None,
    obj_id: str,
    cache_path: Path | None = None,
    detect_switch: bool = True,
    max_checks: int = 5,
    interval: float = 3.0,
    max_rounds: int = 3,
) -> bool:
    """等待 next_keywords 出现，未出现则点击推进并检测界面切换。

    每轮截图检查最多 max_checks 次（周期 interval 秒），共循环 max_rounds 轮：
    - 命中 → 返回 True
    - 本轮未命中且 detect_switch=True → 截左上角 → 点击 → 再截 → 比对相似度
      - 相似度 < SWITCH_THRESHOLD → 界面已切换，返回 True
    - detect_switch=False（"点击进入"阶段）只重复识别，不点击
    """
    for round_num in range(1, max_rounds + 1):
        for _ in range(max_checks):
            t0 = time.time()
            image = screenshot(log, cache_path, quiet=True)
            if image is not None and check_keywords(log, image, next_keywords, obj_id):
                return True
            time.sleep(max(0.0, interval - (time.time() - t0)))

        if detect_switch and tap_pos is not None:
            before = _capture_corner(log)
            tap(log, *tap_pos)
            time.sleep(2.0)
            after = _capture_corner(log)
            sim = region_similar(before, after)
            log.info(f"switch check: sim={sim:.2f} ({round_num}/{max_rounds})")
            if sim < SWITCH_THRESHOLD:
                log.info("screen switched, proceed")
                return True
        else:
            log.info(f"no switch check for {obj_id} ({round_num}/{max_rounds})")

    log.error(f"proceed failed: {obj_id}")
    if cache_path and cache_path.exists():
        cached = cv2.imread(str(cache_path))
        snapshot_error(log, "proceed_failed", f"proceed failed: {obj_id}",
                       {"obj": obj_id, "rounds": max_rounds}, cached)
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