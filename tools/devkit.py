"""本项目访问模拟器的唯一入口（隔离层）。

======================================================================
为什么需要这一层、它是怎么隔离的
======================================================================

adb 的运作方式是三段式：

    客户端(adb.exe)  ──TCP──▶  server(默认 127.0.0.1:5037)  ──TCP──▶  模拟器(16416)

关键在于：**客户端发现 server 是"别的版本"时，会把 server 杀掉、重启一个自己的。**
本机 Alas 用 adb 29 占着 5037，本项目用 adb 36。
只要拿本项目这版 adb 去连 5037，就会把 Alas 的 server 干掉 —— 这是上次 Alas 掉线的根因。

所以隔离靠三件套，任何一条破了都可能出问题：

    1. 独立二进制：tools/adb/adb.exe     不借系统 / MuMu / Alas 的 adb
    2. 独立端口  ：5038                   两个 server 进程各自独立，设备表互不可见
    3. 显式设备  ：-s 127.0.0.1:16416     绝不裸调，杜绝"连到隔壁实例"

本模块把这三条写死，调用方只管用。手动敲命令请用 `tools/adb.cmd`。

======================================================================
另一个必须记住的事实：wm size 会撒谎
======================================================================
模拟器**分辨率一律以 screencap 实际输出为准**（本模块的 screen_size()）。
"""

from __future__ import annotations

import os
import struct
import subprocess
import time
from pathlib import Path

# ── 隔离配置：改这里，全项目生效 ─────────────────────────────────────
_ROOT = Path(__file__).resolve().parent
ADB_PATH = str(_ROOT / "adb" / "adb.exe")
SERVER_PORT = "5038"  # ⚠️ Alas 占 5037，本项目绝不允许碰 5037
SERIAL = "127.0.0.1:16416"  # ⚠️ MuMu 实例1「崩铁（给AI打货币战争用）」
# 注意：adb 还会自动扫描 5554-5585 端口段，把同一台设备又列成 emulator-5556。
# 那是同一个设备的另一个入口，本模块永远显式带 -s，不受它干扰。

DEFAULT_TIMEOUT = 30.0
LOG_DIR = _ROOT.parent / "log" / "error"  # 错误快照归档目录（抄 Alas）


def _env() -> dict[str, str]:
    """构造子进程环境变量，强制 adb 去连我们自己的 server 端口。

    命令行里已经带了 -P，这里再设一遍环境变量做双保险：
    即使有人从别处 import 本模块、或外部环境被污染，也不会跑偏。
    """
    env = dict(os.environ)
    env["ANDROID_ADB_SERVER_PORT"] = SERVER_PORT
    return env


def _adb_once(*args: str, serial: str | None = SERIAL, binary: bool = False,
              timeout: float = DEFAULT_TIMEOUT):
    """执行一条 adb 命令（不带重试，底层原语）。"""
    cmd = [ADB_PATH, "-P", SERVER_PORT]
    if serial:
        cmd += ["-s", serial]
    cmd += list(args)
    p = subprocess.run(cmd, capture_output=True, env=_env(), timeout=timeout)
    if p.returncode != 0:
        err = p.stderr.decode("utf-8", "replace").strip()
        raise RuntimeError(f"adb {' '.join(args)} 失败: {err}")
    return p.stdout if binary else p.stdout.decode("utf-8", "replace")


# 哪些错误属于"连接问题"，值得重试 —— 其他错误（坐标无效、命令语法错）重试也没用
_CONNECTION_ERRORS = ("device offline", "device not found", "connect",
                       "failed to start", "cannot connect")


def _is_connection_error(e: Exception) -> bool:
    if isinstance(e, subprocess.TimeoutExpired):
        return True
    return any(k in str(e) for k in _CONNECTION_ERRORS)


def adb(*args: str, serial: str | None = SERIAL, binary: bool = False,
        timeout: float = DEFAULT_TIMEOUT, retry: int = 3):
    """执行 adb 命令，连接类错误自动重连重试，逻辑错误直接报。

    为什么区分错误类型：device offline 重连就好；但"点击坐标无效"
    重试一百次也一样失败，盲目重试只会浪费时间。
    """
    last_err = None
    for attempt in range(retry):
        try:
            return _adb_once(*args, serial=serial, binary=binary, timeout=timeout)
        except Exception as e:
            last_err = e
            if attempt >= retry - 1 or not _is_connection_error(e):
                raise
            time.sleep(0.3 * (attempt + 1))  # 递增等待
            try:
                ensure_connected()
            except Exception:
                pass  # 重连失败也继续，下次循环再试
    raise last_err


