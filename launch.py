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
            log.info("am start 成功")
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


def run() -> int:
    log.info("=" * 50)
    log.info("崩坏：星穹铁道 启动阶段")
    log.info("=" * 50)

    try:
        ensure_device(log)
    except Exception as e:
        log.error(f"设备连接失败: {e}")
        return 1

    try:
        launch_app()
    except Exception as e:
        log.error(f"app 启动失败: {e}")
        return 1

    log.info("启动完成，交由 navigate 接管")
    return 0


if __name__ == "__main__":
    sys.exit(run())