"""崩坏：星穹铁道 导航脚本。

前置条件：已通过 launch.py 进入游戏主界面。

流程：
1. 确认游戏界面（"状态效果"） → 点击指南入口
2. 确认指南界面（"生存索引"） → 点击旷宇纷争入口
3. 确认旷宇纷争界面（"货币战争"） → 识别"前往参与" → 点击进入货币战争主界面
"""

from __future__ import annotations

import logging
import os
import sys
import time
from pathlib import Path

import cv2
import numpy as np

# ── 配置 ────────────────────────────────────────────────────────────

INITIAL_INTERVAL = 1.0
MAX_INTERVAL = 60.0
MAX_WAIT = 120
MAX_RETRY = 5

CACHE_SCREENSHOT = Path("tmp/navigate_screenshot.png")
ERROR_DIR = Path("log/error")

# 游戏界面关键词（确认起点）
GAME_KEYWORDS = [
    {"keyword": "状态效果", "area": (1150, 100, 1235, 125), "preprocess": "invert", "scale": 1.0, "psm": 6},
]

# 指南界面入口坐标
GUIDE_ENTRY = (1010, 40)

# 指南界面关键词
GUIDE_KEYWORDS = [
    {"keyword": "生存索引", "area": (85, 35, 170, 60), "preprocess": None, "scale": 1.0, "psm": 6},
]

# 旷宇纷争入口坐标（x330-415, y85-145 的中点）
WAR_ENTRY = (372, 115)

# 旷宇纷争界面关键词（识别"货币战争"确认进入了旷宇纷争界面）
WAR_KEYWORDS = [
    {"keyword": "货币战争", "area": (140, 195, 240, 230), "preprocess": None, "scale": 1.0, "psm": 6},
]

# "前往参与"按钮关键词 + 点击坐标（按钮中心 x1000-1085, y605-630）
ENTER_KEYWORDS = [
    {"keyword": "前往参与", "area": (1000, 605, 1085, 630), "preprocess": None, "scale": 2.0, "psm": 6},
]
ENTER_TAP = (1042, 617)

# ── 日志 ────────────────────────────────────────────────────────────

def setup_logging() -> logging.Logger:
    log_dir = Path("log")
    log_dir.mkdir(exist_ok=True)
    log_file = os.environ.get("HSR_LOG_FILE") or str(log_dir / f"{time.strftime('%Y-%m-%d_%H-%M-%S')}.log")

    logger = logging.getLogger("navigate")
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


log = setup_logging()


# ── 错误快照 ───────────────────────────────────────────────────────

def snapshot_error(tag: str, error: str, context: dict, image: np.ndarray | None) -> None:
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

def ensure_device() -> None:
    from tools.devkit import ensure_connected
    state = ensure_connected()
    log.info(f"设备连接: {state}")


def screenshot() -> np.ndarray | None:
    from tools.devkit import screencap_png
    try:
        png_bytes = screencap_png()
        image = cv2.imdecode(np.frombuffer(png_bytes, np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            log.error("截图失败: PNG 解码失败")
            return None
        log.info("截图成功")
        CACHE_SCREENSHOT.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(CACHE_SCREENSHOT), image)
        return image
    except Exception as e:
        log.error(f"截图失败: {e}")
        return None


def tap(x: int, y: int) -> None:
    from tools.devkit import tap as _tap
    _tap(x, y)
    log.info(f"点击 ({x}, {y})")


# ── OCR 识别 ───────────────────────────────────────────────────────

def check_keywords(image: np.ndarray, kw_defs: list[dict]) -> bool:
    from perception.matcher import ocr
    for kw_def in kw_defs:
        text = ocr(image, area=kw_def["area"], lang="chi_sim+eng",
                   preprocess=kw_def.get("preprocess"),
                   scale=kw_def.get("scale", 1.0),
                   psm=kw_def.get("psm"))
        if kw_def["keyword"] in text:
            return True
    return False


# ── 主流程 ─────────────────────────────────────────────────────────

def run() -> int:
    log.info("=" * 50)
    log.info("崩坏：星穹铁道 导航阶段")
    log.info("=" * 50)

    try:
        ensure_device()
    except Exception as e:
        log.error(f"设备连接失败: {e}")
        return 1

    stage = "game"
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
            snapshot_error("timeout", f"等待 {MAX_WAIT}秒超时", context, cached)
            return 1

        image = screenshot()
        if image is None:
            time.sleep(current_interval)
            continue

        screenshot_count += 1

        if stage == "game":
            if check_keywords(image, GAME_KEYWORDS):
                log.info("游戏界面确认")
                current_interval = INITIAL_INTERVAL
                tap(*GUIDE_ENTRY)
                time.sleep(2.0)
                stage = "guide"
            else:
                log.info("加载中...")
                if current_interval < MAX_INTERVAL:
                    current_interval = min(current_interval + 1.0, MAX_INTERVAL)

        elif stage == "guide":
            if check_keywords(image, GUIDE_KEYWORDS):
                log.info("指南界面确认")
                current_interval = INITIAL_INTERVAL
                tap(*WAR_ENTRY)
                time.sleep(2.0)
                retry_count = 0
                stage = "guide_verify"
            else:
                log.info("加载中...")
                if current_interval < MAX_INTERVAL:
                    current_interval = min(current_interval + 1.0, MAX_INTERVAL)

        elif stage == "guide_verify":
            if check_keywords(image, WAR_KEYWORDS):
                log.info("旷宇纷争界面确认")
                current_interval = INITIAL_INTERVAL
                stage = "enter"
            else:
                retry_count += 1
                if retry_count >= MAX_RETRY:
                    log.error(f"旷宇纷争入口点击重试 {MAX_RETRY} 次仍未进入")
                    snapshot_error("guide_retry_exhausted",
                                   f"点击重试 {MAX_RETRY} 次仍未进入旷宇纷争界面",
                                   {"stage": stage, "retry_count": retry_count}, image)
                    return 1
                log.info(f"未进入旷宇纷争界面，再次点击 (重试 {retry_count}/{MAX_RETRY})")
                tap(*WAR_ENTRY)
                time.sleep(2.0)

        elif stage == "enter":
            if check_keywords(image, ENTER_KEYWORDS):
                log.info("前往参与确认")
                current_interval = INITIAL_INTERVAL
                tap(*ENTER_TAP)
                time.sleep(2.0)
                retry_count = 0
                stage = "enter_verify"
            else:
                log.info("加载中...")
                if current_interval < MAX_INTERVAL:
                    current_interval = min(current_interval + 1.0, MAX_INTERVAL)

        elif stage == "enter_verify":
            if check_keywords(image, ENTER_KEYWORDS):
                retry_count += 1
                if retry_count >= MAX_RETRY:
                    log.error(f"前往参与点击重试 {MAX_RETRY} 次仍未进入货币战争主界面")
                    snapshot_error("enter_retry_exhausted",
                                   f"点击重试 {MAX_RETRY} 次仍未进入货币战争主界面",
                                   {"stage": stage, "retry_count": retry_count}, image)
                    return 1
                log.info(f"仍在前往参与界面，再次点击 (重试 {retry_count}/{MAX_RETRY})")
                tap(*ENTER_TAP)
                time.sleep(2.0)
            else:
                log.info("货币战争主界面确认")
                log.info(f"总耗时: {time.time() - start_time:.1f}秒, 截图次数: {screenshot_count}")
                return 0

        time.sleep(current_interval)

    return 0


if __name__ == "__main__":
    sys.exit(run())