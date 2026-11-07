"""启动游戏 app 并进入主界面。

阶段范围：adb 启动 app → 等待登录界面 → 点击进入 → 等待游戏主界面。
后续（指南起）交给 navigate.py。
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

from common import setup_logging, ensure_device, tap, proceed_to_next

# ── 配置 ────────────────────────────────────────────────────────────

PACKAGE = "com.miHoYo.hkrpg"
ACTIVITY = "com.mihoyo.combosdk.ComboSDKActivity"

CACHE_SCREENSHOT = Path("tmp/launch_screenshot.png")

# 登录界面
LOGIN_KEYWORDS = [
    {"keyword": "点击进入", "area": (450, 450, 810, 700)},
]
SCREEN_CENTER = (640, 360)

# 游戏主界面
GAME_KEYWORDS = [
    {"keyword": "状态效果", "area": (1150, 100, 1235, 125)},
]

log = setup_logging("launch")


def launch_app() -> None:
    """通过 adb 启动崩铁 app。"""
    from tools.devkit import adb

    try:
        result = adb("shell", "am", "start", "-a", "android.intent.action.MAIN",
                     "-c", "android.intent.category.LAUNCHER",
                     "-n", f"{PACKAGE}/{ACTIVITY}")
        if "Error" not in result and "Warning" not in result:
            log.info("am start ok")
            return
        if "Warning: Activity not started" in result:
            log.info("app already running")
            return
        log.warning(f"am start warning: {result.strip()[:120]}")
    except Exception as e:
        log.warning(f"am start failed: {e}")

    try:
        result = adb("shell", "monkey", "-p", PACKAGE,
                     "-c", "android.intent.category.LAUNCHER",
                     "--pct-syskeys", "0", "1")
        if "Events injected" in result:
            log.info("monkey start ok")
            return
        log.warning(f"monkey warning: {result.strip()[:120]}")
    except Exception as e:
        log.error(f"monkey failed: {e}")
        raise


def run() -> int:
    log.info("launch start")

    try:
        ensure_device(log)
    except Exception as e:
        log.error(f"device connect failed: {e}")
        return 1

    try:
        launch_app()
    except Exception as e:
        log.error(f"app launch failed: {e}")
        return 1

    # ── 1. 等待登录界面（持续识别，超时120秒）→ 点击屏幕中央 ──
    log.info("stage 1: wait login")
    if not proceed_to_next(
        log, LOGIN_KEYWORDS, None, "login",
        cache_path=CACHE_SCREENSHOT, timeout=120,
    ):
        return 1
    tap(log, *SCREEN_CENTER)
    time.sleep(2.0)

    # ── 2. 等待游戏主界面（持续识别，超时120秒）──
    log.info("stage 2: wait main")
    if not proceed_to_next(
        log, GAME_KEYWORDS, None, "main",
        cache_path=CACHE_SCREENSHOT, timeout=120,
    ):
        return 1

    log.info("launch done: at main screen")
    return 0


if __name__ == "__main__":
    sys.exit(run())