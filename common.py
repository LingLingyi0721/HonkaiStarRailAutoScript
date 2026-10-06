"""公共基础设施模块。

提取各脚本（launch/navigate/battle/boss_info）中重复的：
- 日志设置
- 错误快照
- 设备操作（连接/截图/点击/滑动）
- 段位+层级识别

所有脚本从本模块导入，不再各自重复定义。
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

# 段位徽章区域（模板匹配）
RANK_BADGE_AREA = (72, 236, 108, 264)

# 层级数字区域（OCR识别）
LEVEL_AREA = (188, 303, 282, 374)

# 层级数字超过此阈值时默认段位为A8，跳过模板匹配
LEVEL_HIGH_THRESHOLD = 10
DEFAULT_HIGH_RANK = "A8"


# ── 日志 ────────────────────────────────────────────────────────────

def setup_logging(name: str) -> logging.Logger:
    """设置日志，name 为模块名（如 'battle'、'boss_info'）。

    所有模块共享同一个日志文件（通过 HSR_LOG_FILE 环境变量传递）。
    """
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

    logger.info(f"日志文件: {log_file}")
    return logger


# ── 错误快照 ───────────────────────────────────────────────────────

def snapshot_error(log: logging.Logger, tag: str, error: str,
                   context: dict, image: np.ndarray | None) -> None:
    """保存错误快照（截图+日志）到 log/error/ 目录。"""
    ERROR_DIR.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")

    if image is not None:
        shot_path = ERROR_DIR / f"{ts}_{tag}.png"
        cv2.imwrite(str(shot_path), image)
        log.error(f"错误快照已保存: {shot_path}")

    log_path = ERROR_DIR / f"{ts}_{tag}.log"
    lines = [f"时间: {ts}", f"标签: {tag}", f"错误: {error}"]
    for k, v in context.items():
        lines.append(f"{k}: {v}")
    log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    log.error(f"错误日志已保存: {log_path}")


# ── 设备操作 ───────────────────────────────────────────────────────

def ensure_device(log: logging.Logger) -> None:
    """确保设备已连接。"""
    from tools.devkit import ensure_connected
    state = ensure_connected()
    log.info(f"设备连接: {state}")


def screenshot(log: logging.Logger, cache_path: Path | None = None) -> np.ndarray | None:
    """截图并返回 BGR numpy 数组。可选保存到 cache_path。"""
    from tools.devkit import screencap_png
    try:
        png_bytes = screencap_png()
        image = cv2.imdecode(np.frombuffer(png_bytes, np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            log.error("截图失败: PNG 解码失败")
            return None
        log.info("截图成功")
        if cache_path:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cv2.imwrite(str(cache_path), image)
        return image
    except Exception as e:
        log.error(f"截图失败: {e}")
        return None


def tap(log: logging.Logger, x: int, y: int) -> None:
    """点击指定坐标。"""
    from tools.devkit import tap as _tap
    _tap(x, y)
    log.info(f"点击 ({x}, {y})")


def swipe(log: logging.Logger, x1: int, y1: int, x2: int, y2: int,
          duration_ms: int = 300) -> None:
    """滑动操作。"""
    from tools.devkit import swipe as _swipe
    _swipe(x1, y1, x2, y2, duration_ms)
    log.info(f"滑动 ({x1},{y1}) -> ({x2},{y2})")


# ── OCR 关键词检查 ─────────────────────────────────────────────────

def check_keywords(log: logging.Logger, image: np.ndarray, kw_defs: list[dict]) -> bool:
    """检查截图中是否包含任一关键词定义。

    kw_defs 格式：[{"keyword": "xxx", "area": (x1,y1,x2,y2), "preprocess": None, "scale": 1.0, "psm": 6}]
    """
    from perception.matcher import ocr
    for kw_def in kw_defs:
        text = ocr(image, area=kw_def["area"], lang="chi_sim+eng",
                   preprocess=kw_def.get("preprocess"),
                   scale=kw_def.get("scale", 1.0),
                   psm=kw_def.get("psm"))
        if kw_def["keyword"] in text:
            return True
    return False


# ── 段位+层级识别 ──────────────────────────────────────────────────

def get_rank_level(image: np.ndarray, log: logging.Logger) -> dict | None:
    """识别当前段位和层级，返回字典 {rank, level, combined}。

    层级数字超过 LEVEL_HIGH_THRESHOLD 时默认段位为A8，跳过模板匹配。
    combined 格式如 "A8-50"。
    """
    from perception.matcher import ocr
    from perception.templates import template_lib

    # 先识别层级数字
    level_text = ocr(image, area=LEVEL_AREA, lang="eng",
                     whitelist="0123456789",
                     preprocess=None, scale=1.0, psm=6)
    level_text = level_text.strip()

    if not level_text or not level_text.isdigit():
        log.warning("层级数字识别失败: %s" % repr(level_text))
        return None

    level_num = int(level_text)

    # 层级超过阈值则默认A8，否则模板匹配段位徽章
    if level_num > LEVEL_HIGH_THRESHOLD:
        rank_name = DEFAULT_HIGH_RANK
        log.info("段位: %s (层级%d>%d, 默认判定)" % (rank_name, level_num, LEVEL_HIGH_THRESHOLD))
    else:
        template_lib.reload()
        rank_name, rank_sim = template_lib.match(image, "rank", area=RANK_BADGE_AREA)
        if rank_name is None:
            log.warning("段位徽章匹配失败 (最高相似度=%.4f)" % rank_sim)
            return None
        log.info("段位: %s (相似度=%.4f)" % (rank_name, rank_sim))

    log.info("层级: %s" % level_text)
    combined = "%s-%s" % (rank_name, level_text)
    return {"rank": rank_name, "level": level_text, "combined": combined}


# ── 结构化输出 ─────────────────────────────────────────────────────

def save_output(log: logging.Logger, subdir: str, data: dict) -> Path:
    """将结构化数据保存为 JSON 文件到 output/{subdir}.json。

    固定文件名，同名直接替换（每一局是独立的，不需要保留历史）。
    返回保存的文件路径。
    """
    out_path = OUTPUT_DIR / f"{subdir}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info(f"结构化输出已保存: {out_path}")
    return out_path