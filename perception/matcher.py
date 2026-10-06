"""感知层底层匹配原语。

=====================================================================
这层做什么
=====================================================================
把 OpenCV 模板匹配、颜色比对、Tesseract OCR 封装成几个干净函数，
上层（pages.py / state.py）只调这些函数，不直接碰 cv2 / pytesseract。

设计参考了 Alas 的 Button/Template 类，但做了简化：
- Alas 的 Button 把 area/color/button 三元组绑死在对象里，适合硬编码流程
- 我们的目标是输出结构化 JSON 给 LLM，所以匹配函数返回数据而不是布尔值
- 模板匹配返回 (相似度, 位置)，让上层决定阈值怎么定

=====================================================================
为什么不用 cnocr（Alas 用的）
=====================================================================
Alas 用 cnocr 做游戏内文字识别，那是专门训练过的模型，对碧蓝航线
的字体效果好。崩铁的字体风格不同，而且我们只需要认数字和少量中文
（金币数、角色名），Tesseract 够用且零额外依赖。
"""

from __future__ import annotations

import cv2
import numpy as np
from PIL import Image
from pathlib import Path

# Tesseract 路径：项目自包含，不依赖外部安装
_ROOT = Path(__file__).resolve().parent.parent
_TESSERACT_PATH = str(_ROOT / "tools" / "tesseract" / "tesseract.exe")

# ── 图像加载与裁剪 ──────────────────────────────────────────────────

def load_image(path: str | Path) -> np.ndarray:
    """加载图片为 BGR numpy 数组（OpenCV 惯用格式）。"""
    img = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if img is None:
        raise FileNotFoundError(f"读不了图: {path}")
    return img


def crop(image: np.ndarray, area: tuple[int, int, int, int]) -> np.ndarray:
    """裁剪区域 (x1, y1, x2, y2)。坐标与截图一致，无需换算。"""
    x1, y1, x2, y2 = area
    return image[y1:y2, x1:x2]


def save_image(image: np.ndarray, path: str | Path) -> None:
    """存图，调试用。"""
    cv2.imwrite(str(path), image)


# ── 颜色匹配 ────────────────────────────────────────────────────────

def get_color(image: np.ndarray, area: tuple[int, int, int, int]) -> tuple[int, int, int]:
    """取区域平均颜色 (B, G, R)。Alas 同名函数的逻辑。"""
    region = crop(image, area)
    mean = region.reshape(-1, 3).mean(axis=0)
    return tuple(int(v) for v in mean)


def color_similar(c1: tuple, c2: tuple, threshold: int = 30) -> bool:
    """两个颜色是否在阈值内相似。threshold 是各通道允许的偏差。"""
    return all(abs(a - b) <= threshold for a, b in zip(c1, c2))


# ── 模板匹配 ────────────────────────────────────────────────────────

def template_match(
    template: np.ndarray,
    image: np.ndarray,
    area: tuple[int, int, int, int] | None = None,
    similarity: float = 0.85,
) -> tuple[float, tuple[int, int]]:
    """在 image 中找 template，返回 (相似度, 左上角坐标)。

    如果指定了 area，只在那个区域里找（缩小搜索范围提速）。
    用 TM_CCOEFF_NORMED（归一化相关系数），和 Alas 一致。

    返回值：
        similarity: 0~1，越高越像
        location: template 左上角在 image 中的坐标 (x, y)
    """
    search_area = crop(image, area) if area else image
    result = cv2.matchTemplate(search_area, template, cv2.TM_CCOEFF_NORMED)
    _, sim, _, loc = cv2.minMaxLoc(result)

    # 如果在裁剪区域里找的，坐标要加回偏移
    if area:
        loc = (loc[0] + area[0], loc[1] + area[1])

    return float(sim), loc


def template_match_multi(
    template: np.ndarray,
    image: np.ndarray,
    similarity: float = 0.85,
    min_distance: int = 10,
) -> list[tuple[float, tuple[int, int]]]:
    """找所有匹配位置，返回 [(相似度, 坐标), ...]。

    用于商店格子、角色头像等"画面上可能出现多个同类元素"的场景。
    min_distance: 相邻结果的最小间距（像素），避免同一目标被重复检出。
    """
    result = cv2.matchTemplate(image, template, cv2.TM_CCOEFF_NORMED)
    locations = np.where(result >= similarity)
    scores = result[locations]

    # 合并相近的结果
    points = list(zip(scores.tolist(), zip(locations[1].tolist(), locations[0].tolist())))
    if not points:
        return []

    # 按相似度降序排，贪心剔除太近的
    points.sort(key=lambda p: -p[0])
    kept: list[tuple[float, tuple[int, int]]] = []
    for score, pt in points:
        if all(abs(pt[0] - k[1][0]) + abs(pt[1] - k[1][1]) >= min_distance for k in kept):
            kept.append((score, pt))
    return kept


