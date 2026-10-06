"""工具自包含部署：自动检测并部署 ddddocr 和 Tesseract 到 tools/ 目录。

运行脚本时自动调用，确保项目不依赖全局 pip 安装位置。
也支持手动执行：python tools/ensure_tools.py
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_TOOLS = _ROOT / "tools"


def ensure_tesseract() -> bool:
    """检测 Tesseract 是否在 tools/tesseract/ 下。"""
    exe = _TOOLS / "tesseract" / "tesseract.exe"
    if exe.exists():
        print("[OK] Tesseract 已部署:", exe)
        return True
    print("[MISS] Tesseract 未找到:", exe)
    print("       请手动复制 Tesseract 到 tools/tesseract/")
    return False


def ensure_ddddocr() -> bool:
    """检测 ddddocr 是否在 tools/ddddocr/ 下，不存在则从 pip 安装位置复制。"""
    target = _TOOLS / "ddddocr"
    marker = target / "__init__.py"

    if marker.exists():
        # 检查模型文件是否存在
        model = target / "common.onnx"
        if model.exists():
            print("[OK] ddddocr 已部署:", target)
            return True
        print("[WARN] ddddocr 目录存在但缺少模型文件，重新复制")

    # 从 pip 安装位置复制
    print("[INFO] 正在部署 ddddocr 到 tools/...")
    try:
        import ddddocr as _src
        src_dir = Path(_src.__file__).resolve().parent
    except ImportError:
        print("[INFO] ddddocr 未安装，正在 pip install...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "ddddocr"])
        import ddddocr as _src
        src_dir = Path(_src.__file__).resolve().parent

    # 复制整个包
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(src_dir, target, dirs_exist_ok=True)

    # 删除不需要的大文件（检测模型，我们只用 classification）
    for unused in ["common_det.onnx"]:
        p = target / unused
        if p.exists():
            p.unlink()
            print(f"       跳过不需要的模型: {unused}")

    # 删除 __pycache__
    for pyc in target.rglob("__pycache__"):
        shutil.rmtree(pyc, ignore_errors=True)

    model = target / "common.onnx"
    if model.exists():
        size_mb = model.stat().st_size // 1024 // 1024
        print(f"[OK] ddddocr 部署完成: {target} (common.onnx {size_mb}MB)")
        return True
    print("[FAIL] ddddocr 部署失败：缺少 common.onnx")
    return False


def ensure_all() -> bool:
    """检测并部署所有工具，返回是否全部就绪。"""
    ok = True
    ok = ensure_tesseract() and ok
    ok = ensure_ddddocr() and ok
    return ok


if __name__ == "__main__":
    sys.exit(0 if ensure_all() else 1)