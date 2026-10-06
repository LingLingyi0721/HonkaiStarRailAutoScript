"""P0 通道基准测试：各截图路径的延迟 / 点击延迟。

adb 路径、server 端口、目标设备全部来自 devkit，本文件不再自己维护一份，
避免"改一处漏一处"—— 隔离配置只允许存在一个源头。

另外记一个 Windows 上的坑：
    `adb exec-out screencap -p > x.png` 这种 shell 重定向会经过文本模式转换，
    换行符被改写，PNG 直接损坏。必须用 Python 的 subprocess 拿原始 bytes。

用法：
    python tools/bench_device.py                 # 只测截图（安全，不干扰挂机）
    python tools/bench_device.py --rounds 10
    python tools/bench_device.py --tap 640 360   # 额外测点击（会真实点击！）
"""

from __future__ import annotations

import argparse
import statistics
import sys
import time

import devkit

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
PNG_IEND = b"IEND\xaeB`\x82"


def bench_png(rounds: int) -> tuple[list[float], list[int], bool]:
    """路径 A：exec-out 直出 PNG（设备端要压缩，开销大）。"""
    times, sizes, ok = [], [], True
    for _ in range(rounds):
        t0 = time.perf_counter()
        d = devkit.screencap_png()
        times.append(time.perf_counter() - t0)
        sizes.append(len(d))
        if not (d.startswith(PNG_MAGIC) and PNG_IEND in d[-16:]):
            ok = False
    return times, sizes, ok


def bench_raw(rounds: int) -> tuple[list[float], list[int]]:
    """路径 B：raw RGBA（省掉设备端压缩，但数据量变大）。"""
    times, sizes = [], []
    for _ in range(rounds):
        t0 = time.perf_counter()
        _w, _h, payload = devkit.screencap_raw()
        times.append(time.perf_counter() - t0)
        sizes.append(len(payload))
    return times, sizes


def bench_tap(x: int, y: int, rounds: int) -> list[float]:
    times = []
    for _ in range(rounds):
        t0 = time.perf_counter()
        devkit.tap(x, y)
        times.append(time.perf_counter() - t0)
    return times


def fmt(times: list[float]) -> str:
    ms = [t * 1000 for t in times]
    sd = statistics.stdev(ms) if len(ms) > 1 else 0.0
    return (f"平均 {statistics.mean(ms):7.1f} ms | 最小 {min(ms):7.1f} | "
            f"最大 {max(ms):7.1f} | 抖动 {sd:6.1f} ms")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds", type=int, default=5)
    ap.add_argument("--tap", nargs=2, type=int, metavar=("X", "Y"),
                    help="额外测点击延迟（会真实点击，别在挂机任务里乱用）")
    args = ap.parse_args()

    print(f"adb      : {devkit.ADB_PATH}")
    print(f"server   : 127.0.0.1:{devkit.SERVER_PORT}   (Alas 独立占用 5037)")
    print(f"设备     : {devkit.SERIAL}")
    print(f"状态     : {devkit.ensure_connected()}")
    w, h = devkit.screen_size()
    print(f"分辨率   : {w} x {h}   (实测自截图，不是 wm size)\n")

    tp, sp, ok = bench_png(args.rounds)
    print(f"[PNG]  {fmt(tp)}")
    print(f"       体积 {statistics.mean(sp) / 1024:.1f} KB | 完整性 {'OK' if ok else '损坏'}")

    tr, sr = bench_raw(args.rounds)
    print(f"[raw]  {fmt(tr)}")
    print(f"       体积 {statistics.mean(sr) / 1024:.1f} KB")

    ratio = statistics.mean(tp) / statistics.mean(tr)
    print(f"\nPNG 比 raw 慢 {ratio:.2f} 倍 —— 这个倍数就是设备端压缩的纯成本")

    if args.tap:
        x, y = args.tap
        print(f"\n[tap {x},{y}]  {fmt(bench_tap(x, y, args.rounds))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())