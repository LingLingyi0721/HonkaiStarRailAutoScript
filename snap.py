"""截图工具：截取当前画面并保存到 tmp/snap.png。

用法：
    python snap.py          # 截图保存到 tmp/snap.png
    python snap.py abc      # 截图保存到 tmp/snap_abc.png
"""

import sys
import time
from pathlib import Path

import cv2
import numpy as np

from tools.devkit import screencap_png

name = sys.argv[1] if len(sys.argv) > 1 else "snap"
out = Path(f"tmp/{name}.png")
out.parent.mkdir(exist_ok=True)

png = screencap_png()
img = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_COLOR)
cv2.imwrite(str(out), img)
print(f"截图已保存: {out} ({img.shape[1]}x{img.shape[0]})")