def match_binary(
    template: np.ndarray,
    image: np.ndarray,
    area: tuple[int, int, int, int] | None = None,
    similarity: float = 0.85,
) -> tuple[float, tuple[int, int]]:
    """二值化后模板匹配。对光照变化更鲁棒。

    Alas 的 match_binary 逻辑：先把 template 和 image 都转灰度+Otsu 二值化，
    再做 matchTemplate。适合按钮文字、图标等高对比度元素。
    """
    search_area = crop(image, area) if area else image

    tpl_gray = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
    _, tpl_bin = cv2.threshold(tpl_gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)

    img_gray = cv2.cvtColor(search_area, cv2.COLOR_BGR2GRAY)
    _, img_bin = cv2.threshold(img_gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)

    result = cv2.matchTemplate(img_bin, tpl_bin, cv2.TM_CCOEFF_NORMED)
    _, sim, _, loc = cv2.minMaxLoc(result)

    if area:
        loc = (loc[0] + area[0], loc[1] + area[1])

    return float(sim), loc


# ── OCR ─────────────────────────────────────────────────────────────

_pytesseract = None


def _get_tesseract():
    """懒加载 pytesseract，避免 import 时就要求装好。"""
    global _pytesseract
    if _pytesseract is None:
        import pytesseract
        pytesseract.pytesseract.tesseract_cmd = _TESSERACT_PATH
        _pytesseract = pytesseract
    return _pytesseract


def ocr(
    image: np.ndarray,
    area: tuple[int, int, int, int] | None = None,
    lang: str = "chi_sim",
    whitelist: str | None = None,
    preprocess: str | None = None,
    scale: float = 1.0,
    psm: int | None = None,
) -> str:
    """对图片（或指定区域）做 OCR，返回识别出的文本。

    Args:
        image: 截图 BGR 数组
        area: (x1,y1,x2,y2)，指定区域；None 则整图
        lang: Tesseract 语言包。chi_sim=简体中文，eng=英文，chi_sim+eng=混合
        whitelist: 只认这些字符（如 "0123456789" 只认数字）
        preprocess: 预处理方式，改善特定场景的识别率：
            None     — 不处理（默认）
            "invert" — 灰度+反转颜色（白字深底场景，如崩铁登录界面）
            "binary" — 灰度+Otsu二值化（高对比度场景）
            "invert_binary" — 灰度+反转+二值化（白字深底+降噪）
        scale: 放大倍数（崩铁小字需放大2-3倍 Tesseract 才能识别）
        psm: Tesseract 页面分割模式（None=默认, 6=统一文本块, 7=单行, 11=稀疏文本）
    """
    region = crop(image, area) if area else image

    # 放大
    if scale > 1.0:
        region = cv2.resize(region, None, fx=scale, fy=scale,
                             interpolation=cv2.INTER_CUBIC)

    if preprocess:
        gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)
        if preprocess == "invert":
            processed = cv2.bitwise_not(gray)
        elif preprocess == "binary":
            _, processed = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
        elif preprocess == "invert_binary":
            inverted = cv2.bitwise_not(gray)
            _, processed = cv2.threshold(inverted, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
        else:
            processed = gray
        pil = Image.fromarray(processed)
    else:
        rgb = cv2.cvtColor(region, cv2.COLOR_BGR2RGB)
        pil = Image.fromarray(rgb)

    ts = _get_tesseract()
    config = ""
    if psm is not None:
        config += f"--psm {psm}"
    if whitelist:
        if config:
            config += " "
        config += f"-c tessedit_char_whitelist={whitelist}"
    text = ts.image_to_string(pil, lang=lang, config=config)
    return text.strip()


def ocr_digits(image: np.ndarray, area: tuple[int, int, int, int] | None = None) -> str:
    """只认数字的 OCR，用于金币数、利息、等级等。"""
    return ocr(image, area, lang="eng", whitelist="0123456789")


# ── 区域工具 ────────────────────────────────────────────────────────

def area_center(area: tuple[int, int, int, int]) -> tuple[int, int]:
    """区域中心点，用于点击。"""
    x1, y1, x2, y2 = area
    return ((x1 + x2) // 2, (y1 + y2) // 2)


def area_offset(area: tuple[int, int, int, int], dx: int, dy: int) -> tuple[int, int, int, int]:
    """平移区域。"""
    x1, y1, x2, y2 = area
    return (x1 + dx, y1 + dy, x2 + dx, y2 + dy)