def snapshot_error(tag: str, error: Exception) -> Path | None:
    """失败时自动截图 + 保存上下文到 log/error/。

    这是抄 Alas 的做法：出错时立刻留一份现场（截图 + 日志），
    事后回放能看到"失败那一刻画面是什么"，对调试价值最高。
    用 _adb_once 而不是 adb，避免快照本身也陷入重试循环。
    """
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    shot = None
    try:
        png = _adb_once("exec-out", "screencap", "-p", binary=True, timeout=5)
        shot = LOG_DIR / f"{ts}_{tag}.png"
        shot.write_bytes(png)
    except Exception:
        pass  # 截图也失败就算了，至少把日志留下
    log = LOG_DIR / f"{ts}_{tag}.log"
    log.write_text(f"时间: {ts}\n标签: {tag}\n错误: {error}\n", encoding="utf-8")
    return shot


def ensure_connected() -> str:
    """确保 server 在跑、目标设备在线；掉线就自动重连。返回设备状态串。"""
    out = adb("devices", serial=None)
    line = next((l for l in out.splitlines() if l.startswith(SERIAL)), None)
    if line is None or "offline" in line:
        adb("connect", SERIAL, serial=None)
        out = adb("devices", serial=None)
        line = next((l for l in out.splitlines() if l.startswith(SERIAL)), None)
    if line is None:
        raise RuntimeError(f"连不上 {SERIAL}，检查 MuMu 实例是否启动")
    state = line.split()[1] if len(line.split()) > 1 else "unknown"
    if state != "device":
        raise RuntimeError(f"{SERIAL} 状态异常: {state}")
    return line


# ── 画面 ────────────────────────────────────────────────────────────

def screencap_png() -> bytes:
    """截图，PNG 格式（设备端压缩，CPU 开销大，只在需要存盘时用）。"""
    return adb("exec-out", "screencap", "-p", binary=True)


def screencap_raw() -> tuple[int, int, bytes]:
    """截图，raw RGBA_8888。返回 (宽, 高, 像素数据)。

    比 PNG 快得多：省掉设备端压缩，代价是数据量大（本地回环传输几乎免费）。
    头部布局各版本不完全一致（12 或 16 字节），这里按长度自动判别。
    """
    d = adb("exec-out", "screencap", binary=True)
    w, h, _fmt = struct.unpack("<III", d[:12])
    payload = d[12:]
    if len(payload) == w * h * 4 + 4:  # 多一个 size 字段
        payload = payload[4:]
    if len(payload) != w * h * 4:
        raise RuntimeError(f"raw 数据长度不符: {len(payload)} != {w * h * 4}")
    return w, h, payload


def screen_size() -> tuple[int, int]:
    """屏幕真实分辨率。以截图为准 —— wm size 报的是假值。"""
    w, h, _ = screencap_raw()
    return w, h


# ── 操作 ────────────────────────────────────────────────────────────

def tap(x: int, y: int) -> None:
    """点击。坐标系与截图一致（已用无障碍树 bounds 验证过，无需换算）。"""
    adb("shell", "input", "tap", str(x), str(y))


def swipe(x1: int, y1: int, x2: int, y2: int, ms: int = 300) -> None:
    adb("shell", "input", "swipe", str(x1), str(y1), str(x2), str(y2), str(ms))


def keyevent(code: str) -> None:
    adb("shell", "input", "keyevent", code)


# ── 自检 ────────────────────────────────────────────────────────────

def self_check() -> bool:
    """打印隔离状态，确认没有踩到 Alas 的 5037。"""
    ok = True
    print(f"adb 二进制 : {ADB_PATH}")
    ver = adb("version").splitlines()
    print(f"adb 版本   : {ver[1] if len(ver) > 1 else ver[0]}")
    print(f"server 端口: {SERVER_PORT}  (Alas 用 5037，两者独立)")
    print(f"目标设备   : {SERIAL}")

    try:
        line = ensure_connected()
        print(f"设备状态   : {line}")
    except Exception as e:
        print(f"设备状态   : ✗ {e}")
        ok = False

    try:
        w, h = screen_size()
        print(f"真实分辨率 : {w} x {h}   ← 来自实际截图，wm size 不可信")
    except Exception as e:
        print(f"真实分辨率 : ✗ {e}")
        ok = False

    # 确认我们没在 5037 上留下任何东西
    out = adb("devices", serial=None)
    others = [l for l in out.splitlines() if l.strip() and "List of devices" not in l]
    if any(l.startswith("127.0.0.1:16384") for l in others):
        print("⚠️  设备表里出现了 Alas 的 16384，检查是否串台")
        ok = False

    print(f"\n隔离自检: {'通过 ✅' if ok else '失败 ❌'}")
    return ok


if __name__ == "__main__":
    raise SystemExit(0 if self_check() else 1)