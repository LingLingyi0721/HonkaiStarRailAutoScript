"""感知层主 API。

用法：
    from perception import perceive_screenshot
    state = perceive_screenshot()  # 自动截图 + 识别 + 提取
    # state 是一个 dict，直接喂给 LLM

或者手动传入截图：
    from perception import perceive
    from tools.devkit import screencap_png
    import cv2
    import numpy as np

    png_bytes = screencap_png()
    image = cv2.imdecode(np.frombuffer(png_bytes, np.uint8), cv2.IMREAD_COLOR)
    state = perceive(image)
"""

from __future__ import annotations

import cv2
import numpy as np

from perception.matcher import *
from perception.assets import *
from perception.pages import identify_page
from perception.state import perceive, register_extractor


def perceive_screenshot() -> dict:
    """一键感知：截图 → 识别页面 → 提取状态 → 返回 JSON。

    这是编排层最常用的入口。返回的 dict 可以直接序列化为 JSON
    传给 LLM。
    """
    from tools.devkit import screencap_png

    png_bytes = screencap_png()
    image = cv2.imdecode(np.frombuffer(png_bytes, np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise RuntimeError("截图解码失败")

    return perceive(image)


__all__ = [
    "perceive",
    "perceive_screenshot",
    "identify_page",
    "register_extractor",
    "register_template",
    "register_area",
    "register_page",
    "get_template",
    "get_area",
    "get_page",
    # matcher 函数
    "load_image",
    "crop",
    "get_color",
    "color_similar",
    "template_match",
    "template_match_multi",
    "match_binary",
    "ocr",
    "ocr_digits",
    "area_center",
    "area_offset",
]