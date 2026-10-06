"""崩坏：星穹铁道 货币战争入口脚本。

前置条件：已通过 navigate.py 进入货币战争主界面。

流程：
1. 确认货币战争主界面（"货币战争"） → 点击开始按钮
2. 兜底：点击后"货币战争"仍在则再次点击，最多5次
3. 确认模式选择界面（"进入标准博弈"） → 点击进入按钮
4. 兜底：点击后"进入标准博弈"仍在则再次点击，最多5次
5. 确认标准博弈界面（段位关键词） → 结束
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

CACHE_SCREENSHOT = Path("tmp/battle_screenshot.png")
ERROR_DIR = Path("log/error")

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

# 段位徽章区域（模板匹配）
RANK_BADGE_AREA = (72, 236, 108, 264)

# 层级数字区域（OCR识别）
LEVEL_AREA = (188, 303, 282, 374)

# 层级数字超过此阈值时默认段位为A8，跳过模板匹配
LEVEL_HIGH_THRESHOLD = 10
DEFAULT_HIGH_RANK = "A8"

# ── 日志 ────────────────────────────────────────────────────────────

def setup_logging() -> logging.Logger:
    log_dir = Path("log")
    log_dir.mkdir(exist_ok=True)
    log_file = os.environ.get("HSR_LOG_FILE") or str(log_dir / f"{time.strftime('%Y-%m-%d_%H-%M-%S')}.log")

    logger = logging.getLogger("battle")
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


def get_rank_level(image: np.ndarray) -> str | None:
    """识别当前段位和层级，返回组合值如 'A8-50'。

    层级数字超过 LEVEL_HIGH_THRESHOLD 时默认段位为 A8，跳过模板匹配。
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
    result = "%s-%s" % (rank_name, level_text)
    log.info("编号组合: %s" % result)
    return result


# ── 主流程 ─────────────────────────────────────────────────────────

def run() -> int:
    log.info("=" * 50)
    log.info("崩坏：星穹铁道 货币战争主页")
    log.info("=" * 50)

    try:
        ensure_device()
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
            snapshot_error("timeout", f"等待 {MAX_WAIT}秒超时", context, cached)
            return 1

        image = screenshot()
        if image is None:
            time.sleep(current_interval)
            continue

        screenshot_count += 1

        if stage == "confirm":
            if check_keywords(image, WAR_MAIN_KEYWORDS):
                log.info("货币战争主界面确认")
                current_interval = INITIAL_INTERVAL
                tap(*START_TAP)
                time.sleep(2.0)
                retry_count = 0
                stage = "start_verify"
            else:
                log.info("加载中...")
                if current_interval < MAX_INTERVAL:
                    current_interval = min(current_interval + 1.0, MAX_INTERVAL)

        elif stage == "start_verify":
            if check_keywords(image, MODE_KEYWORDS):
                log.info("模式选择界面确认")
                current_interval = INITIAL_INTERVAL
                tap(*ENTER_TAP)
                time.sleep(2.0)
                retry_count = 0
                stage = "enter_verify"
            elif check_keywords(image, WAR_MAIN_KEYWORDS):
                retry_count += 1
                if retry_count >= MAX_RETRY:
                    log.error(f"开始按钮点击重试 {MAX_RETRY} 次仍未进入货币战争")
                    snapshot_error("start_retry_exhausted",
                                   f"点击重试 {MAX_RETRY} 次仍未进入货币战争",
                                   {"stage": stage, "retry_count": retry_count}, image)
                    return 1
                log.info(f"仍在货币战争主界面，再次点击 (重试 {retry_count}/{MAX_RETRY})")
                tap(*START_TAP)
                time.sleep(2.0)
            else:
                log.info("加载中...")
                if current_interval < MAX_INTERVAL:
                    current_interval = min(current_interval + 1.0, MAX_INTERVAL)

        elif stage == "enter_verify":
            if check_keywords(image, RANK_KEYWORDS):
                log.info("标准博弈界面确认")
                log.info(f"总耗时: {time.time() - start_time:.1f}秒, 截图次数: {screenshot_count}")
                return 0
            elif check_keywords(image, MODE_KEYWORDS):
                retry_count += 1
                if retry_count >= MAX_RETRY:
                    log.error(f"进入标准博弈点击重试 {MAX_RETRY} 次仍未进入标准博弈界面")
                    snapshot_error("enter_retry_exhausted",
                                   f"点击重试 {MAX_RETRY} 次仍未进入标准博弈界面",
                                   {"stage": stage, "retry_count": retry_count}, image)
                    return 1
                log.info(f"仍在模式选择界面，再次点击 (重试 {retry_count}/{MAX_RETRY})")
                tap(*ENTER_TAP)
                time.sleep(2.0)
            else:
                log.info("加载中...")
                if current_interval < MAX_INTERVAL:
                    current_interval = min(current_interval + 1.0, MAX_INTERVAL)

        time.sleep(current_interval)

    return 0


if __name__ == "__main__":
    sys.exit(run())