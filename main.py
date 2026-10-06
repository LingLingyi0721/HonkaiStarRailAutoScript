"""编排层：按顺序调度各阶段脚本。

用法：
    python main.py              # 全部阶段
    python main.py --from guide # 从指定阶段开始
    python main.py --only launch # 只跑单个阶段
    python main.py --rank A8-10  # 指定目标段位层级
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

# ── 阶段注册 ───────────────────────────────────────────────────────

STAGES = [
    ("launch",    "launch game",     "launch"),
    ("navigate",  "navigate to war", "navigate"),
    ("boss_info", "boss info",       "boss_info"),
    # ("settle",  "settle & loop",   "settle"),
]


def run_stage(name: str, label: str, module: str, **kwargs) -> int:
    print(f"\nstage: {name} — {label}")

    try:
        mod = __import__(module)
    except ImportError as e:
        print(f"[ERROR] 模块导入失败: {module}: {e}")
        return 1

    try:
        rc = mod.run(**kwargs) if kwargs else mod.run()
    except Exception as e:
        print(f"[ERROR] 阶段异常: {name}: {e}")
        return 1

    if rc != 0:
        print(f"[ERROR] 阶段失败: {name} (rc={rc})")
        return rc

    print(f"[OK] 阶段完成: {name}")
    return 0


# ── 主流程 ─────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="HSR auto script")
    parser.add_argument("--from", dest="start", default=None,
                        help="从指定阶段开始（跳过之前的阶段）")
    parser.add_argument("--only", dest="only", default=None,
                        help="只跑指定阶段")
    parser.add_argument("--skip-tools-check", action="store_true",
                        help="跳过工具自包含检测")
    parser.add_argument("--rank", dest="rank_level", default=None,
                        help="目标段位层级，如 A8-10。不指定则保持当前位置")
    args = parser.parse_args()

    # 工具自包含检测与部署
    if not args.skip_tools_check:
        from tools.ensure_tools import ensure_all
        ensure_all()

    # 确定要跑的阶段列表
    if args.only:
        stages = [(n, l, m) for n, l, m in STAGES if n == args.only]
        if not stages:
            print(f"[ERROR] 未知阶段: {args.only}")
            print(f"可用阶段: {[n for n, _, _ in STAGES]}")
            return 1
    elif args.start:
        idx = next((i for i, (n, _, _) in enumerate(STAGES) if n == args.start), None)
        if idx is None:
            print(f"[ERROR] 未知阶段: {args.start}")
            print(f"可用阶段: {[n for n, _, _ in STAGES]}")
            return 1
        stages = STAGES[idx:]
    else:
        stages = STAGES

    total_start = time.time()

    # 设置统一日志文件路径，各子模块通过环境变量读取
    log_dir = Path("log")
    log_dir.mkdir(exist_ok=True)
    log_file = str(log_dir / f"{time.strftime('%Y-%m-%d_%H-%M-%S')}.log")
    os.environ["HSR_LOG_FILE"] = log_file
    print(f"log file: {log_file}")

    print(f"stages: {[n for n, _, _ in stages]}")

    for name, label, module in stages:
        if name == "navigate" and args.rank_level:
            stage_kwargs["target_rank_level"] = args.rank_level
        rc = run_stage(name, label, module, **stage_kwargs)
        if rc != 0:
            print(f"\naborted: stage {name} failed")
            print(f"completed: {[n for n, _, _ in stages[:stages.index((name, label, module))]]}")
            return rc

    elapsed = time.time() - total_start
    print(f"\nall done: {elapsed:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())