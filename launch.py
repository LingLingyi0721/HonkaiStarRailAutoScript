"""崩坏：星穹铁道 启动脚本。

职责：仅管理 adb 连接和启动游戏 app。
登录界面确认、点击进入、游戏界面确认等全部交给 navigate.py。
"""

from __future__ import annotations

import sys

from common import setup_logging, ensure_device

# ── 配置 ────────────────────────────────────────────────────────────

PACKAGE = "com.miHoYo.hkrpg"
ACTIVITY = "com.mihoyo.combosdk.ComboSDKActivity"

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

    log.info("launch done")
    return 0


if __name__ == "__main__":
    sys.exit(run())