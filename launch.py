"""崩坏：星穹铁道 启动脚本。

流程：
1. 确保 adb 连接 + 启动崩铁 app
2. 识别到"点击进入" → 单击屏幕中央
3. 识别到"状态效果" → 确认进入游戏，结束
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

PACKAGE = "com.miHoYo.hkrpg"
ACTIVITY = "com.mihoyo.combosdk.ComboSDKActivity"
SERIAL = "127.0.0.1:16416"

SCREEN_CENTER = (640, 360)
INITIAL_INTERVAL = 1.0
MAX_INTERVAL = 60.0
MAX_WAIT = 300
MAX_RETRY = 5

CACHE_SCREENSHOT = Path("tmp/launch_screenshot.png")
ERROR_DIR = Path("log/error")

# 登录界面：主关键词"点击进入"命中即确认；辅助关键词仅日志
LOGIN_PRIMARY = {
    "keyword": "点击进入",
    "area": (400, 600, 880, 700),
    "preprocess": "binary",
    "scale": 2.0,
    "psm": 6,
}

LOGIN_AUXILIARY = [
    {"keyword": "公告", "area": (1050, 80, 1280, 600), "preprocess": None, "scale": 2.0, "psm": 6},
    {"keyword": "更新", "area": (1050, 80, 1280, 600), "preprocess": None, "scale": 2.0, "psm": 6},
    {"keyword": "设置", "area": (1050, 80, 1280, 600), "preprocess": None, "scale": 2.0, "psm": 6},
]

# 游戏内界面关键词
GAME_KEYWORDS = [
    {"keyword": "状态效果", "area": (1150, 100, 1235, 125), "preprocess": "invert", "scale": 1.0, "psm": 6},
]


# ── 日志 ────────────────────────────────────────────────────────────

def setup_logging() -> logging.Logger:
    log_dir = Path("log")
    log_dir.mkdir(exist_ok=True)
    log_file = os.environ.get("HSR_LOG_FILE") or str(log_dir / f"{time.strftime('%Y-%m-%d_%H-%M-%S')}.log")

    logger = logging.getLogger("launch")
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


def launch_app() -> None:
    from tools.devkit import adb

    try:
        result = adb("shell", "am", "start", "-a", "android.intent.action.MAIN",
                     "-c", "android.intent.category.LAUNCHER",
                     "-n", f"{PACKAGE}/{ACTIVITY}")
        if "Error" not in result and "Warning" not in result:
            log.info(f"am start 成功")
            return
        if "Warning: Activity not started" in result:
            log.info("app 已在运行")
            return
        log.warning(f"am start 异常: {result.strip()[:120]}")
    except Exception as e:
        log.warning(f"am start 失败: {e}")

    try:
        result = adb("shell", "monkey", "-p", PACKAGE,
                     "-c", "android.intent.category.LAUNCHER",
                     "--pct-syskeys", "0", "1")
        if "Events injected" in result:
            log.info("monkey 启动成功")
            return
        log.warning(f"monkey 异常: {result.strip()[:120]}")
    except Exception as e:
        log.error(f"monkey 启动失败: {e}")
        raise


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


def tap_center() -> None:
    from tools.devkit import tap
    tap(*SCREEN_CENTER)
    log.info(f"点击 ({SCREEN_CENTER[0]}, {SCREEN_CENTER[1]})")


# ── OCR 识别 ───────────────────────────────────────────────────────

def check_login_screen(image: np.ndarray) -> bool:
    from perception.matcher import ocr

    # 主关键词
    text = ocr(image, area=LOGIN_PRIMARY["area"], lang="chi_sim+eng",
               preprocess=LOGIN_PRIMARY.get("preprocess"),
               scale=LOGIN_PRIMARY.get("scale", 1.0),
               psm=LOGIN_PRIMARY.get("psm"))
    primary_hit = LOGIN_PRIMARY["keyword"] in text

    # 辅助关键词（同区域共享一次 OCR）
    area_groups: dict[tuple, list[dict]] = {}
    for kw_def in LOGIN_AUXILIARY:
        key = (kw_def["area"], kw_def.get("preprocess"),
               kw_def.get("scale", 1.0), kw_def.get("psm"))
        area_groups.setdefault(key, []).append(kw_def)

    aux_hits = []
    for (area, preprocess, scale, psm), kw_list in area_groups.items():
        text = ocr(image, area=area, lang="chi_sim+eng",
                   preprocess=preprocess, scale=scale, psm=psm)
        for kw_def in kw_list:
            if kw_def["keyword"] in text:
                aux_hits.append(kw_def["keyword"])

    if primary_hit:
        log.info(f"登录界面确认")
    return primary_hit


def check_game_screen(image: np.ndarray) -> bool:
    from perception.matcher import ocr
    for kw_def in GAME_KEYWORDS:
        text = ocr(image, area=kw_def["area"], lang="chi_sim+eng",
                   preprocess=kw_def.get("preprocess"),
                   scale=kw_def.get("scale", 1.0),
                   psm=kw_def.get("psm"))
        if kw_def["keyword"] in text:
            log.info("游戏界面确认")
            return True
    return False



# ── 主流程 ─────────────────────────────────────────────────────────

def run() -> int:
    log.info("=" * 50)
    log.info("崩坏：星穹铁道 启动阶段")
    log.info("=" * 50)

    try:
        ensure_device()
    except Exception as e:
        log.error(f"设备连接失败: {e}")
        return 1

    try:
        launch_app()
    except Exception as e:
        log.error(f"app 启动失败: {e}")
        return 1

    stage = "login"
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

        if stage == "login":
            if check_login_screen(image):
                current_interval = INITIAL_INTERVAL
                tap_center()
                time.sleep(2.0)
                retry_count = 0
                stage = "login_verify"
            else:
                log.info("加载中...")
                if current_interval < MAX_INTERVAL:
                    current_interval = min(current_interval + 1.0, MAX_INTERVAL)

        elif stage == "login_verify":
            if check_login_screen(image):
                retry_count += 1
                if retry_count >= MAX_RETRY:
                    log.error(f"登录界面点击重试 {MAX_RETRY} 次仍未离开")
                    snapshot_error("login_retry_exhausted",
                                   f"点击重试 {MAX_RETRY} 次仍未离开登录界面",
                                   {"stage": stage, "retry_count": retry_count}, image)
                    return 1
                log.info(f"仍在登录界面，再次点击 (重试 {retry_count}/{MAX_RETRY})")
                tap_center()
                time.sleep(2.0)
            else:
                log.info("已离开登录界面")
                current_interval = INITIAL_INTERVAL
                stage = "game"

        elif stage == "game":
            if check_game_screen(image):
                log.info(f"总耗时: {time.time() - start_time:.1f}秒, 截图次数: {screenshot_count}")
                return 0
            else:
                log.info("加载中...")
                if current_interval < MAX_INTERVAL:
                    current_interval = min(current_interval + 1.0, MAX_INTERVAL)

        time.sleep(current_interval)

    return 0


if __name__ == "__main__":
    sys.exit(run())