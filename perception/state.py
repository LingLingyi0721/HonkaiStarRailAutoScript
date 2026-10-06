"""状态提取：从截图中提取结构化信息，输出给 LLM 决策。

=====================================================================
这层做什么
=====================================================================
知道当前在哪个页面后，提取该页面上的关键信息：
- 可交互元素（按钮、卡片）及其位置
- 文字内容（金币数、角色名、羁绊名等）
- 其他数值（等级、回合数等）

最终输出一个干净的 JSON，LLM 只看这个 JSON 就能做决策，
不需要看原始截图——省 token，也更稳定。

=====================================================================
输出格式
=====================================================================
{
    "page": "cw_shop",
    "confidence": 0.92,
    "elements": [
        {"name": "refresh_shop", "area": [1100,400,1200,450], "click": [1150,425], "visible": true},
        ...
    ],
    "texts": {
        "gold": "50",
        "interest": "5",
        "shop_level": "3",
        ...
    }
}
"""

from __future__ import annotations

import cv2
import numpy as np
from typing import Any

from perception.matcher import (
    load_image, template_match, template_match_multi, match_binary,
    get_color, color_similar, ocr_rapid_text, ocr_digits, crop, area_center
)
from perception.assets import (
    get_template, get_area, all_templates, TemplateDef, AreaDef
)
from perception.pages import identify_page


def perceive(image: np.ndarray) -> dict[str, Any]:
    """主入口：从截图提取结构化状态。

    Args:
        image: BGR numpy 数组（截图）

    Returns:
        结构化状态字典，格式见模块文档
    """
    page_name, confidence = identify_page(image)

    state: dict[str, Any] = {
        "page": page_name,
        "confidence": round(confidence, 3),
        "elements": [],
        "texts": {},
    }

    # 根据页面类型提取不同的信息
    extractor = _EXTRACTORS.get(page_name)
    if extractor:
        extractor(image, state)

    return state


# ── 页面专属提取器 ──────────────────────────────────────────────────
# 每个提取器函数签名: (image, state) -> None，直接修改 state 字典
# TODO: 等游戏画面出来后，根据实际 UI 编写具体提取逻辑

_EXTRACTORS: dict[str, Any] = {}


def register_extractor(page_name: str):
    """装饰器：注册页面专属状态提取器。"""
    def decorator(fn):
        _EXTRACTORS[page_name] = fn
        return fn
    return decorator


# ── 通用提取工具 ────────────────────────────────────────────────────

def find_elements(
    image: np.ndarray,
    templates: list[TemplateDef],
) -> list[dict[str, Any]]:
    """在截图中查找多个模板，返回找到的元素列表。

    每个元素包含：name, area, click(中心点), visible
    """
    elements = []
    for tpl_def in templates:
        try:
            template = load_image(tpl_def.path)
        except FileNotFoundError:
            continue

        if tpl_def.binary:
            sim, loc = match_binary(template, image, area=tpl_def.area, similarity=tpl_def.similarity)
        else:
            sim, loc = template_match(template, image, area=tpl_def.area, similarity=tpl_def.similarity)

        h, w = template.shape[:2]
        area = (loc[0], loc[1], loc[0] + w, loc[1] + h)
        elements.append({
            "name": tpl_def.name,
            "area": list(area),
            "click": list(area_center(area)),
            "visible": sim >= tpl_def.similarity,
            "similarity": round(sim, 3),
        })
    return elements


def extract_text_from_areas(
    image: np.ndarray,
    areas: dict[str, AreaDef],
    digits_only: bool = False,
) -> dict[str, str]:
    """对指定区域做 OCR，返回 {字段名: 文字}。"""
    texts = {}
    for name, area_def in areas.items():
        if digits_only:
            text = ocr_digits(image, area_def.area)
        else:
            text = ocr_rapid_text(image, area_def.area)
        if text:
            texts[name] = text
    return texts


# ── 占位提取器（等游戏画面后填充） ──────────────────────────────────

@register_extractor("cw_shop")
def _extract_cw_shop(image: np.ndarray, state: dict) -> None:
    """货币战争商店页状态提取。

    需要提取：
    - 金币数、利息、商店等级
    - 商店里有哪些角色（名字 + 价格）
    - 可交互按钮（刷新、购买、升人口）
    """
    # TODO: 等游戏画面出来后，用实际截图校准坐标和模板
    pass


@register_extractor("cw_battle_prep")
def _extract_cw_battle_prep(image: np.ndarray, state: dict) -> None:
    """货币战争战斗准备页状态提取。

    需要提取：
    - 当前阵容（角色名 + 羁绊）
    - 站位信息（前排/后排）
    - 装备信息
    - 可交互按钮（开始战斗、调整站位）
    """
    # TODO: 等游戏画面出来后填充
    pass


@register_extractor("cw_battle")
def _extract_cw_battle(image: np.ndarray, state: dict) -> None:
    """货币战争战斗进行中状态提取。

    战斗中一般不需要干预，但需要判断战斗是否结束。
    """
    # TODO: 等游戏画面出来后填充
    pass


@register_extractor("cw_result")
def _extract_cw_result(image: np.ndarray, state: dict) -> None:
    """货币战争结算页状态提取。

    需要提取：
    - 胜负结果
    - 获得金币
    - 可交互按钮（继续/退出）
    """
    # TODO: 等游戏画面出来后填充
    pass


@register_extractor("loading")
def _extract_loading(image: np.ndarray, state: dict) -> None:
    """加载页状态提取。只需要确认在加载中即可。"""
    state["texts"]["status"] = "loading"