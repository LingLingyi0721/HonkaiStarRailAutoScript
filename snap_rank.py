"""段位模板截图工具。

截取当前画面的段位徽章区域，保存到 image/rank/ 目录。
用户只需传入模板名称（如 A0, A1, ... A8）。

用法：
    python snap_rank.py A7    # 截取段位区域，保存为 image/rank/A7.png
    python snap_rank.py A8    # 保存为 image/rank/A8.png
"""

import sys
from pathlib import Path

import cv2
import numpy as np

from tools.devkit import screencap_png

# 段位徽章区域（用户从 PS 精确抠取）
RANK_AREA = (72, 236, 108, 264)

# 模板保存目录
TEMPLATE_DIR = Path("image/rank")


def main() -> int:
    if len(sys.argv) < 2:
        print("用法: python snap_rank.py <名称>")
        print("示例: python snap_rank.py A7")
        return 1

    name = sys.argv[1]
    TEMPLATE_DIR.mkdir(parents=True, exist_ok=True)
    out_path = TEMPLATE_DIR / f"{name}.png"

    png = screencap_png()
    img = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_COLOR)

    x1, y1, x2, y2 = RANK_AREA
    region = img[y1:y2, x1:x2]
    cv2.imwrite(str(out_path), region)

    print(f"段位模板已保存: {out_path} ({region.shape[1]}x{region.shape[0]})")
    return 0


if __name__ == "__main__":
    sys.exit(main())