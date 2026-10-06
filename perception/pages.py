"""页面识别：判断当前截图属于哪个页面。

=====================================================================
这层做什么
=====================================================================
拿到一张截图，判断"现在在哪个页面"。这是感知层的第一步——
LLM 需要知道当前上下文才能做决策。

识别逻辑：
1. 遍历所有已注册的 PageMark（按优先级降序）
2. 对每个页面，检查它的模板匹配 + 颜色校验是否全部通过
3. 第一个全部通过的页面就是当前页面
4. 如果都不通过，返回 "unknown"

=====================================================================
为什么不用更花哨的方法（如深度学习页面分类）
=====================================================================
模板匹配 + 颜色校验足够快（<50ms），足够准（固定分辨率下几乎无误判），
而且不需要训练数据。Alas 用这套方法跑了几年，验证过可靠性。
"""

from __future__ import annotations

import cv2
import numpy as np

from perception.matcher import (
    load_image, template_match, match_binary, get_color, color_similar
)
from perception.assets import all_pages, get_template, PageMark


def identify_page(image: np.ndarray) -> tuple[str, float]:
    """识别当前截图属于哪个页面。

    Args:
        image: BGR numpy 数组（截图）

    Returns:
        (page_name, confidence): 页面名和置信度
        page_name 为 "unknown" 时表示无法识别
    """
    best_page = "unknown"
    best_conf = 0.0

    for page in all_pages():
        conf = _check_page(image, page)
        if conf > best_conf:
            best_page = page.name
            best_conf = conf

    return best_page, best_conf


def _check_page(image: np.ndarray, page: PageMark) -> float:
    """检查一张截图是否符合某个页面的特征。

    返回置信度 0~1。所有特征都通过才返回高置信度。
    """
    if not page.templates and not page.color_checks:
        # 没定义任何特征的页面，跳过（占位页面）
        return 0.0

    scores = []

    # 模板匹配
    for tpl_def in page.templates:
        try:
            template = load_image(tpl_def.path)
        except FileNotFoundError:
            # 模板图片还没截出来，跳过这个特征
            continue

        if tpl_def.binary:
            sim, _ = match_binary(template, image, area=tpl_def.area, similarity=tpl_def.similarity)
        else:
            sim, _ = template_match(template, image, area=tpl_def.area, similarity=tpl_def.similarity)

        if sim < tpl_def.similarity:
            return 0.0  # 任一特征不满足，直接否决
        scores.append(sim)

    # 颜色校验
    for area_def, expected_color, threshold in page.color_checks:
        actual_color = get_color(image, area_def.area)
        if not color_similar(actual_color, expected_color, threshold):
            return 0.0
        # 颜色匹配的置信度：越接近越高
        diff = sum(abs(a - b) for a, b in zip(actual_color, expected_color))
        scores.append(1.0 - diff / (3 * threshold))

    if not scores:
        return 0.0

    return sum(scores) / len(scores)